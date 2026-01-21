#!/usr/bin/env python3
"""
Script to fix data ownership - assigns ALL orphaned data to kgajjala@gmail.com.
This is a more robust version of the migration that handles edge cases.
"""
import os
from sqlmodel import Session, text
from app.database import engine
from uuid import uuid4
from datetime import datetime

def fix_data_ownership(dry_run=True):
    """
    Fix data ownership by assigning all orphaned data to kgajjala@gmail.com.

    Args:
        dry_run: If True, only show what would be done without making changes
    """
    print("=" * 80)
    print("DATA OWNERSHIP FIX SCRIPT")
    print("=" * 80)

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    else:
        print("⚠️  LIVE MODE - Changes will be committed to database")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    print()

    default_email = "kgajjala@gmail.com"

    with Session(engine) as session:
        # Step 1: Find or create the default account
        print("Step 1: Checking for default account...")
        try:
            result = session.exec(text(f"SELECT id FROM account WHERE email = '{default_email}'")).first()
            if result:
                default_account_id = result[0]
                print(f"   ✅ Found account: {default_account_id}")
            else:
                print(f"   ⚠️  Account not found. Creating...")
                new_id = str(uuid4())
                now_str = datetime.utcnow().isoformat()

                if not dry_run:
                    session.exec(text(
                        f"INSERT INTO account (id, email, google_sub, full_name, created_at) "
                        f"VALUES ('{new_id}', '{default_email}', 'migration_placeholder', 'Karthik Gajjala', '{now_str}')"
                    ))
                    session.commit()
                    default_account_id = new_id
                    print(f"   ✅ Created account: {default_account_id}")
                else:
                    default_account_id = new_id
                    print(f"   [DRY RUN] Would create account: {default_account_id}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return

        # Step 2: Fix watchlist ownership
        print("\nStep 2: Fixing watchlist ownership...")
        try:
            # Count orphaned watchlists
            null_count = session.exec(text("SELECT COUNT(*) FROM watchlist WHERE account_id IS NULL")).scalar()
            print(f"   Found {null_count} watchlists with NULL account_id")

            if null_count > 0:
                if not dry_run:
                    result = session.exec(text(
                        f"UPDATE watchlist SET account_id = '{default_account_id}' WHERE account_id IS NULL"
                    ))
                    session.commit()
                    print(f"   ✅ Updated {null_count} watchlists")
                else:
                    print(f"   [DRY RUN] Would update {null_count} watchlists")
            else:
                print(f"   ℹ️  No orphaned watchlists found")

            # Verify
            owned_count = session.exec(text(
                f"SELECT COUNT(*) FROM watchlist WHERE account_id = '{default_account_id}'"
            )).scalar()
            total_count = session.exec(text("SELECT COUNT(*) FROM watchlist")).scalar()
            print(f"   📊 kgajjala@gmail.com now owns {owned_count} of {total_count} watchlists")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            session.rollback()

        # Step 3: Fix RR watchlist ownership
        print("\nStep 3: Fixing rr_watchlist ownership...")
        try:
            # Count orphaned RR entries
            null_count = session.exec(text("SELECT COUNT(*) FROM rr_watchlist WHERE account_id IS NULL")).scalar()
            print(f"   Found {null_count} RR entries with NULL account_id")

            if null_count > 0:
                if not dry_run:
                    result = session.exec(text(
                        f"UPDATE rr_watchlist SET account_id = '{default_account_id}' WHERE account_id IS NULL"
                    ))
                    session.commit()
                    print(f"   ✅ Updated {null_count} RR entries")
                else:
                    print(f"   [DRY RUN] Would update {null_count} RR entries")
            else:
                print(f"   ℹ️  No orphaned RR entries found")

            # Verify
            owned_count = session.exec(text(
                f"SELECT COUNT(*) FROM rr_watchlist WHERE account_id = '{default_account_id}'"
            )).scalar()
            total_count = session.exec(text("SELECT COUNT(*) FROM rr_watchlist")).scalar()
            print(f"   📊 kgajjala@gmail.com now owns {owned_count} of {total_count} RR entries")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            session.rollback()

        print("\n" + "=" * 80)
        if dry_run:
            print("DRY RUN COMPLETE - No changes were made")
            print("Run with --live flag to apply changes: python fix_data_ownership.py --live")
        else:
            print("FIX COMPLETE - All orphaned data assigned to kgajjala@gmail.com")
        print("=" * 80)


if __name__ == "__main__":
    import sys

    # Check for --live flag
    live_mode = "--live" in sys.argv or "-l" in sys.argv

    fix_data_ownership(dry_run=not live_mode)
