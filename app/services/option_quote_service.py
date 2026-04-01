"""Service for fetching and caching individual option quotes."""
import logging
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Any, Optional

from app.providers.factory import ProviderFactory
from app.providers.exceptions import DataNotAvailableError
from app.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

# In-memory cache: symbol -> {data, expires_at}
_quote_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = Lock()

CACHE_TTL_MINUTES = 20


def _round2(value: Optional[float]) -> Optional[float]:
    """Round to 2 decimal places, or return None."""
    return round(value, 2) if value is not None else None


def _build_response(quote, provider_name: str) -> Dict[str, Any]:
    """Serialize an OptionQuote into the API response dict."""
    bid = _round2(quote.bid)
    ask = _round2(quote.ask)
    mid = _round2((bid + ask) / 2) if bid is not None and ask is not None else None

    return {
        "symbol": quote.contract_symbol,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last_price": _round2(quote.last_price),
        "strike": _round2(quote.strike),
        "volume": quote.volume,
        "open_interest": quote.open_interest,
        "implied_volatility": _round2(quote.implied_volatility),
        "greeks": {
            "delta": quote.delta,
            "gamma": quote.gamma,
            "theta": quote.theta,
            "vega": quote.vega,
            "rho": quote.rho,
        },
        "provider": provider_name,
    }


def get_option_quote(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Fetch a single option quote, with a 20-minute in-memory cache.

    Args:
        parsed: Output of parse_option_symbol() — contains normalized_symbol,
                ticker, expiration, option_type, strike.

    Returns:
        Response dict ready to return from the API endpoint, or None if the
        provider returned no data for this symbol.

    Raises:
        DataNotAvailableError: If the provider hits a rate limit and the
            yfinance fallback also fails.
    """
    symbol = parsed["normalized_symbol"]

    # Check cache
    with _cache_lock:
        cached = _quote_cache.get(symbol)
        if cached and cached["expires_at"] > datetime.utcnow():
            logger.debug(f"Cache hit for option quote {symbol}")
            return cached["data"]

    # Fetch from provider
    provider = ProviderFactory.get_options_provider()
    provider_name = provider.get_provider_name()

    quote = None
    try:
        quote = provider.fetch_option_quote(symbol)
    except DataNotAvailableError as e:
        if "rate limit" in str(e).lower():
            logger.warning(
                f"MarketData rate limit hit fetching option quote for {symbol}; "
                "falling back to yfinance (Greeks will not be available)"
            )
            yf_provider = YFinanceProvider()
            quote = yf_provider.fetch_option_quote(symbol)
            provider_name = yf_provider.get_provider_name()
        else:
            raise

    if quote is None:
        return None

    result = _build_response(quote, provider_name)

    # Store in cache
    with _cache_lock:
        _quote_cache[symbol] = {
            "data": result,
            "expires_at": datetime.utcnow() + timedelta(minutes=CACHE_TTL_MINUTES),
        }

    return result
