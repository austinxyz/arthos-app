from sqlmodel import Session, select, create_engine, text
from app.models.account import Account
from app.models.watchlist import WatchList
from app.models.rr_watchlist import RRWatchlist
from app.database import engine, create_db_and_tables

def verify_refactor():
    print("Verifying refactor to Account...")
    
    # 1. Run migrations
    try:
        create_db_and_tables()
        print("✅ Database migration functions called.")
    except Exception as e:
        print(f"❌ Database migration failed: {e}")
        return

    # 2. Check Database Schema (via SQLModel)
    with Session(engine) as session:
        # Check Account table
        try:
            account = session.exec(select(Account).where(Account.email == "kgajjala@gmail.com")).first()
            if not account:
                 print("❌ Account 'kgajjala@gmail.com' NOT found in 'account' table!")
            else:
                 print(f"✅ Account found: {account.email} (ID: {account.id})")
        except Exception as e:
             print(f"❌ Failed to query Account table: {e}")
             
        # Check WatchList column rename
        try:
            # We can't easily check column name with SQLModel if the model and DB don't match, 
            # but since we updated the model, if selecting works, the column must exist or map correctly.
            # Let's try raw SQL to be sure about the DB column name.
            try:
                session.exec(text("SELECT account_id FROM watchlist LIMIT 1"))
                print("✅ 'watchlist.account_id' column exists.")
            except Exception:
                print("❌ 'watchlist.account_id' column DOES NOT exist.")
                
            try:
                session.exec(text("SELECT account_id FROM rr_watchlist LIMIT 1"))
                print("✅ 'rr_watchlist.account_id' column exists.")
            except Exception:
                print("❌ 'rr_watchlist.account_id' column DOES NOT exist.")

        except Exception as e:
            print(f"❌ Schema check failed: {e}")

if __name__ == "__main__":
    verify_refactor()
