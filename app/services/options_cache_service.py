"""Options data caching service to reduce API calls."""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from threading import Lock

logger = logging.getLogger(__name__)

# In-memory cache with TTL
_options_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = Lock()

# Cache TTL settings
CACHE_TTL_MINUTES = 15  # Options data is cached for 15 minutes during market hours
CACHE_TTL_AFTER_HOURS_MINUTES = 60  # Cache longer after market hours


def _is_market_hours() -> bool:
    """Check if it's currently US market hours (9:30 AM - 4:00 PM ET)."""
    from datetime import timezone
    import pytz
    
    try:
        et = pytz.timezone('US/Eastern')
        now_et = datetime.now(et)
        
        # Check if weekend
        if now_et.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Check if during market hours
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return market_open <= now_et <= market_close
    except Exception:
        # If timezone check fails, assume market is open
        return True


def _get_cache_ttl() -> timedelta:
    """Get cache TTL based on market hours."""
    if _is_market_hours():
        return timedelta(minutes=CACHE_TTL_MINUTES)
    else:
        return timedelta(minutes=CACHE_TTL_AFTER_HOURS_MINUTES)


def get_cached_options_data(ticker: str, expiration: str) -> Optional[Tuple[str, Dict[float, Dict[str, Any]]]]:
    """
    Get options data from cache if available and not expired.
    
    Args:
        ticker: Stock ticker symbol
        expiration: Expiration date (YYYY-MM-DD)
        
    Returns:
        Cached options data tuple (expiration, options_by_strike) or None if not cached/expired
    """
    cache_key = f"{ticker.upper()}:{expiration}"
    
    with _cache_lock:
        if cache_key in _options_cache:
            cached = _options_cache[cache_key]
            cached_at = cached.get('cached_at')
            ttl = _get_cache_ttl()
            
            if cached_at and datetime.now() - cached_at < ttl:
                logger.debug(f"Options cache hit for {cache_key}")
                return (cached.get('expiration'), cached.get('options_data'))
            else:
                # Expired, remove from cache
                del _options_cache[cache_key]
                logger.debug(f"Options cache expired for {cache_key}")
    
    return None


def cache_options_data(ticker: str, expiration: str, options_data: Dict[float, Dict[str, Any]]) -> None:
    """
    Cache options data.
    
    Args:
        ticker: Stock ticker symbol
        expiration: Expiration date
        options_data: Options data to cache
    """
    cache_key = f"{ticker.upper()}:{expiration}"
    
    with _cache_lock:
        _options_cache[cache_key] = {
            'expiration': expiration,
            'options_data': options_data,
            'cached_at': datetime.now()
        }
        logger.debug(f"Cached options data for {cache_key}")


def clear_options_cache(ticker: Optional[str] = None) -> None:
    """
    Clear options cache.
    
    Args:
        ticker: If provided, only clear cache for this ticker. Otherwise clear all.
    """
    with _cache_lock:
        if ticker:
            keys_to_remove = [k for k in _options_cache.keys() if k.startswith(f"{ticker.upper()}:")]
            for key in keys_to_remove:
                del _options_cache[key]
            logger.info(f"Cleared options cache for {ticker}")
        else:
            _options_cache.clear()
            logger.info("Cleared all options cache")


def calculate_atm_iv(options_data: Dict[float, Dict[str, Any]], current_price: float) -> Optional[float]:
    """
    Calculate ATM (at-the-money) implied volatility.
    
    Uses the average IV of the call and put options at the strike closest to current price.
    
    Args:
        options_data: Options data by strike
        current_price: Current stock price
        
    Returns:
        ATM IV as percentage, or None if not available
    """
    if not options_data or current_price <= 0:
        return None
    
    # Find the strike closest to current price
    strikes = list(options_data.keys())
    if not strikes:
        return None
    
    closest_strike = min(strikes, key=lambda s: abs(s - current_price))
    strike_data = options_data.get(closest_strike, {})
    
    # Get IVs from both call and put
    ivs = []
    
    call_data = strike_data.get('call')
    if call_data and call_data.get('impliedVolatility') is not None:
        ivs.append(call_data['impliedVolatility'])
    
    put_data = strike_data.get('put')
    if put_data and put_data.get('impliedVolatility') is not None:
        ivs.append(put_data['impliedVolatility'])
    
    if not ivs:
        return None
    
    # Return average of available IVs
    return sum(ivs) / len(ivs)


def update_stock_iv_metrics(ticker: str, current_iv: float) -> None:
    """
    Update stock attributes with IV metrics.
    
    Stores current IV and calculates IV Rank and IV Percentile based on historical data.
    
    Args:
        ticker: Stock ticker symbol
        current_iv: Current ATM implied volatility (percentage)
    """
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.stock_price import StockAttributes
    
    try:
        with Session(engine) as session:
            # Get existing attributes
            statement = select(StockAttributes).where(StockAttributes.ticker == ticker.upper())
            attributes = session.exec(statement).first()
            
            if not attributes:
                logger.warning(f"No stock attributes found for {ticker}, cannot update IV metrics")
                return
            
            # Update current IV
            attributes.current_iv = Decimal(str(round(current_iv, 4)))
            
            # Get historical IV data for IV Rank calculation
            # For now, we'll use simple logic based on existing 52w high/low
            # A more complete implementation would track daily IV history
            
            # Update 52-week high/low if needed
            if attributes.iv_high_52w is None or current_iv > float(attributes.iv_high_52w):
                attributes.iv_high_52w = Decimal(str(round(current_iv, 4)))
            
            if attributes.iv_low_52w is None or current_iv < float(attributes.iv_low_52w):
                attributes.iv_low_52w = Decimal(str(round(current_iv, 4)))
            
            # Calculate IV Rank: (Current IV - 52w Low) / (52w High - 52w Low) * 100
            if attributes.iv_high_52w is not None and attributes.iv_low_52w is not None:
                iv_high = float(attributes.iv_high_52w)
                iv_low = float(attributes.iv_low_52w)
                
                if iv_high > iv_low:
                    iv_rank = ((current_iv - iv_low) / (iv_high - iv_low)) * 100
                    attributes.iv_rank = Decimal(str(round(iv_rank, 2)))
                else:
                    attributes.iv_rank = Decimal('50.0')  # Default to 50 if no range
            
            # For IV Percentile, we'd need historical daily IV data
            # For now, use a simplified version based on IV Rank
            # In a production system, you'd track daily IV and calculate actual percentile
            if attributes.iv_rank is not None:
                # Simplified: use IV rank as approximation of percentile
                attributes.iv_percentile = attributes.iv_rank
            
            session.add(attributes)
            session.commit()
            
            logger.info(f"Updated IV metrics for {ticker}: IV={current_iv:.1f}%, IVR={attributes.iv_rank}%")
            
    except Exception as e:
        logger.error(f"Error updating IV metrics for {ticker}: {e}")
