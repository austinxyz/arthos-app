"""OCC option symbol parser and validator."""
import re
from datetime import date, datetime
from typing import Dict, Any

# OCC format: {TICKER}{YYMMDD}{C|P}{STRIKE8}
# Example: NFLX281215P00105000
_OCC_PATTERN = re.compile(r'^([A-Z]{1,6})(\d{6})([CP])(\d{8})$')


def parse_option_symbol(symbol: str) -> Dict[str, Any]:
    """
    Parse and validate an OCC option symbol.

    Args:
        symbol: OCC option symbol, e.g. 'NFLX281215P00105000'. Case-insensitive.

    Returns:
        Dict with keys:
            normalized_symbol (str): uppercased original symbol
            ticker (str): underlying ticker
            expiration (date): expiration date
            option_type (str): 'call' or 'put'
            strike (float): strike price

    Raises:
        ValueError: if the symbol is malformed, has an invalid date, zero strike,
                    or an expiration in the past.
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Option symbol must be a non-empty string")

    normalized = symbol.strip().upper()

    m = _OCC_PATTERN.match(normalized)
    if not m:
        raise ValueError(
            f"'{symbol}' does not match OCC format TICKER(1-6)+YYMMDD+C/P+8-digit-strike "
            f"(e.g. NFLX281215P00105000)"
        )

    ticker, yymmdd, cp, strike_str = m.groups()

    # Parse expiration date — raises ValueError on invalid calendar date
    try:
        expiration = datetime.strptime(yymmdd, "%y%m%d").date()
    except ValueError:
        raise ValueError(f"'{yymmdd}' is not a valid date in YYMMDD format")

    # Reject past expirations
    if expiration < date.today():
        raise ValueError(f"Option expiration {expiration} is in the past")

    # Parse strike
    strike = int(strike_str) / 1000.0
    if strike <= 0:
        raise ValueError(f"Strike price must be greater than zero, got {strike}")

    return {
        "normalized_symbol": normalized,
        "ticker": ticker,
        "expiration": expiration,
        "option_type": "call" if cp == "C" else "put",
        "strike": strike,
    }
