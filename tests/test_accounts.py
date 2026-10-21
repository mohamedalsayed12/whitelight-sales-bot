from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.database import SessionLocal
from app.models import Cheque, ChequeStatus, Client, ClientType, Invoice, UserRole

TODAY = date(2026, 10, 20)


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr("app.services.accounts.bahrain_today", lambda: TODAY)
    return TODAY


def _add_client(
    *,
    name: str,
    credit_limit: str = "1000.000",
    salesman_id: int | None = None,
) -> int:
    db = SessionLocal()
    try:
        client = Client(
            name=name,
            type=ClientType.hotel,
            credit_limit=Decimal(credit_limit),
            assigned_salesman_id=salesman_id,
            phone="",
        )
        db.add(client)
        db.commit()
        return client.id
    finally:
        db.close()


def _add_invoice(client_id: int, number: str, due: date, amount: str, paid: str = "0") -> None:
    db = SessionLocal()
    try:
        db.add(
            Invoice(
                client_id=client_id,
                number=number,
                issue_date=due - timedelta(days=30),
                due_date=due,
                amount=Decimal(amount),
                amount_paid=Decimal(paid),
            )
        )
        db.commit()
    finally:
        db.close()


def _add_cheque(client_id: int, number: str, amount: str, status: ChequeStatus) -> None:
    db = SessionLocal()
    try:
        db.add(
            Cheque(
                client_id=client_id,
                cheque_number=number,
                bank="NBB",
                amount=Decimal(amount),
                due_date=TODAY,
                status=status,
            )
        )
        db.commit()
    finally:
        db.close()


def _account(client, token: str, client_id: int):
    return client.get(
        f"/clients/{client_id}/account",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_account_requires_a_token(client):
    response = client.get("/clients/1/account")

    assert response.status_code == 401


def test_unknown_client_is_404(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")

    response = _account(client, token, 999)

    assert response.status_code == 404
    assert response.json()["detail"] == "Client not found"


def test_client_id_must_be_an_integer(client, add_user, login):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")

    response = client.get(
        "/clients/abc/account",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_salesman_sees_only_assigned_clients(client, add_user, login, today):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    own_id = _add_client(name="Gulf Hotel", salesman_id=sam.id)
    other_id = _add_client(name="Marina Restaurant", salesman_id=other.id)
    loose_id = _add_client(name="Walk-in Cafe")
    token = login("sam@example.com")

    own = _account(client, token, own_id)
    denied = _account(client, token, other_id)
    unassigned = _account(client, token, loose_id)

    assert own.status_code == 200
    assert own.json()["name"] == "Gulf Hotel"
    assert own.json()["status"] == "ok"
    assert denied.status_code == 403
    assert denied.json()["detail"] == "You can only view clients assigned to you"
    assert unassigned.status_code == 403


def test_manager_and_admin_can_view_any_client(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    add_user(email="admin@example.com", role=UserRole.admin, full_name="Ada")
    client_id = _add_client(name="Walk-in Cafe")

    manager = _account(client, login("manager@example.com"), client_id)
    admin = _account(client, login("admin@example.com"), client_id)

    assert manager.status_code == 200
    assert admin.status_code == 200


def test_aging_buckets_use_the_bahrain_date(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="10000")
    _add_invoice(client_id, "DUE-TODAY", today, "10")
    _add_invoice(client_id, "DUE-30", today - timedelta(days=30), "10")
    _add_invoice(client_id, "DUE-31", today - timedelta(days=31), "10")
    _add_invoice(client_id, "DUE-60", today - timedelta(days=60), "10")
    _add_invoice(client_id, "DUE-61", today - timedelta(days=61), "10")
    _add_invoice(client_id, "DUE-90", today - timedelta(days=90), "10")
    _add_invoice(client_id, "DUE-91", today - timedelta(days=91), "10")
    _add_invoice(client_id, "NOT-DUE", today + timedelta(days=1), "10")
    _add_invoice(client_id, "PAID", today - timedelta(days=10), "10", paid="10")

    response = _account(client, token, client_id)

    assert response.status_code == 200
    body = response.json()
    assert body["total_outstanding"] == "80.000"
    assert body["overdue"] == {
        "0_30": "20.000",
        "31_60": "20.000",
        "61_90": "20.000",
        "over_90": "10.000",
    }
    assert body["status"] == "on_hold"


def test_money_that_is_not_due_yet_is_ok(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="100")
    _add_invoice(client_id, "INV-1", today + timedelta(days=1), "40")

    body = _account(client, token, client_id).json()

    assert body["total_outstanding"] == "40.000"
    assert body["overdue"] == {"0_30": "0.000", "31_60": "0.000", "61_90": "0.000", "over_90": "0.000"}
    assert body["status"] == "ok"


def test_recent_overdue_is_a_warning(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="100")
    _add_invoice(client_id, "INV-1", today - timedelta(days=10), "10", paid="4")

    body = _account(client, token, client_id).json()

    assert body["total_outstanding"] == "6.000"
    assert body["overdue"]["0_30"] == "6.000"
    assert body["status"] == "warning"


def test_ninety_days_overdue_is_still_a_warning(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="100")
    _add_invoice(client_id, "INV-1", today - timedelta(days=90), "10")

    body = _account(client, token, client_id).json()

    assert body["overdue"]["61_90"] == "10.000"
    assert body["overdue"]["over_90"] == "0.000"
    assert body["status"] == "warning"


def test_more_than_ninety_days_overdue_is_on_hold(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="100")
    _add_invoice(client_id, "INV-1", today - timedelta(days=91), "10")

    body = _account(client, token, client_id).json()

    assert body["status"] == "on_hold"


def test_over_the_credit_limit_is_on_hold(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="100")
    _add_invoice(client_id, "INV-1", today + timedelta(days=5), "100.001")

    assert _account(client, token, client_id).json()["status"] == "on_hold"


def test_exactly_the_credit_limit_is_ok(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel", credit_limit="100")
    _add_invoice(client_id, "INV-1", today + timedelta(days=5), "100")

    assert _account(client, token, client_id).json()["status"] == "ok"


def test_pending_cheques_are_received_or_deposited(client, add_user, login, today):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")
    client_id = _add_client(name="Gulf Hotel")
    _add_cheque(client_id, "1001", "20", ChequeStatus.received)
    _add_cheque(client_id, "1002", "5.500", ChequeStatus.deposited)
    _add_cheque(client_id, "1003", "100", ChequeStatus.cleared)
    _add_cheque(client_id, "1004", "7", ChequeStatus.bounced)

    body = _account(client, token, client_id).json()

    assert body["pending_cheques"] == "25.500"
    assert body["total_outstanding"] == "0.000"
