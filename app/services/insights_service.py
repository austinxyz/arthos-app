"""LLM-powered stock insights service using Google AI Studio (Gemini)."""
import os
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlmodel import Session, select

from app.database import engine
from app.models.stock_price import StockAttributes

logger = logging.getLogger(__name__)

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # "groq" or "gemini"
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
GOOGLE_AI_MODEL = os.getenv("GOOGLE_AI_MODEL", "gemini-2.0-flash")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
INSIGHTS_STALE_HOURS = 24
LLM_TIMEOUT_SECONDS = 30

# LLM Prompt template
INSIGHTS_PROMPT = """You are an experienced stock market analyst. Analyze the stock {ticker} and provide insights.

Return a JSON object with exactly this structure:
{{
  "going_right": [
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}}
  ],
  "going_wrong": [
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}},
    {{"title": "Brief headline", "description": "1-2 sentence explanation"}}
  ]
}}

Consider these factors:
- Fundamentals (revenue, earnings, margins, debt)
- Technical indicators (price trends, moving averages, volume)
- Market conditions and sector performance
- Business developments (products, partnerships, management)
- Competitive positioning
- Macroeconomic factors

Be specific and actionable. Use recent data and developments.
Return ONLY the JSON object, no additional text or markdown formatting."""


def is_insights_stale(updated_at: Optional[datetime]) -> bool:
    """
    Check if insights are stale (older than INSIGHTS_STALE_HOURS).

    Args:
        updated_at: Timestamp when insights were last updated

    Returns:
        True if insights are stale or missing, False if fresh
    """
    if updated_at is None:
        return True

    stale_threshold = datetime.utcnow() - timedelta(hours=INSIGHTS_STALE_HOURS)
    return updated_at < stale_threshold


def _parse_llm_response(response_text: str, ticker: str) -> Optional[Dict[str, Any]]:
    """
    Parse and validate LLM response text into insights dictionary.

    Args:
        response_text: Raw text response from LLM
        ticker: Stock ticker symbol (for logging)

    Returns:
        Dictionary with 'going_right' and 'going_wrong' lists, or None on failure
    """
    try:
        # Remove markdown code blocks if present
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Fix trailing commas (common LLM issue - valid in JS but not JSON)
        # Remove trailing commas before ] or }
        text = re.sub(r',(\s*[}\]])', r'\1', text)

        insights = json.loads(text)

        # Validate structure
        if "going_right" not in insights or "going_wrong" not in insights:
            logger.error(f"Invalid insights structure for {ticker}: missing required keys")
            return None

        if not isinstance(insights["going_right"], list) or not isinstance(insights["going_wrong"], list):
            logger.error(f"Invalid insights structure for {ticker}: values must be lists")
            return None

        return insights

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON for {ticker}: {e}")
        return None


def _fetch_insights_from_gemini(ticker: str, prompt: str) -> Optional[str]:
    """Fetch insights using Google Gemini API."""
    if not GOOGLE_AI_API_KEY:
        logger.error("GOOGLE_AI_API_KEY not configured")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_AI_API_KEY)

        response = client.models.generate_content(
            model=GOOGLE_AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2048,
            )
        )

        if not response or not response.text:
            logger.error(f"Empty response from Gemini for {ticker}")
            return None

        return response.text

    except Exception as e:
        logger.error(f"Error fetching insights from Gemini for {ticker}: {e}")
        return None


def _fetch_insights_from_groq(ticker: str, prompt: str) -> Optional[str]:
    """Fetch insights using Groq API."""
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not configured")
        return None

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        response = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=2048,
        )

        if not response or not response.choices or not response.choices[0].message.content:
            logger.error(f"Empty response from Groq for {ticker}")
            return None

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Error fetching insights from Groq for {ticker}: {e}")
        return None


