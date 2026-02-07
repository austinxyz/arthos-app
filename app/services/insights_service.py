"""LLM-powered stock insights service."""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlmodel import Session, select

from app.database import engine
from app.models.stock_price import StockAttributes
from app.providers.llm import LLMProviderFactory

logger = logging.getLogger(__name__)

# Configuration
INSIGHTS_STALE_HOURS = 24

# LLM Prompt template
INSIGHTS_PROMPT = """Role: Act as a Senior Equity Research Analyst with a focus on deep fundamental valuation and strategic capital allocation.

Task: Conduct a comprehensive, multi-layered investment analysis of {ticker}. The goal is to determine if the current stock price represents a fundamental opportunity or a "value trap."

Please structure the analysis into the following 6 distinct sections:

1. The Strategic Narrative & Pivot

What is the core story management is selling right now? (e.g., Transition to AI, shifting from license to SaaS, etc.).

Requirement: Include specific quotes or stated goals from recent earnings calls or analyst days (CEO/CTO) that validate this strategy.

Are they a "First Mover" or a "Late Mover" playing catch-up?

2. Fundamental "Health Check" (The Numbers)

Revenue Mix: Break down the quality of revenue (Recurring vs. One-time). Is the "growth" segment actually moving the needle?

DuPont Analysis: Break down their ROE (Return on Equity). Is it driven by high margins, asset efficiency, or just massive leverage (Debt)?

Capital Intensity: Calculate the "Capex/Revenue" ratio. Are they burning cash to buy growth? How does this compare to their historical average?

3. The Debt & Cash Flow Stress Test

Leverage: What is their Debt-to-EBITDA ratio? Is it dangerously high (>3x)?

Maturity Profile: Do they have a "wall of debt" coming due in the next 2-3 years?

Cash Flow Dynamics: Analyze the trend of Free Cash Flow over the last 4 quarters. Are they funding operations from cash flow or by issuing new debt/equity?

4. Anatomy of Recent Price Action

The stock has moved significantly recently. Dissect why beyond the headlines.

Was the move driven by a "valuation reset" (multiple compression), a fundamental broken promise (earnings miss), or macro factors?

Identify key technical support/resistance levels that matter right now.

5. Future Pathways & Watchlist

Bull Case: What must go right for the stock to double?

Bear Case: What is the specific "failure mode"? (e.g., AI adoption slows, margins compress).

Leading Indicators: Give me 2-3 specific metrics to watch in the next earnings report (e.g., RPO conversion, Gross Margin stability) that will signal which scenario is playing out.

6. The Investment Verdict

Synthesize the above into a clear stance: Buy, Sell, or Wait?

Provide a "Buy Zone" price level where the risk/reward becomes favorable.

Format the response using Markdown with clear section headers (## for each section)."""


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
    Parse LLM response text into insights dictionary.

    Args:
        response_text: Raw text response from LLM (markdown format)
        ticker: Stock ticker symbol (for logging)

    Returns:
        Dictionary with 'analysis' key containing the markdown text, or None on failure
    """
    if not response_text or not response_text.strip():
        logger.error(f"Empty LLM response for {ticker}")
        return None

    text = response_text.strip()

    # Basic validation - check for expected section headers
    expected_sections = ["Strategic Narrative", "Fundamental", "Debt", "Price Action", "Future", "Verdict"]
    found_sections = sum(1 for section in expected_sections if section.lower() in text.lower())

    if found_sections < 3:
        logger.warning(f"LLM response for {ticker} may be incomplete (found {found_sections}/6 expected sections)")

    return {"analysis": text}


def fetch_insights_from_llm(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch insights from the active LLM provider (OpenRouter) for a given ticker.

    The model is configured via the database (admin debug page).

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dictionary with 'analysis' key containing markdown text, or None on failure
    """
    prompt = INSIGHTS_PROMPT.format(ticker=ticker.upper())

    # Get the configured LLM provider
    provider = LLMProviderFactory.get_default_provider()

    if not provider.is_configured():
        logger.error(f"{provider.get_provider_name()} is not configured (missing API key)")
        return None

    logger.info(f"Fetching insights for {ticker} using {provider.get_provider_name()} ({provider.get_model_name()})")

    response_text = provider.generate(prompt)

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
        - insights: Dict with 'analysis' key containing markdown text (or None if unavailable)
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
            # Check if the provider is configured
            provider = LLMProviderFactory.get_default_provider()
            if not provider.is_configured():
                result["status"] = "unavailable"
                result["error"] = f"{provider.get_provider_name()} API key not configured"
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

    # Check if the provider is configured
    provider = LLMProviderFactory.get_default_provider()
    if not provider.is_configured():
        logger.warning(f"{provider.get_provider_name()} not configured, skipping insights refresh")
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
