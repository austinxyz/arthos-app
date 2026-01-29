# Risk Reversal Strategy (RRR)

A risk reversal strategy bets that a stock will reverse direction and appreciate in price. The strategy involves selling a put to finance the purchase of calls, creating a leveraged bullish position with minimal or zero out-of-pocket cost.

## Core Strategy

1. **Sell a Put** - Collect premium to finance the trade
2. **Buy Call(s)** - Capture upside price appreciation
3. **Optionally Sell OTM Call** - (Collar variant) Cap gains in exchange for reduced cost

## Option Selection Rules

### Expiration
- Only LEAPS options expiring in **January of next year or later**

### Strike Price Ranges
- **Put strikes**: 90% to 130% of current stock price (10% below to 30% above)
- **Call strikes**: At or above the put strike price

### Pricing
- Always use the **average of bid and ask prices** (mid-price)
- Filter out any options with missing or zero bid/ask quotes

## Strategy Types

### 1:1 Ratio
- Sell 1 put, buy 1 call
- Most straightforward structure
- Works best when put and call can be at similar strikes

### 1:2 Ratio
- Sell 1 put, buy 2 calls
- Provides more upside leverage
- May require higher put strike to collect enough premium to finance 2 calls. Identify the strike price where selling one put can let us buy 2 calls at the same strike price with a net cost of less than 3% of the current stock price. From this pivot point, expand the search by 10% above and below the put strike price to find other combinations.

### 1:3 Ratio
- Sell 1 put, buy 3 calls
- Provides even more upside leverage
- May require higher put strike to collect enough premium to finance 3 calls. Identify the strike price where selling one put can let us buy 2 calls at the same strike price with a net cost of less than 5% of the current stock price. From this pivot point, expand the search by 10% above and below the put strike price to find other combinations.

### Collar
- Sell 1 put + buy call(s) + **sell OTM call**
- The sold call must be at least **30% higher** than the bought call strike
- Caps maximum profit at the sold call strike
- Reduces net cost, useful in high volatility environments
- Available in both 1:1 and 1:2 configurations

## Cost Constraints

- **Net cost must be within ±3% of current stock price**
- Negative cost (credit) is preferred
- Zero cost is ideal

## Sorting Priority

Strategies are ranked by:
1. **Put strike proximity** to current stock price (closest first)
2. **Call strike proximity** to put strike (closest first)
3. **Net cost** closest to $0

## Example

For AAPL at $100:

| Type | Structure | Example |
|------|-----------|---------|
| 1:1 | Sell $100 put, Buy $100 call | Net cost: $1.50 |
| 1:2 | Sell $120 put, Buy 2× $120 calls | Net cost: $2.25 |
| Collar | Sell $100 put, Buy 2× $120 calls, Sell 2× $180 calls | Net cost: $0.50 |

## Display

Results are shown in the **RRR tab** on the stock detail page with filters for:
- 1:1
- 1:2
- 1:3
- Collar
- All

Each strategy displays:
- Put/Call strikes and premiums
- Breakeven prices
- Strike spread
- Net cost ($ and %)
- Days to expiration
- Put risk (max loss if assigned)