def fetch_insights_from_llm(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch insights from configured LLM provider for a given ticker.

    Uses LLM_PROVIDER environment variable to select between 'groq' and 'gemini'.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dictionary with 'going_right' and 'going_wrong' lists, or None on failure
    """
    prompt = INSIGHTS_PROMPT.format(ticker=ticker.upper())

    # Select provider based on configuration
    if LLM_PROVIDER == "gemini":
        logger.info(f"Fetching insights for {ticker} using Gemini ({GOOGLE_AI_MODEL})")
        response_text = _fetch_insights_from_gemini(ticker, prompt)
    else:  # Default to groq
        logger.info(f"Fetching insights for {ticker} using Groq ({GROQ_MODEL})")
        response_text = _fetch_insights_from_groq(ticker, prompt)

    if not response_text:
        return None

    insights = _parse_llm_response(response_text, ticker)

    if insights:
        logger.info(f"Successfully fetched insights for {ticker}")

    return insights


def save_insights(ticker: str, insights: Dict[str, Any]) -> bool:
    """
    Save insights to the database.

    Args:
        ticker: Stock ticker symbol
        insights: Dictionary with insights data

    Returns:
        True on success, False on failure
    """
    try:
        with Session(engine) as session:
            # Get or create StockAttributes
            statement = select(StockAttributes).where(StockAttributes.ticker == ticker.upper())
            stock_attr = session.exec(statement).first()

            if stock_attr:
                stock_attr.insights_json = json.dumps(insights)
                stock_attr.insights_updated_at = datetime.utcnow()
                session.add(stock_attr)
                session.commit()
                logger.info(f"Saved insights for {ticker}")
                return True
            else:
                logger.warning(f"StockAttributes not found for {ticker}, cannot save insights")
                return False

    except Exception as e:
        logger.error(f"Error saving insights for {ticker}: {e}")
        return False


def get_insights(ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Get insights for a stock, fetching from LLM if stale or missing.

    Args:
        ticker: Stock ticker symbol
        force_refresh: If True, fetch fresh insights regardless of staleness

    Returns:
        Dictionary with:
        - ticker: Stock symbol
        - insights: Dict with going_right/going_wrong lists (or None if unavailable)
        - updated_at: Timestamp string or None
        - is_stale: Boolean indicating if insights need refresh
        - status: 'available', 'stale', 'unavailable', or 'error'
    """
    ticker_upper = ticker.upper()

    result = {
        "ticker": ticker_upper,
        "insights": None,
        "updated_at": None,
        "is_stale": True,
        "status": "unavailable"
    }

    try:
        with Session(engine) as session:
            statement = select(StockAttributes).where(StockAttributes.ticker == ticker_upper)
            stock_attr = session.exec(statement).first()

            if stock_attr and stock_attr.insights_json and not force_refresh:
                # We have cached insights
                stale = is_insights_stale(stock_attr.insights_updated_at)

                try:
                    insights = json.loads(stock_attr.insights_json)
                    result["insights"] = insights
                    result["updated_at"] = stock_attr.insights_updated_at.isoformat() if stock_attr.insights_updated_at else None
                    result["is_stale"] = stale
                    result["status"] = "stale" if stale else "available"

                    # If not stale, return cached insights
                    if not stale:
                        return result

                except json.JSONDecodeError:
                    logger.error(f"Failed to parse cached insights for {ticker_upper}")

            # Need to fetch fresh insights (either missing, stale, or force_refresh)
            # Check if the configured provider has an API key
            if LLM_PROVIDER == "gemini" and not GOOGLE_AI_API_KEY:
                result["status"] = "unavailable"
                result["error"] = "GOOGLE_AI_API_KEY not configured"
                return result
            elif LLM_PROVIDER != "gemini" and not GROQ_API_KEY:
                result["status"] = "unavailable"
                result["error"] = "GROQ_API_KEY not configured"
                return result

            # Fetch from LLM
            insights = fetch_insights_from_llm(ticker_upper)

            if insights:
                # Save to database
                save_insights(ticker_upper, insights)

                result["insights"] = insights
                result["updated_at"] = datetime.utcnow().isoformat()
                result["is_stale"] = False
                result["status"] = "available"
            else:
                # LLM fetch failed - return cached if available
                if result["insights"]:
                    result["status"] = "stale"
                else:
                    result["status"] = "error"
                    result["error"] = "Failed to fetch insights"

    except Exception as e:
        logger.error(f"Error getting insights for {ticker_upper}: {e}")
        result["status"] = "error"
        result["error"] = str(e)

    return result


def refresh_insights_for_watchlist_tickers() -> Dict[str, int]:
    """
    Refresh insights for all unique tickers across all watchlists.
    Called by the scheduler.

    Returns:
        Dictionary with counts: {'success': N, 'failed': N, 'skipped': N}
    """
    from app.models.watchlist import WatchListStock

    results = {"success": 0, "failed": 0, "skipped": 0}

    # Check if the configured provider has an API key
    if LLM_PROVIDER == "gemini" and not GOOGLE_AI_API_KEY:
        logger.warning("GOOGLE_AI_API_KEY not configured, skipping insights refresh")
        return results
    elif LLM_PROVIDER != "gemini" and not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not configured, skipping insights refresh")
        return results

    try:
        with Session(engine) as session:
            # Get all unique tickers from watchlists
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()

            logger.info(f"Refreshing insights for {len(tickers)} tickers")

            for ticker in tickers:
                try:
                    # Check if insights are stale
                    attr_stmt = select(StockAttributes).where(StockAttributes.ticker == ticker.upper())
                    stock_attr = session.exec(attr_stmt).first()

                    if stock_attr and not is_insights_stale(stock_attr.insights_updated_at):
                        results["skipped"] += 1
                        continue

                    # Fetch fresh insights
                    insights = fetch_insights_from_llm(ticker)

                    if insights:
                        save_insights(ticker, insights)
                        results["success"] += 1
                    else:
                        results["failed"] += 1

                except Exception as e:
                    logger.error(f"Error refreshing insights for {ticker}: {e}")
                    results["failed"] += 1

    except Exception as e:
        logger.error(f"Error in refresh_insights_for_watchlist_tickers: {e}")

    logger.info(f"Insights refresh complete: {results}")
    return results
