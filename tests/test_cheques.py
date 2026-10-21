from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.database import SessionLocal
from app.models import Cheque, ChequeStatus, Client, ClientType, UserRole

TODAY = date(2026, 10, 20)


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr("app.services.accounts.bahrain_today", lambda: TODAY)
    return TODAY


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_client(name: str, salesman_id: int) -> int:
    db = SessionLocal()
    try:
        client = Client(
            name=name,
            type=ClientType.hotel,
            credit_limit=Decimal("1000"),
            assigned_salesman_id=salesman_id,
            phone="",
        )
        db.add(client)
        db.commit()
        return client.id
    finally:
        db.close()


def _add_cheque(client_id: int, number: str, due: date, status: ChequeStatus, amount: str = "10") -> int:
    db = SessionLocal()
    try:
        cheque = Cheque(
            client_id=client_id,
            cheque_number=number,
            bank="NBB",
            amount=Decimal(amount),
            due_date=due,
            status=status,
        )
        db.add(cheque)
        db.commit()
        return cheque.id
    finally:
        db.close()


def _log(client, token: str, client_id: int, amount: str = "20.000", due: str = "2026-10-25"):
    return client.post(
        "/cheques",
        headers=_headers(token),
        json={
            "client_id": client_id,
            "cheque_number": " 1001 ",
            "bank": "NBB",
            "amount": amount,
            "due_date": due,
        },
    )


def test_logging_a_cheque_requires_a_token(client):
    response = client.post(
        "/cheques",
        json={
            "client_id": 1,
            "cheque_number": "1001",
            "bank": "NBB",
            "amount": "10",
            "due_date": "2026-10-25",
        },
    )

    assert response.status_code == 401


def test_salesman_logs_a_cheque_and_it_is_pending_on_the_account(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    salesman = login("sam@example.com")
    client_id = _add_client("Gulf Hotel", sam.id)

    created = _log(client, salesman, client_id)
    account = client.get(f"/clients/{client_id}/account", headers=_headers(salesman))

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "received"
    assert body["cheque_number"] == "1001"
    assert body["amount"] == "20.000"
    assert body["collected_by_id"] == sam.id
    assert body["client_name"] == "Gulf Hotel"
    assert account.status_code == 200
    assert account.json()["pending_cheques"] == "20.000"


def test_manager_cannot_log_a_cheque(client, add_user, login):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")

    response = _log(client, token, 1)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only a salesman can log a cheque"


def test_salesman_cannot_log_a_cheque_for_someone_elses_client(client, add_user, login):
    add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    salesman = login("sam@example.com")
    client_id = _add_client("Marina Hotel", other.id)

    response = _log(client, salesman, client_id)

    assert response.status_code == 403
    assert response.json()["detail"] == "You can only log cheques for clients assigned to you"


def test_manager_moves_a_cheque_through_the_bank(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    salesman = login("sam@example.com")
    manager = login("manager@example.com")
    client_id = _add_client("Gulf Hotel", sam.id)
    cheque_id = _log(client, salesman, client_id).json()["id"]

    denied = client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(salesman),
        json={"status": "deposited"},
    )
    skipped = client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(manager),
        json={"status": "cleared"},
    )
    deposited = client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(manager),
        json={"status": "deposited"},
    )
    cleared = client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(manager),
        json={"status": "cleared"},
    )
    finished = client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(manager),
        json={"status": "bounced"},
    )

    assert denied.status_code == 403
    assert skipped.status_code == 409
    assert deposited.status_code == 200
    assert deposited.json()["status"] == "deposited"
    assert cleared.status_code == 200
    assert cleared.json()["status"] == "cleared"
    assert finished.status_code == 409


def test_a_deposited_cheque_can_bounce(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    salesman = login("sam@example.com")
    manager = login("manager@example.com")
    client_id = _add_client("Gulf Hotel", sam.id)
    cheque_id = _log(client, salesman, client_id).json()["id"]
    client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(manager),
        json={"status": "deposited"},
    )

    bounced = client.post(
        f"/cheques/{cheque_id}/status",
        headers=_headers(manager),
        json={"status": "bounced"},
    )

    assert bounced.status_code == 200
    assert bounced.json()["status"] == "bounced"
    listed = client.get("/cheques/bounced", headers=_headers(manager))
    assert [row["id"] for row in listed.json()] == [cheque_id]


def test_due_list_is_the_next_seven_days_and_hides_other_clients(client, add_user, login, today):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    salesman = login("sam@example.com")
    other_token = login("other@example.com")
    own = _add_client("Gulf Hotel", sam.id)
    theirs = _add_client("Marina Hotel", other.id)
    due_today = _add_cheque(own, "1", TODAY, ChequeStatus.received)
    due_last = _add_cheque(own, "2", TODAY + timedelta(days=7), ChequeStatus.deposited)
    _add_cheque(own, "3", TODAY + timedelta(days=8), ChequeStatus.received)
    _add_cheque(own, "4", TODAY - timedelta(days=1), ChequeStatus.received)
    _add_cheque(own, "5", TODAY, ChequeStatus.cleared)
    _add_cheque(own, "6", TODAY, ChequeStatus.bounced)
    hidden = _add_cheque(theirs, "7", TODAY, ChequeStatus.received)

    own_list = client.get("/cheques/due", headers=_headers(salesman))
    other_list = client.get("/cheques/due", headers=_headers(other_token))

    assert [row["id"] for row in own_list.json()] == [due_today, due_last]
    assert [row["id"] for row in other_list.json()] == [hidden]


def test_zero_amount_and_unknown_cheque_are_rejected(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    salesman = login("sam@example.com")
    manager = login("manager@example.com")
    client_id = _add_client("Gulf Hotel", sam.id)

    zero = _log(client, salesman, client_id, amount="0")
    missing = client.post(
        "/cheques/999/status",
        headers=_headers(manager),
        json={"status": "deposited"},
    )

    assert zero.status_code == 422
    assert missing.status_code == 404
