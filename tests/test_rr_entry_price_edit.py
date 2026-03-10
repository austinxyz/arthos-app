"""Tests for the RR entry price edit functionality."""
import pytest
from datetime import date, timedelta, datetime
from decimal import Decimal
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.database import engine
from app.models.rr_watchlist import RRWatchlist
from app.services.rr_watchlist_service import update_rr_entry_prices


def make_rr_entry(
    ticker="AAPL",
    put_strike=150.0,
    call_strike=170.0,
    put_qty=1,
    call_qty=1,
    put_quote=5.0,
    call_quote=8.0,
    ratio="1:1",
    account_id=None,
):
    """Create and persist a test RR entry, returning it."""
    with Session(engine) as session:
        entry = RRWatchlist(
            ticker=ticker,
            expiration=date.today() + timedelta(days=365),
            put_strike=Decimal(str(put_strike)),
            call_strike=Decimal(str(call_strike)),
            put_quantity=put_qty,
            call_quantity=call_qty,
            stock_price=Decimal("160.00"),
            entry_price=Decimal(str(call_quote * call_qty - put_quote * put_qty)),
            call_option_quote=Decimal(str(call_quote)),
            put_option_quote=Decimal(str(put_quote)),
            ratio=ratio,
            expired_yn="N",
            date_added=datetime.now(),
            account_id=str(account_id) if account_id else None,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


@pytest.fixture
def client():
    return TestClient(app)


class TestUpdateRREntryPricesService:
    def test_updates_quotes_and_recalculates_entry_price(self, setup_database, test_user):
        """Service correctly updates quotes and recalculates net entry_price."""
        entry = make_rr_entry(
            put_quote=5.0, call_quote=8.0, put_qty=1, call_qty=1,
            account_id=test_user.id
        )
        # Original entry_price = 8.0 * 1 - 5.0 * 1 = 3.0

        result = update_rr_entry_prices(
            rr_uuid=entry.id,
            put_option_quote=6.0,
            call_option_quote=9.0,
            account_id=str(test_user.id),
        )

        assert result["success"] is True
        assert result["put_option_quote"] == pytest.approx(6.0)
        assert result["call_option_quote"] == pytest.approx(9.0)
        # new entry_price = 9.0 * 1 - 6.0 * 1 = 3.0
        assert result["entry_price"] == pytest.approx(3.0)

        # Verify DB updated
        with Session(engine) as session:
            updated = session.get(RRWatchlist, entry.id)
            assert float(updated.put_option_quote) == pytest.approx(6.0)
            assert float(updated.call_option_quote) == pytest.approx(9.0)
            assert float(updated.entry_price) == pytest.approx(3.0)

    def test_entry_price_reflects_call_quantity(self, setup_database, test_user):
        """Net entry price scales by call quantity: call_quote * call_qty - put_quote * put_qty."""
        entry = make_rr_entry(
            put_quote=5.0, call_quote=4.0, put_qty=1, call_qty=2,
            ratio="1:2", account_id=test_user.id
        )

        result = update_rr_entry_prices(
            rr_uuid=entry.id,
            put_option_quote=5.0,
            call_option_quote=4.0,
            account_id=str(test_user.id),
        )

        assert result["success"] is True
        # entry_price = 4.0 * 2 - 5.0 * 1 = 3.0
        assert result["entry_price"] == pytest.approx(3.0)

    def test_returns_error_for_wrong_account(self, setup_database, test_user):
        """Returns access denied for wrong account_id."""
        entry = make_rr_entry(put_quote=5.0, call_quote=8.0, account_id=test_user.id)

        result = update_rr_entry_prices(
            rr_uuid=entry.id,
            put_option_quote=6.0,
            call_option_quote=9.0,
            account_id="wrong-account-id",
        )

        assert result["success"] is False
        assert "denied" in result["error"].lower()

    def test_returns_error_for_missing_entry(self, setup_database):
        """Returns error when entry UUID does not exist."""
        result = update_rr_entry_prices(
            rr_uuid="00000000-0000-0000-0000-000000000000",
            put_option_quote=5.0,
            call_option_quote=8.0,
        )
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_collar_updates_short_call_quote(self, setup_database, test_user):
        """For Collar strategies, short_call_option_quote is also updated."""
        with Session(engine) as session:
            entry = RRWatchlist(
                ticker="TSLA",
                expiration=date.today() + timedelta(days=365),
                put_strike=Decimal("150.0"),
                call_strike=Decimal("170.0"),
                put_quantity=1,
                call_quantity=1,
                short_call_strike=Decimal("200.0"),
                short_call_quantity=1,
                short_call_option_quote=Decimal("2.0"),
                stock_price=Decimal("160.0"),
                entry_price=Decimal("1.0"),  # 8-5-2=1
                call_option_quote=Decimal("8.0"),
                put_option_quote=Decimal("5.0"),
                ratio="Collar",
                collar_type="1:1",
                expired_yn="N",
                date_added=datetime.now(),
                account_id=str(test_user.id),
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

        result = update_rr_entry_prices(
            rr_uuid=entry_id,
            put_option_quote=6.0,
            call_option_quote=9.0,
            account_id=str(test_user.id),
            short_call_option_quote=3.0,
        )

        assert result["success"] is True
        # entry_price = 9*1 - 6*1 - 3*1 = 0.0
        assert result["entry_price"] == pytest.approx(0.0)
        assert result["short_call_option_quote"] == pytest.approx(3.0)


class TestUpdateRREntryPricesAPI:
    def test_patch_endpoint_updates_prices(self, setup_database, test_user):
        """PATCH /api/rr-watchlist/{uuid}/entry-prices returns updated values."""
        entry = make_rr_entry(
            put_quote=5.0, call_quote=8.0, put_qty=1, call_qty=1,
            account_id=test_user.id
        )

        with TestClient(app) as client:
            # Set up session
            with client as c:
                session_data = {"account_id": str(test_user.id)}
                with c.session_transaction() if hasattr(c, 'session_transaction') else __import__('contextlib').nullcontext():
                    pass

        # Use authenticated client via session cookie injection
        from fastapi.testclient import TestClient as TC
        with TC(app) as c:
            # Inject account_id into session by calling test login
            login_resp = c.get(f"/_test/login/{test_user.id}")
            assert login_resp.status_code == 200

            resp = c.patch(
                f"/api/rr-watchlist/{entry.id}/entry-prices",
                json={"put_option_quote": 6.0, "call_option_quote": 9.0},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["put_option_quote"] == pytest.approx(6.0)
            assert data["call_option_quote"] == pytest.approx(9.0)
            assert data["entry_price"] == pytest.approx(3.0)

    def test_patch_endpoint_missing_fields(self, setup_database, test_user):
        """Returns error when required price fields are missing."""
        entry = make_rr_entry(account_id=test_user.id)

        from fastapi.testclient import TestClient as TC
        with TC(app) as c:
            c.post(f"/_test/login/{test_user.id}")
            resp = c.patch(
                f"/api/rr-watchlist/{entry.id}/entry-prices",
                json={"call_option_quote": 9.0},  # missing put_option_quote
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
