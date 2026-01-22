# Few enhancements to watchlist function

## Public Watchlists
We should have a public watchlists section where users can view watchlists created by other users. 
Each watchlist has a toggle option to make it public or private. The default is private.
A Watchlist can be toggled to public or private by the account owner at any time.

All public watchlists should be visible to all users in the public watchlists section.

### UI Changes
- Add a new page `/public-watchlists` that displays all public watchlists.
- Add a toggle option to each watchlist in the watchlist details page to make it public or private.
- Add a toggle option to each watchlist in the watchlist table to make it public or private.
- Add a link to the homepage to navigate to the public watchlists page.

## Public Watchlists Page
- Display all public watchlists in a table.
- Each row should display the watchlist name, description, and the number of stocks in the watchlist.
- Each row should have a button to view the watchlist details.
- Each row should display the owner of the watchlist.

### Watchlist Details Page
- When a stock is added to the watch list, we capture the entry price for the stock which is the current price when added
- When displaying the watchlist, each row should display the absolute change and % change from the enty price.
- The changes positive or negative should be indicated by color green or red respectively using the common standard css we created for price and percentage changes.
- The change and percentage change columns should be sortable in the table.

### One time script for all existing watchlists
- We need to run a one time script to update all existing watchlists to have the entry price as closing price on the day it was added. We should have the data in the stock_history table for this.

### Enhance the Playwright tests
- Update existing test cases to work with the new features.
    - private and public toggle option
    - Change and % change columns should be sortable in the table.
    - All watchlists should be displaying the change and % change from the entry price.
- Add new test cases for the new features to display public watchlists and their details.
- Simplify and prune redundant and unneccessary test cases.