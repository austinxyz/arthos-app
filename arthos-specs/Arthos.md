This document describes the user scenarios, models and business logic that supports the user scenarios for Arthos app.

### Models
#### stock_attributes

This table captures the key information for each stock that is added to any watchlist.

- ticker - 8 character alphabetical string that represents a stock in the exchange e.g., AAPL, TSLA. This is the primary key for the table.
- date_added - timestamp when the entry was created.
- date_modified - timestamp when the entry was last updated. All updates to the row should update this field to the current time stamp.
- dividend_amt - Annual dividend amount paid out by this stock. It should be most recent quarterly dividend amount multiplied by 4.
- divident_yield - dividend amount divided by the stock price when the row was created or updated.
- next_earnings_date - date for the next earnings date for the stock.
- is_next_earnings_date_estimate - boolean field, if the next_earnings_date is an estimate and not confirmed.

#### stock_price

