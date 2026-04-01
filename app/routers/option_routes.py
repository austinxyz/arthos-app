"""Router for individual option quote lookups."""
import logging
from fastapi import APIRouter, HTTPException, Path

from app.utils.option_symbol import parse_option_symbol
from app.services.option_quote_service import get_option_quote
from app.providers.exceptions import DataNotAvailableError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/optionquote/{option_symbol}")
async def option_quote(option_symbol: str = Path(..., description="OCC option symbol, e.g. NFLX281215P00105000")):
    """
    Fetch a single option quote by OCC symbol.

    Returns bid, ask, mid, last price, IV, and Greeks (when available).
    Data is cached for 20 minutes. Past expirations return 404.
    """
    try:
        parsed = parse_option_symbol(option_symbol)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        result = get_option_quote(parsed)
    except DataNotAvailableError as e:
        logger.error(f"Provider error fetching option quote for {option_symbol}: {e}")
        raise HTTPException(status_code=503, detail="Option quote data unavailable")

    if result is None:
        raise HTTPException(status_code=404, detail=f"Option quote not found: {option_symbol}")

    return result
