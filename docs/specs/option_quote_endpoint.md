# Spec: `/v1/optionquotes/{option_symbol}` Endpoint

## Overview

Add a new REST API endpoint that accepts a single OCC option symbol, validates it, fetches the option quote, and returns a structured JSON response. This enables callers to retrieve real-time bid/ask/last prices and Greeks for any individual option contract by its standardized symbol.

---

## OCC Symbol Format

The [Options Clearing Corporation (OCC)](https://www.theocc.com/) defines the canonical option symbol format used universally across brokers and data providers:

```
{TICKER}{YYMMDD}{TYPE}{STRIKE}
```

| Field    | Length   | Description                                     | Example       |
|----------|----------|-------------------------------------------------|---------------|
| TICKER   | 1–6 chars| Uppercase letters, the underlying stock symbol  | `NFLX`        |
| YYMMDD   | 6 digits | Expiration date: year/month/day                 | `281215`      |
| TYPE     | 1 char   | `C` (call) or `P` (put)                         | `P`           |
| STRIKE   | 8 digits | Strike price × 1000, zero-padded                | `00105000`    |

**Full example:** `NFLX281215P00105000`
- Underlying: NFLX
- Expiration: 2028-12-15
- Type: Put
- Strike: 00105000 → $105.00

**Validation regex:** `^([A-Z]{1,6})(\d{6})([CP])(\d{8})$`

Additional validation (applied after regex match):
- Expiration date must be a valid calendar date (e.g., day ≤ 28/30/31 depending on month)
- Strike must be > 0

---

## API Contract

### Request

```
GET /v1/optionquotes/{option_symbol}
```

**Path parameter:** `option_symbol` — OCC-format option symbol (case-insensitive; normalized to uppercase internally).

**No authentication required** (consistent with other `/v1/` endpoints).

### Response — 200 OK

```json
{
  "symbol": "NFLX281215P00105000",
  "underlying": "NFLX",
  "expiration": "2028-12-15",
  "option_type": "put",
  "strike": 105.0,
  "bid": 2.50,
  "ask": 2.70,
  "mid": 2.60,
  "last_price": 2.55,
  "volume": 312,
  "open_interest": 1540,
  "implied_volatility": 34.5,
  "greeks": {
    "delta": -0.23,
    "gamma": 0.011,
    "theta": -0.04,
    "vega": 0.18,
    "rho": -0.07
  },
  "provider": "MarketData.app"
}
```

- `mid` is computed as `(bid + ask) / 2` when both are present, otherwise `null`.
- `greeks` values are `null` when not provided by the active data provider (yfinance does not supply Greeks).
- `provider` is informational only — indicates which data source fulfilled the request.

### Error Responses

| HTTP Status | `detail` value                                | When                                               |
|-------------|-----------------------------------------------|----------------------------------------------------|
| 422         | `"Invalid option symbol format: {symbol}"`    | Fails OCC regex or date/strike validation          |
| 404         | `"Option quote not found: {symbol}"`          | Provider returned no data for the symbol           |
| 503         | `"Option quote data unavailable"`             | Provider error or rate limit exhausted with no fallback |

---

## Implementation Plan

### Step 1 — OCC Symbol Parser/Validator

**New file:** `app/utils/option_symbol.py`

Add a `parse_option_symbol(symbol: str) -> dict` function that:
1. Strips whitespace and uppercases the input.
2. Applies the regex `^([A-Z]{1,6})(\d{6})([CP])(\d{8})$`.
3. Parses the date group as `datetime.strptime(yymmdd, "%y%m%d")` — raises `ValueError` on invalid dates (e.g., `990231`).
4. Converts the strike group to a float: `int(strike_str) / 1000`.
5. Raises `ValueError` with a descriptive message on any failure.
6. Returns a dict with keys: `ticker`, `expiration` (as `datetime.date`), `option_type` (`"call"` or `"put"`), `strike` (float), `normalized_symbol` (uppercase original).

### Step 2 — Abstract Base Class Extension

**File:** `app/providers/base.py`

Add `fetch_option_quote` as an abstract method on `StockDataProvider`:

```python
@abstractmethod
def fetch_option_quote(self, option_symbol: str) -> Optional[OptionQuote]:
    """
    Fetch a single option quote by OCC symbol.
    Returns None if not found or not supported.
    """
    pass
```

This keeps provider implementations consistent and allows the service layer to call the method on any provider without `isinstance` checks.

### Step 3 — YFinance Provider Fallback Implementation

**File:** `app/providers/yfinance_provider.py`

Implement `fetch_option_quote` for yfinance. Since yfinance does not have a single-contract endpoint, the method will:
1. Parse ticker and expiration from the symbol.
2. Call `fetch_options_chain(ticker, expiration)`.
3. Search the returned calls or puts list for a contract whose `contract_symbol` matches the requested symbol.
4. Return the matching `OptionQuote` or `None` if not found.

**Trade-off:** This fetches the full chain to find one contract. Acceptable as a best-effort fallback; Greeks will be `None` since yfinance does not provide them.

### Step 4 — New Router

**New file:** `app/routers/option_routes.py`

```python
from fastapi import APIRouter, HTTPException, Path
from app.utils.option_symbol import parse_option_symbol
from app.services.option_quote_service import get_option_quote

router = APIRouter()

@router.get("/v1/optionquotes/{option_symbol}")
async def option_quote(option_symbol: str = Path(...)):
    try:
        parsed = parse_option_symbol(option_symbol)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid option symbol format: {e}")

    result = await get_option_quote(parsed["normalized_symbol"])
    if result is None:
        raise HTTPException(status_code=404, detail=f"Option quote not found: {option_symbol}")
    return result
```

### Step 5 — New Service

**New file:** `app/services/option_quote_service.py`

```python
async def get_option_quote(option_symbol: str) -> Optional[dict]:
    """
    Fetch a single option quote.
    Uses options provider (MarketData if configured, else yfinance).
    Returns None if quote not found.
    """
```

Responsibilities:
1. Call `ProviderFactory.get_options_provider()` to get the active provider.
2. Call `provider.fetch_option_quote(option_symbol)`.
3. On `DataNotAvailableError` with a rate-limit message, raise `HTTPException(503)`.
4. If the result is an `OptionQuote`, serialize it to the response dict (compute `mid`, include `greeks`, set `provider` name).
5. Return `None` if the provider returned `None` (triggers 404 in the router).

### Step 6 — Register Router in `main.py`

**File:** `app/main.py`

```python
from app.routers import option_routes
app.include_router(option_routes.router)
```

---

## Provider Behavior Matrix

| Scenario                                | Provider Used        | Greeks Available | Notes                                 |
|-----------------------------------------|----------------------|------------------|---------------------------------------|
| `MARKETDATA_API_KEY` set, within limits | MarketData.app       | Yes              | Direct `/options/quotes/{symbol}/`    |
| `MARKETDATA_API_KEY` set, rate limited  | yfinance (fallback)  | No               | Fetches full chain, finds contract    |
| `MARKETDATA_API_KEY` not set            | yfinance             | No               | Fetches full chain, finds contract    |

---

## File Change Summary

| File                                      | Action | Reason                                              |
|-------------------------------------------|--------|-----------------------------------------------------|
| `app/utils/option_symbol.py`              | New    | OCC symbol parser/validator                         |
| `app/providers/base.py`                   | Edit   | Add `fetch_option_quote` abstract method            |
| `app/providers/marketdata_provider.py`    | None   | Already implements `fetch_option_quote`             |
| `app/providers/yfinance_provider.py`      | Edit   | Implement `fetch_option_quote` via chain lookup     |
| `app/services/option_quote_service.py`    | New    | Orchestration: provider call + response shaping     |
| `app/routers/option_routes.py`            | New    | Route handler + validation                          |
| `app/main.py`                             | Edit   | Register new router                                 |

---

## Testing Plan

### Unit Tests (`tests/test_option_symbol.py`)
- Valid symbols parse correctly (varied ticker lengths, calls and puts).
- Invalid format (bad regex) raises `ValueError`.
- Invalid date (e.g., Feb 30) raises `ValueError`.
- Zero strike raises `ValueError`.
- Case normalization: `nflx281215p00105000` → `NFLX281215P00105000`.

### Integration Tests (`tests/test_option_quote_api.py`)
- Mock provider returns a populated `OptionQuote` → response is 200 with all fields.
- Mock provider returns `None` → 404.
- Provider raises `DataNotAvailableError("rate limit")` → 503.
- Bad symbol in URL → 422 with descriptive detail.
- `mid` computation: present when bid+ask both non-null, null otherwise.
- `greeks` block is all-null when provider returns no Greeks (yfinance path).

### Browser Tests
Not required — this is a backend-only JSON API endpoint with no UI changes.

---

## Open Questions (for review)

1. **Caching:** Should single option quotes be cached (like chain data is)? MarketData free tier has 100 calls/day. Recommend a short TTL (e.g., 60 seconds) to reduce load, but this needs a decision.
2. **Expiration in the past:** Should we validate that the parsed expiration date is not in the past? Expired options can still have quotes in some providers. Recommend allowing it (let the provider return 404 naturally).
3. **`mid` rounding:** How many decimal places for `mid`? Suggest 2 (consistent with `bid`/`ask`).
4. **Rate limit fallback for yfinance:** On MarketData rate limit, the yfinance fallback fetches the full chain. Should we log a warning when this happens? Recommend yes (already done in `rr_routes.py`).
