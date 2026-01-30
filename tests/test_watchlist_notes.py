"""Tests for watchlist stock notes."""
import pytest
from uuid import uuid4
from datetime import datetime
from sqlmodel import Session, select
from app.database import engine, create_db_and_tables
from app.models.watchlist import WatchList, WatchListStock
from app.models.watchlist_stock_notes import WatchlistStockNote
from app.models.account import Account
from app.services.watchlist_notes_service import (
    create_or_update_note,
    get_note,
    delete_note,
    get_all_notes_for_stock,
    get_watchlists_for_stock,
    MAX_NOTE_LENGTH
)
from tests.conftest import populate_test_stock_prices


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup
    with Session(engine) as session:
        # Delete notes first (FK constraint)
        for note in session.exec(select(WatchlistStockNote)).all():
            session.delete(note)
        session.commit()

        for stock in session.exec(select(WatchListStock)).all():
            session.delete(stock)
        session.commit()

        for watchlist in session.exec(select(WatchList)).all():
            session.delete(watchlist)
        session.commit()

        for account in session.exec(select(Account)).all():
            session.delete(account)
        session.commit()


def _create_test_account(account_id: str = None) -> Account:
    """Helper to create a test account."""
    if account_id is None:
        account_id = str(uuid4())

    with Session(engine) as session:
        account = Account(
            id=account_id,
            email=f"test-{account_id[:8]}@example.com",
            google_sub=f"google-{account_id[:8]}"
        )
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def _create_test_watchlist(account_id: str, name: str = "Test Watchlist") -> WatchList:
    """Helper to create a test watchlist."""
    with Session(engine) as session:
        watchlist = WatchList(
            watchlist_id=str(uuid4()),
            watchlist_name=name,
            account_id=account_id,
            date_added=datetime.now(),
            date_modified=datetime.now()
        )
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
    return watchlist


def _add_stock_to_watchlist(watchlist_id: str, ticker: str) -> WatchListStock:
    """Helper to add a stock to a watchlist."""
    with Session(engine) as session:
        stock = WatchListStock(
            watchlist_id=watchlist_id,
            ticker=ticker.upper(),
            date_added=datetime.now()
        )
        session.add(stock)
        session.commit()
        session.refresh(stock)
    return stock


class TestCreateOrUpdateNote:
    """Tests for create_or_update_note function."""

    def test_create_note_success(self):
        """Test creating a new note."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        note = create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Great dividend stock",
            account_id=account.id
        )

        assert note is not None
        assert note.watchlist_id == watchlist.watchlist_id
        assert note.ticker == "AAPL"
        assert note.note_text == "Great dividend stock"
        assert note.created_at is not None
        assert note.updated_at is not None

    def test_update_existing_note(self):
        """Test updating an existing note."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        # Create initial note
        note1 = create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Initial note",
            account_id=account.id
        )
        original_created_at = note1.created_at

        # Update note
        note2 = create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Updated note",
            account_id=account.id
        )

        assert note2.note_text == "Updated note"
        assert note2.created_at == original_created_at
        assert note2.updated_at >= note1.updated_at

    def test_note_max_length_validation(self):
        """Test that notes exceeding max length are rejected."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        long_note = "A" * (MAX_NOTE_LENGTH + 1)

        with pytest.raises(ValueError, match="cannot exceed"):
            create_or_update_note(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                note_text=long_note,
                account_id=account.id
            )

    def test_note_at_max_length(self):
        """Test that notes at exactly max length are accepted."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        max_note = "A" * MAX_NOTE_LENGTH

        note = create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text=max_note,
            account_id=account.id
        )

        assert note is not None
        assert len(note.note_text) == MAX_NOTE_LENGTH

    def test_create_note_stock_not_in_watchlist(self):
        """Test that creating a note fails if stock is not in watchlist."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        # Don't add stock to watchlist

        with pytest.raises(ValueError, match="not in watchlist"):
            create_or_update_note(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                note_text="Test note",
                account_id=account.id
            )

    def test_create_note_watchlist_not_found(self):
        """Test that creating a note fails if watchlist doesn't exist."""
        account = _create_test_account()
        fake_watchlist_id = str(uuid4())

        with pytest.raises(ValueError, match="not found"):
            create_or_update_note(
                watchlist_id=fake_watchlist_id,
                ticker="AAPL",
                note_text="Test note",
                account_id=account.id
            )


