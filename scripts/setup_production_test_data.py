"""Setup test data for production test account (arthos.test@gmail.com).

This script creates sample watchlists and data for the test account in production.
Run this once after creating the test account to populate it with test data.

Usage:
    # Set production database URL
    export DATABASE_URL=<production-postgresql-url>
    python scripts/setup_production_test_data.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from app.database import engine
from app.models.account import Account
from app.models.watchlist import WatchList, WatchListStock
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist
from uuid import uuid4
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_EMAIL = "arthos.test@gmail.com"


def get_or_create_test_account() -> str:
    """Get or create the test account in production database.

    Returns:
        str: Account ID of the test account
    """
    with Session(engine) as session:
        # Check if account exists
        statement = select(Account).where(Account.email == TEST_EMAIL)
        account = session.exec(statement).first()

        if account:
            logger.info(f"Found existing test account: {account.id}")
            return account.id

        # Create account (this will happen after first OAuth login)
        logger.warning(
            f"Account {TEST_EMAIL} not found in database. "
            "Please log in once via browser first to create the account."
        )
        sys.exit(1)


def setup_test_watchlists(account_id: str):
    """Create sample watchlists for testing.

    Args:
        account_id: The test account ID
    """
    logger.info("Creating test watchlists...")

    # Create a few test watchlists
    watchlists_data = [
        {
            "name": "Tech Stocks",
            "description": "Test watchlist for technology companies",
            "tickers": ["AAPL", "MSFT", "GOOGL"],
        },
        {
            "name": "Dividend Stocks",
            "description": "Test watchlist for dividend-paying stocks",
            "tickers": ["JNJ", "PG", "KO"],
        },
        {
            "name": "Growth Stocks",
            "description": "Test watchlist for high-growth companies",
            "tickers": ["NVDA", "TSLA", "AMD"],
        },
    ]

    for wl_data in watchlists_data:
        try:
            # Check if watchlist already exists
            with Session(engine) as session:
                statement = select(WatchList).where(
                    WatchList.watchlist_name == wl_data["name"],
                    WatchList.account_id == account_id
                )
                existing = session.exec(statement).first()

                if existing:
                    logger.info(f"Watchlist '{wl_data['name']}' already exists, skipping")
                    continue

            # Create watchlist
            watchlist = create_watchlist(
                watchlist_name=wl_data["name"],
                account_id=account_id,
                description=wl_data["description"]
            )
            logger.info(f"Created watchlist: {wl_data['name']} ({watchlist.watchlist_id})")

            # Add stocks (note: this will trigger stock data fetch in production)
            added, invalid = add_stocks_to_watchlist(
                watchlist.watchlist_id,
                wl_data["tickers"],
                account_id=account_id
            )
            logger.info(f"  Added {len(added)} stocks: {added}")
            if invalid:
                logger.warning(f"  Invalid tickers: {invalid}")

        except Exception as e:
            logger.error(f"Error creating watchlist '{wl_data['name']}': {e}")


def cleanup_test_data(account_id: str):
    """Clean up all test data for the account.

    Args:
        account_id: The test account ID
    """
    logger.info("Cleaning up test data...")

    with Session(engine) as session:
        # Delete all watchlists for this account
        statement = select(WatchList).where(WatchList.account_id == account_id)
        watchlists = session.exec(statement).all()

        for watchlist in watchlists:
            # Delete stocks first (foreign key)
            stock_statement = select(WatchListStock).where(
                WatchListStock.watchlist_id == watchlist.watchlist_id
            )
            stocks = session.exec(stock_statement).all()
            for stock in stocks:
                session.delete(stock)

            # Delete watchlist
            session.delete(watchlist)
            logger.info(f"Deleted watchlist: {watchlist.watchlist_name}")

        session.commit()
        logger.info("Cleanup complete")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Setup production test data")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up test data instead of creating it"
    )
    args = parser.parse_args()

    # Verify we're connected to a database
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)

    # Warn if not production
    if "railway" not in db_url.lower() and "my.arthos.app" not in db_url.lower():
        logger.warning("WARNING: Not connected to production database!")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            sys.exit(0)

    # Get test account
    account_id = get_or_create_test_account()

    if args.cleanup:
        cleanup_test_data(account_id)
    else:
        setup_test_watchlists(account_id)

    logger.info("Done!")


if __name__ == "__main__":
    main()
