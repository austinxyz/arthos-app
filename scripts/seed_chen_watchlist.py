"""
One-time script: create "Chen Stock Picks" watchlist and populate it.
Run from project root:
    .venv/Scripts/python scripts/seed_chen_watchlist.py
"""
import sys
import os

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import create_db_and_tables
from app.services import watchlist_service

WATCHLIST_NAME = "Chen Stock Picks"

# All tickers extracted from chen.md (deduplicated, sorted by sector)
TICKERS = [
    # 光互连 / AI 数据中心
    "CRDO", "AAOI", "COHR", "OCC", "VIAV", "POET", "LWLG", "ADTN",
    # 存储
    "MU",
    # 半导体
    "AMKR", "INTT", "AEHR", "GCTS",
    # 低轨卫星
    "PL", "SIDU", "ASTS", "RKLB", "YSS",
    # 无人机 / AI 平台
    "ONDS",
    # 储能
    "EOSE",
    # 电网 / 超导
    "AMSC", "ON", "STM", "WOLF",
    # 激光
    "LASE",
    # 其他
    "OPTX", "BW", "AXTI", "TTMI",
    # STEM was delisted/merged — skip
]


def main():
    print("Initialising database …")
    create_db_and_tables()

    # Check if watchlist already exists
    existing = watchlist_service.get_all_watchlists(account_id=None)
    for wl in existing:
        if wl.watchlist_name == WATCHLIST_NAME:
            print(f"Watchlist '{WATCHLIST_NAME}' already exists (id={wl.watchlist_id}). Skipping creation.")
            watchlist_id = wl.watchlist_id
            break
    else:
        print(f"Creating watchlist '{WATCHLIST_NAME}' …")
        wl = watchlist_service.create_watchlist(
            watchlist_name=WATCHLIST_NAME,
            account_id=None,
            description="Stocks recommended by Yun Chen (2026-03-23 ~ 2026-04-14)",
        )
        watchlist_id = wl.watchlist_id
        print(f"  Created: id={watchlist_id}")

    print(f"\nAdding {len(TICKERS)} tickers …")
    added, skipped = watchlist_service.add_stocks_to_watchlist(
        watchlist_id=watchlist_id,
        tickers=TICKERS,
        account_id=None,
    )

    print(f"\nAdded ({len(added)}): {[s.ticker for s in added]}")
    if skipped:
        print(f"Skipped ({len(skipped)}): {skipped}")
    print("\nDone. Open http://localhost:8000/watchlists to view.")


if __name__ == "__main__":
    main()