class TestAccessControl:
    """Tests for access control on notes."""

    def test_cannot_create_note_for_other_users_watchlist(self):
        """Test that users cannot create notes for watchlists they don't own."""
        owner = _create_test_account()
        other_user = _create_test_account()

        watchlist = _create_test_watchlist(owner.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        with pytest.raises(ValueError, match="Access denied"):
            create_or_update_note(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                note_text="Unauthorized note",
                account_id=other_user.id
            )

    def test_cannot_delete_note_from_other_users_watchlist(self):
        """Test that users cannot delete notes from watchlists they don't own."""
        owner = _create_test_account()
        other_user = _create_test_account()

        watchlist = _create_test_watchlist(owner.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        # Owner creates a note
        create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Owner's note",
            account_id=owner.id
        )

        # Other user tries to delete it
        with pytest.raises(ValueError, match="Access denied"):
            delete_note(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                account_id=other_user.id
            )

    def test_cannot_get_note_from_other_users_watchlist(self):
        """Test that users cannot get notes from watchlists they don't own."""
        owner = _create_test_account()
        other_user = _create_test_account()

        watchlist = _create_test_watchlist(owner.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        # Owner creates a note
        create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Owner's note",
            account_id=owner.id
        )

        # Other user tries to get it
        with pytest.raises(ValueError, match="Access denied"):
            get_note(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                account_id=other_user.id
            )


class TestGetNote:
    """Tests for get_note function."""

    def test_get_existing_note(self):
        """Test getting an existing note."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Test note",
            account_id=account.id
        )

        note = get_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            account_id=account.id
        )

        assert note is not None
        assert note.note_text == "Test note"

    def test_get_nonexistent_note(self):
        """Test getting a note that doesn't exist."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        note = get_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            account_id=account.id
        )

        assert note is None


class TestDeleteNote:
    """Tests for delete_note function."""

    def test_delete_existing_note(self):
        """Test deleting an existing note."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Test note",
            account_id=account.id
        )

        result = delete_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            account_id=account.id
        )

        assert result is True

        # Verify note is deleted
        note = get_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            account_id=account.id
        )
        assert note is None

    def test_delete_nonexistent_note(self):
        """Test deleting a note that doesn't exist."""
        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        result = delete_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            account_id=account.id
        )

        assert result is False


