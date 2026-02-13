#!/usr/bin/env python3
"""
Diagnostic script to check data ownership status in production.
Run this to see why grandfathering didn't work.
"""
import os
from sqlmodel import Session, text
from app.database import engine

def diagnose_data_ownership():
    """Check the current state of data ownership."""
    default_email = os.getenv("DEFAULT_ACCOUNT_EMAIL", "default-account@arthos.local")

    print("=" * 80)
    print("DATA OWNERSHIP DIAGNOSTIC")
    print("=" * 80)

    with Session(engine) as session:
        # Check if account exists
        print(f"\n1. Checking for {default_email} account...")
        try:
            result = session.exec(text(f"SELECT id, email, google_sub FROM account WHERE email = '{default_email}'")).first()
            if result:
                print(f"   ✅ Account exists: ID = {result[0]}, email = {result[1]}, google_sub = {result[2]}")
                default_account_id = result[0]
            else:
                print("   ❌ Account does NOT exist!")
                return
        except Exception as e:
            print(f"   ❌ Error checking account table: {e}")
            return

        # Check watchlist ownership
        print("\n2. Checking watchlist ownership...")
        try:
            # Total watchlists
            total = session.exec(text("SELECT COUNT(*) FROM watchlist")).scalar()
            print(f"   Total watchlists: {total}")

            # Watchlists with NULL account_id
            null_count = session.exec(text("SELECT COUNT(*) FROM watchlist WHERE account_id IS NULL")).scalar()
            print(f"   Watchlists with NULL account_id: {null_count}")

            # Watchlists owned by default account
            owned = session.exec(text(f"SELECT COUNT(*) FROM watchlist WHERE account_id = '{default_account_id}'")).scalar()
            print(f"   Watchlists owned by {default_email}: {owned}")

            # Watchlists owned by others
            others = total - null_count - owned
            print(f"   Watchlists owned by other accounts: {others}")

            if null_count > 0:
                print(f"   ⚠️  WARNING: {null_count} watchlists have NULL account_id - grandfathering incomplete!")
            elif owned == 0 and total > 0:
                print(f"   ⚠️  WARNING: No watchlists assigned to {default_email} but {total} exist!")
            else:
                print(f"   ✅ All watchlists properly assigned")

        except Exception as e:
            print(f"   ❌ Error checking watchlist: {e}")

        # Check RR watchlist ownership
        print("\n3. Checking rr_watchlist ownership...")
        try:
            # Total RR entries
            total = session.exec(text("SELECT COUNT(*) FROM rr_watchlist")).scalar()
            print(f"   Total RR watchlist entries: {total}")

            # RR entries with NULL account_id
            null_count = session.exec(text("SELECT COUNT(*) FROM rr_watchlist WHERE account_id IS NULL")).scalar()
            print(f"   RR entries with NULL account_id: {null_count}")

            # RR entries owned by default account
            owned = session.exec(text(f"SELECT COUNT(*) FROM rr_watchlist WHERE account_id = '{default_account_id}'")).scalar()
            print(f"   RR entries owned by {default_email}: {owned}")

            # RR entries owned by others
            others = total - null_count - owned
            print(f"   RR entries owned by other accounts: {others}")

            if null_count > 0:
                print(f"   ⚠️  WARNING: {null_count} RR entries have NULL account_id - grandfathering incomplete!")
            elif owned == 0 and total > 0:
                print(f"   ⚠️  WARNING: No RR entries assigned to {default_email} but {total} exist!")
            else:
                print(f"   ✅ All RR entries properly assigned")

        except Exception as e:
            print(f"   ❌ Error checking rr_watchlist: {e}")

        # Show sample records
        print("\n4. Sample watchlist records (first 5)...")
        try:
            results = session.exec(text("SELECT watchlist_id, watchlist_name, account_id FROM watchlist LIMIT 5")).all()
            for row in results:
                status = "✅" if row[2] == default_account_id else ("❌ NULL" if row[2] is None else "⚠️  OTHER")
                print(f"   {status} {row[0]}: {row[1]} (account_id: {row[2]})")
        except Exception as e:
            print(f"   ❌ Error: {e}")

        print("\n5. Checking for any other accounts...")
        try:
            results = session.exec(text("SELECT id, email FROM account")).all()
            print(f"   Total accounts: {len(results)}")
            for row in results:
                marker = "👤" if row[1] == default_email else "👥"
                print(f"   {marker} {row[1]} (ID: {row[0]})")
        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    diagnose_data_ownership()
