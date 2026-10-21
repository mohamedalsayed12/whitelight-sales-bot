from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database import SessionLocal
from app.models import (
    Cheque,
    ChequeStatus,
    Client,
    ClientType,
    Invoice,
    Order,
    OrderLine,
    OrderStatus,
    Product,
    UserRole,
)

TODAY = date(2026, 10, 20)


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr("app.services.accounts.bahrain_today", lambda: TODAY)
    return TODAY


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_client(salesman_id: int) -> int:
    db = SessionLocal()
    try:
        client = Client(
            name="Gulf Hotel",
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


def _add_product(sku: str, stock: str, reorder: str, *, active: bool = True) -> int:
    db = SessionLocal()
    try:
        product = Product(
            sku=sku,
            name=sku,
            category="",
            unit="pcs",
            stock_on_hand=Decimal(stock),
            reorder_level=Decimal(reorder),
            active=active,
        )
        db.add(product)
        db.commit()
        return product.id
    finally:
        db.close()


def _add_order(
    client_id: int,
    salesman_id: int,
    product_id: int,
    quantity: str,
    price: str,
    when: datetime,
    status: OrderStatus = OrderStatus.submitted,
) -> None:
    db = SessionLocal()
    try:
        order = Order(
            client_id=client_id,
            salesman_id=salesman_id,
            status=status,
            created_at=when,
        )
        db.add(order)
        db.flush()
        db.add(
            OrderLine(
                order_id=order.id,
                product_id=product_id,
                quantity=Decimal(quantity),
                unit_price=Decimal(price),
            )
        )
        db.commit()
    finally:
        db.close()


def test_reorder_list_uses_available_stock_and_open_orders(client, add_user, login):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    client_id = _add_client(sam.id)
    _add_product("WL-100", "2", "5")
    _add_product("WL-150", "3", "3")
    _add_product("WL-200", "10", "2")
    reserved = _add_product("WL-300", "10", "5")
    _add_product("WL-400", "0", "10", active=False)
    _add_order(client_id, sam.id, reserved, "6", "1", datetime(2026, 10, 20, 12, tzinfo=timezone.utc))
    _add_order(
        client_id,
        sam.id,
        reserved,
        "100",
        "1",
        datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
        status=OrderStatus.cancelled,
    )

    denied = client.get("/reorder", headers=_headers(salesman))
    listed = client.get("/reorder", headers=_headers(manager))

    assert denied.status_code == 403
    assert listed.status_code == 200
    by_sku = {row["sku"]: row for row in listed.json()}
    assert set(by_sku) == {"WL-100", "WL-150", "WL-300"}
    assert by_sku["WL-100"]["available"] == "2.000"
    assert by_sku["WL-100"]["on_order"] == "0.000"
    assert by_sku["WL-300"]["available"] == "4.000"
    assert by_sku["WL-300"]["on_order"] == "6.000"
    assert by_sku["WL-300"]["stock_on_hand"] == "10.000"
    assert by_sku["WL-150"]["available"] == "3.000"


def test_daily_summary_is_for_the_ceo_and_uses_the_bahrain_day(client, add_user, login, today):
    admin = add_user(email="ceo@example.com", role=UserRole.admin, full_name="CEO")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    ceo = login("ceo@example.com")
    manager = login("manager@example.com")
    client_id = _add_client(sam.id)
    product_id = _add_product("WL-100", "2", "5")
    noon_today = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)
    just_after_midnight = datetime(2026, 10, 19, 22, tzinfo=timezone.utc)
    next_bahrain_day = datetime(2026, 10, 20, 21, tzinfo=timezone.utc)
    _add_order(client_id, sam.id, product_id, "2", "5.000", just_after_midnight)
    _add_order(client_id, sam.id, product_id, "1", "2.500", noon_today)
    _add_order(client_id, sam.id, product_id, "1", "9.000", next_bahrain_day)
    _add_order(
        client_id,
        sam.id,
        product_id,
        "1",
        "4.000",
        noon_today,
        status=OrderStatus.cancelled,
    )
    db = SessionLocal()
    try:
        db.add(
            Invoice(
                client_id=client_id,
                number="INV-DUE",
                issue_date=TODAY - timedelta(days=30),
                due_date=TODAY,
                amount=Decimal("15"),
                amount_paid=Decimal("5"),
            )
        )
        db.add(
            Invoice(
                client_id=client_id,
                number="INV-LATER",
                issue_date=TODAY,
                due_date=TODAY + timedelta(days=1),
                amount=Decimal("40"),
                amount_paid=Decimal("0"),
            )
        )
        db.add(
            Cheque(
                client_id=client_id,
                cheque_number="1",
                bank="NBB",
                amount=Decimal("7"),
                due_date=TODAY,
                status=ChequeStatus.received,
                collected_by_id=sam.id,
                collected_at=just_after_midnight,
            )
        )
        db.add(
            Cheque(
                client_id=client_id,
                cheque_number="2",
                bank="NBB",
                amount=Decimal("1.500"),
                due_date=TODAY,
                status=ChequeStatus.bounced,
                collected_by_id=sam.id,
                collected_at=noon_today,
            )
        )
        db.add(
            Cheque(
                client_id=client_id,
                cheque_number="3",
                bank="NBB",
                amount=Decimal("3"),
                due_date=TODAY,
                status=ChequeStatus.received,
                collected_by_id=sam.id,
                collected_at=next_bahrain_day,
            )
        )
        db.commit()
    finally:
        db.close()

    denied = client.get("/summary", headers=_headers(manager))
    summary = client.get("/summary", headers=_headers(ceo))

    assert denied.status_code == 403
    assert denied.json()["detail"] == "Only an admin can view the daily summary"
    assert summary.status_code == 200
    body = summary.json()
    assert body["day"] == "2026-10-20"
    assert body["orders_today"] == 2
    assert body["orders_total"] == "12.500"
    assert body["cheques_collected"] == "8.500"
    assert body["total_overdue"] == "10.000"
    assert [item["sku"] for item in body["reorder"]] == ["WL-100"]
    assert admin.id > 0
