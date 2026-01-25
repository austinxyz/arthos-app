# Algorithms for different types of option trades

Option trades are all based on Option quotes fetched from yFinance in our code. We are usually interested in Calls and Puts with in 30% of the current stock price i.e., if
the stock price is $100, we are usually interested in puts and calls between $70 and $130.
These quotes are across various durations.

### Covered Call Strategy
In the covered call strategy, we buy the stock and sell a call option at a strike price. This strike price is usually above the current stock price and sometimes, it may be below.
We want to target expirations that have higher implied volatility, usually around earnings announcement, annual shareholder meetings, product launches etc., Our goal is to find opportunities where the volatility is high, so the call premiums are high (since we are selling).

Implement a new tab under stock details page and write a new algorithm for covered calls. Call this tab - CC (New). Once we perfect it, we will remove the existing Covered Calls tab.

Walk through Option quotes for the stock for the next 3 months.
Call Premium is calculated by the average of bid and ask prices for the strike price.
Focus on premiums where:
- Call Premium is > 1% of the current stock price (strictly greater than, not equal to)
- Strike price is >= current stock price (only ATM and OTM calls, exclude ITM calls)

Calculate returns in two scenarios -
1. Call exercised - Return is (strike price + call premium - current stock price). Return % is divide the Return by current stock price.
2. Call Not exercised - Return is call premium. Return % is divide by the current stock price.

For both scenarios, calculate the annualized return = (return % *365) / (days from today to expiration)

Rank the results where returns for exercise and does not exercise are roughly equal (within 2% difference) followed by annualized return descending.

**Implementation Details:**
- Use calendar days for annualized return calculations
- Premium threshold is hard-coded at 1% of current stock price
- Return visualization bars use fixed width of 250px

The user interface should have the following table columns
1. Expiration Date
2. Strike Price
3. Call Premium
4. Return if exercised and % Return and with a line break specify Annualized Return
5. Return if not exercised and % Return and with a line break specify annualized Return
6. Return Visualization
    - Blue bar: Stock appreciation percentage (for OTM calls)
    - Green bar: Call premium percentage
    - Red bar: Negative stock appreciation (for ITM calls)

#### Implement Test coverage for this using PlayWright for all user interactions and user interface elements and unit test cases with mock data for the algorithm.

## Dumbell Charts for Covered Calls
We need to add a visualization above the table for covered calls. 
Please create a "Dumbbell Plot" (also known as a Connected Dot Plot) to visualize the spread between "Return if Exercised" vs "Return if Not Exercised".
We will use the Dumbell Charts from Highcharts library to implement this.

Here are the specific requirements for the implementation:

1. **Data Structure:**
   The input will be a list of records containing: 'Expiration Date', 'Strike Price', 'Return if Exercised (%)', and 'Return if Not Exercised (%)'.

2. **Visual Layout:**
   - **Y-Axis:** List the contracts (labeled as "Date - $Strike").
   - **X-Axis:** The Return percentage.
   - **Plot Style:** For each contract, plot two distinct markers on the same horizontal line:
     - One marker for the "Exercised" return.
     - One marker for the "Not Exercised" return.
     - Connect these two markers with a horizontal line (to visualize the spread).
   - **Colors:** Use distinct colors for the two scenarios (e.g., Green for Exercised, Blue for Not Exercised).

3. **Grid & Ticks Configuration (Crucial):**
   - The X-axis must show **major grid lines at exactly 0.2% increments** (e.g., 2.0%, 2.2%, 2.4%).
   - Enable **minor ticks** on the X-axis between the major grid lines for precision.
   - Ensure the grid lines are visible but subtle (e.g., light gray dashed lines) so they don't overpower the data.

