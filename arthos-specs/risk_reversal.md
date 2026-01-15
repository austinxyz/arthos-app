# Risk Reversal Strategy Rewrite (RRR)

At the core a risk reversal strategy is betting the stock will reverse in direction
and go up in price. We invest into this strategy by

- We should only look at leaps that expire in following year Jan or later.
- Selling a Put at a strike price close to or slightly higher than the current stock price that provides the capital for the trade.
- Buying a call at a strike price close to or slightly higher than the put strike price to capture the price appreciation in stock.
- The put and call ratios can be 1:1, 1:2 or 1:3. We will always fix the put at 1 and vary the number of calls.
- The goal of this strategy is to
    - Make the put price as close to current stock price as possible
    - Make the call price as close to put price as possible
    - Make the net cost of the trade as close to zero as possible and not more than 3% of the current stock price
- For ratios higher than 1:1 i.e., 1:2 and 1:3, we may have to look at higher put strike prices to collect more premium to finance our calls.
- Sometimes if the volatility is very high, we can sell an out of the money call to add more capital to finance the trade 
    - e.g., lets say AAPL stock price is $100
    - We can find a risk reversal of 1:1 by selling Jan 2027 $100 put and buying a $100 call for $1.50
    - In order to find a 1:2 strategy, we may have to sell $120 put to purchase 2 x $120 calls for $2.25.
    - Another option could be sell $100 put, buy 2 x $120 call and sell 2 x $180 call for a total price of $2.50.

For option quotes, always use the average of bid and ask prices. If the prices do not exist for some reason, filter out those strike prices.