class TestGetAllNotesForStock:
    """Tests for get_all_notes_for_stock function."""

    def test_get_notes_across_multiple_watchlists(self):
        """Test getting notes for a stock across multiple watchlists."""
        account = _create_test_account()

        watchlist1 = _create_test_watchlist(account.id, "Growth Portfolio")
        watchlist2 = _create_test_watchlist(account.id, "Dividend Portfolio")

        _add_stock_to_watchlist(watchlist1.watchlist_id, "AAPL")
        _add_stock_to_watchlist(watchlist2.watchlist_id, "AAPL")

        create_or_update_note(
            watchlist_id=watchlist1.watchlist_id,
            ticker="AAPL",
            note_text="Tech growth play",
            account_id=account.id
        )

        create_or_update_note(
            watchlist_id=watchlist2.watchlist_id,
            ticker="AAPL",
            note_text="Dividend income",
            account_id=account.id
        )

        notes = get_all_notes_for_stock("AAPL", account.id)

        assert len(notes) == 2
        note_texts = [n["note_text"] for n in notes]
        assert "Tech growth play" in note_texts
        assert "Dividend income" in note_texts

        # Verify watchlist names are included
        watchlist_names = [n["watchlist_name"] for n in notes]
        assert "Growth Portfolio" in watchlist_names
        assert "Dividend Portfolio" in watchlist_names

    def test_get_notes_only_returns_own_watchlists(self):
        """Test that get_all_notes_for_stock only returns notes from user's own watchlists."""
        user1 = _create_test_account()
        user2 = _create_test_account()

        watchlist1 = _create_test_watchlist(user1.id, "User1 Watchlist")
        watchlist2 = _create_test_watchlist(user2.id, "User2 Watchlist")

        _add_stock_to_watchlist(watchlist1.watchlist_id, "AAPL")
        _add_stock_to_watchlist(watchlist2.watchlist_id, "AAPL")

        create_or_update_note(
            watchlist_id=watchlist1.watchlist_id,
            ticker="AAPL",
            note_text="User1 note",
            account_id=user1.id
        )

        create_or_update_note(
            watchlist_id=watchlist2.watchlist_id,
            ticker="AAPL",
            note_text="User2 note",
            account_id=user2.id
        )

        # User1 should only see their own notes
        user1_notes = get_all_notes_for_stock("AAPL", user1.id)
        assert len(user1_notes) == 1
        assert user1_notes[0]["note_text"] == "User1 note"

        # User2 should only see their own notes
        user2_notes = get_all_notes_for_stock("AAPL", user2.id)
        assert len(user2_notes) == 1
        assert user2_notes[0]["note_text"] == "User2 note"

    def test_get_notes_returns_empty_for_no_watchlists(self):
        """Test that get_all_notes_for_stock returns empty list when user has no watchlists."""
        account = _create_test_account()

        notes = get_all_notes_for_stock("AAPL", account.id)

        assert notes == []


class TestGetWatchlistsForStock:
    """Tests for get_watchlists_for_stock function."""

    def test_get_watchlists_containing_stock(self):
        """Test getting watchlists that contain a specific stock."""
        account = _create_test_account()

        watchlist1 = _create_test_watchlist(account.id, "Watchlist A")
        watchlist2 = _create_test_watchlist(account.id, "Watchlist B")
        watchlist3 = _create_test_watchlist(account.id, "Watchlist C")

        _add_stock_to_watchlist(watchlist1.watchlist_id, "AAPL")
        _add_stock_to_watchlist(watchlist2.watchlist_id, "AAPL")
        # watchlist3 doesn't have AAPL
        _add_stock_to_watchlist(watchlist3.watchlist_id, "MSFT")

        watchlists = get_watchlists_for_stock("AAPL", account.id)

        assert len(watchlists) == 2
        watchlist_names = [w["watchlist_name"] for w in watchlists]
        assert "Watchlist A" in watchlist_names
        assert "Watchlist B" in watchlist_names
        assert "Watchlist C" not in watchlist_names


class TestCascadeDelete:
    """Tests for cascade delete behavior when watchlist is deleted."""

    def test_notes_deleted_when_watchlist_deleted(self):
        """Test that notes are deleted when the parent watchlist is deleted."""
        from app.services.watchlist_service import delete_watchlist

        account = _create_test_account()
        watchlist = _create_test_watchlist(account.id)
        _add_stock_to_watchlist(watchlist.watchlist_id, "AAPL")

        create_or_update_note(
            watchlist_id=watchlist.watchlist_id,
            ticker="AAPL",
            note_text="Test note",
            account_id=account.id
        )

        # Verify note exists
        with Session(engine) as session:
            note = session.get(WatchlistStockNote, (watchlist.watchlist_id, "AAPL"))
            assert note is not None

        # Delete watchlist
        delete_watchlist(watchlist.watchlist_id, account.id)

        # Verify note is also deleted (due to FK cascade or manual cleanup)
        with Session(engine) as session:
            note = session.get(WatchlistStockNote, (watchlist.watchlist_id, "AAPL"))
            # Note should be None because watchlist no longer exists
            # (database cascade or orphan cleanup should handle this)
            # If this fails, we might need to add cascade delete in the model
            assert note is None
