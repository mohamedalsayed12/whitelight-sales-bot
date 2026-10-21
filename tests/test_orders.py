from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Client, ClientType, Invoice, Product, UserRole


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_product(sku: str, name: str, stock: str, *, active: bool = True) -> None:
    db = SessionLocal()
    try:
        db.add(
            Product(
                sku=sku,
                name=name,
                category="",
                unit="pcs",
                stock_on_hand=Decimal(stock),
                reorder_level=Decimal("5"),
                active=active,
            )
        )
        db.commit()
    finally:
        db.close()


def _add_client(name: str, salesman_id: int, *, credit_limit: str = "1000") -> int:
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


def _set_price(client, token: str, sku: str, price: str, price_list: str = "hotel") -> None:
    response = client.put(
        f"/price-lists/{price_list}/items",
        headers=_headers(token),
        json={"sku": sku, "unit_price": price},
    )
    assert response.status_code == 200, response.text


def _assign_list(client, token: str, client_id: int, price_list: str = "hotel") -> None:
    response = client.patch(
        f"/clients/{client_id}",
        headers=_headers(token),
        json={"price_list": price_list},
    )
    assert response.status_code == 200, response.text


def _order(client, token: str, client_id: int, sku: str = "WL-100", quantity: str = "2"):
    return client.post(
        "/orders",
        headers=_headers(token),
        json={"client_id": client_id, "lines": [{"sku": sku, "quantity": quantity}]},
    )


def test_order_requires_a_token(client):
    response = client.post("/orders", json={"client_id": 1, "lines": [{"sku": "WL-100", "quantity": "1"}]})

    assert response.status_code == 401


def test_manager_cannot_submit_an_order(client, add_user, login):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")

    response = _order(client, token, 1)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only a salesman can submit an order"


def test_salesman_submits_an_order_at_the_price_list_price(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)

    created = _order(client, salesman, client_id, quantity="4")

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "submitted"
    assert body["warning"] is None
    assert body["salesman_id"] == sam.id
    assert body["lines"] == [{"sku": "WL-100", "quantity": "4.000", "unit_price": "2.500"}]
    assert body["history"][0]["status"] == "submitted"
    assert body["history"][0]["changed_by_id"] == sam.id
    assert datetime.fromisoformat(body["history"][0]["changed_at"]).tzinfo is not None

    stock = client.get("/stock", params={"q": "WL-100"}, headers=_headers(salesman))
    assert stock.json()[0]["available"] == "6.000"
    assert stock.json()[0]["low_stock"] is False


def test_a_later_price_change_does_not_change_the_order(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)
    created = _order(client, salesman, client_id)
    _set_price(client, manager, "WL-100", "9.000")

    fetched = client.get(f"/orders/{created.json()['id']}", headers=_headers(salesman))

    assert fetched.status_code == 200
    assert fetched.json()["lines"][0]["unit_price"] == "2.500"


def test_on_hold_client_still_creates_an_order_with_a_warning(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id, credit_limit="0")
    db = SessionLocal()
    try:
        db.add(
            Invoice(
                client_id=client_id,
                number="INV-1",
                issue_date=date(2026, 9, 1),
                due_date=date(2026, 10, 1),
                amount=Decimal("20"),
                amount_paid=Decimal("0"),
            )
        )
        db.commit()
    finally:
        db.close()
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)

    response = _order(client, salesman, client_id)

    assert response.status_code == 201
    assert response.json()["status"] == "submitted"
    assert response.json()["warning"] == "Client is on hold. A manager must approve."


def test_not_enough_stock_is_a_conflict_and_saves_nothing(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "5")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)
    _order(client, salesman, client_id, quantity="3")

    response = _order(client, salesman, client_id, quantity="3")

    assert response.status_code == 409
    assert response.json()["detail"] == "Not enough stock for WL-100: available 2.000, requested 3.000"
    listed = client.get("/orders", headers=_headers(salesman))
    assert len(listed.json()) == 1


def test_salesman_cannot_see_another_salesmans_order(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    other_token = login("other@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    own_client = _add_client("Gulf Hotel", sam.id)
    other_client = _add_client("Marina Restaurant", other.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, own_client)
    _assign_list(client, manager, other_client)
    own = _order(client, salesman, own_client)
    theirs = _order(client, other_token, other_client)

    hidden = client.get(f"/orders/{theirs.json()['id']}", headers=_headers(salesman))
    visible = client.get("/orders", headers=_headers(salesman))
    manager_list = client.get("/orders", headers=_headers(manager))

    assert own.status_code == 201
    assert hidden.status_code == 403
    assert hidden.json()["detail"] == "You can only view your own orders"
    assert [row["id"] for row in visible.json()] == [own.json()["id"]]
    assert {row["id"] for row in manager_list.json()} == {own.json()["id"], theirs.json()["id"]}


def test_salesman_cannot_order_for_someone_elses_client(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Marina Restaurant", other.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)

    response = _order(client, salesman, client_id)

    assert response.status_code == 403


def test_order_rejects_a_missing_price_and_an_unknown_product(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id)

    no_list = _order(client, salesman, client_id)
    _assign_list(client, manager, client_id)
    missing = client.post(
        "/orders",
        headers=_headers(salesman),
        json={"client_id": client_id, "lines": [{"sku": "NO-SUCH", "quantity": "1"}]},
    )

    assert no_list.status_code == 422
    assert no_list.json()["detail"] == "Client has no price list"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Product NO-SUCH not found"


def test_product_on_the_other_list_is_rejected(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500", price_list="restaurant")
    _assign_list(client, manager, client_id, price_list="hotel")

    response = _order(client, salesman, client_id)

    assert response.status_code == 422
    assert response.json()["detail"] == "WL-100 is not on the hotel price list"


def test_manager_moves_an_order_through_delivery(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    manager_user = add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)
    order_id = _order(client, salesman, client_id, quantity="4").json()["id"]

    denied = client.post(
        f"/orders/{order_id}/status",
        headers=_headers(salesman),
        json={"status": "approved"},
    )
    skipped = client.post(
        f"/orders/{order_id}/status",
        headers=_headers(manager),
        json={"status": "delivered"},
    )
    approved = client.post(
        f"/orders/{order_id}/status",
        headers=_headers(manager),
        json={"status": "approved"},
    )
    out = client.post(
        f"/orders/{order_id}/status",
        headers=_headers(manager),
        json={"status": "out_for_delivery"},
    )
    delivered = client.post(
        f"/orders/{order_id}/status",
        headers=_headers(manager),
        json={"status": "delivered"},
    )

    assert denied.status_code == 403
    assert skipped.status_code == 409
    assert approved.status_code == 200
    assert out.status_code == 200
    assert delivered.status_code == 200
    body = delivered.json()
    assert body["status"] == "delivered"
    assert [entry["status"] for entry in body["history"]] == [
        "submitted",
        "approved",
        "out_for_delivery",
        "delivered",
    ]
    assert body["history"][1]["changed_by_id"] == manager_user.id
    db = SessionLocal()
    try:
        product = db.scalar(select(Product).where(Product.sku == "WL-100"))
        assert product is not None
        assert product.stock_on_hand == Decimal("6")
    finally:
        db.close()
    stock = client.get("/stock", params={"q": "WL-100"}, headers=_headers(salesman))
    assert stock.json()[0]["available"] == "6.000"


def test_cancelling_releases_the_reserved_stock(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp", "10")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)
    order_id = _order(client, salesman, client_id, quantity="4").json()["id"]

    response = client.post(
        f"/orders/{order_id}/status",
        headers=_headers(manager),
        json={"status": "cancelled"},
    )

    assert response.status_code == 200
    stock = client.get("/stock", params={"q": "WL-100"}, headers=_headers(salesman))
    assert stock.json()[0]["available"] == "10.000"


def test_duplicate_line_and_bad_quantity_are_422(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    salesman = login("sam@example.com")
    client_id = _add_client("Gulf Hotel", sam.id)

    duplicate = client.post(
        "/orders",
        headers=_headers(salesman),
        json={
            "client_id": client_id,
            "lines": [
                {"sku": "WL-100", "quantity": "1"},
                {"sku": "WL-100", "quantity": "1"},
            ],
        },
    )
    zero = client.post(
        "/orders",
        headers=_headers(salesman),
        json={"client_id": client_id, "lines": [{"sku": "WL-100", "quantity": "0"}]},
    )

    assert duplicate.status_code == 422
    assert zero.status_code == 422


def test_salesman_cannot_set_a_price(client, add_user, login):
    add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    token = login("sam@example.com")

    response = client.put(
        "/price-lists/hotel/items",
        headers=_headers(token),
        json={"sku": "WL-100", "unit_price": "1"},
    )

    assert response.status_code == 403


def test_unknown_order_is_404(client, add_user, login):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")

    response = client.get("/orders/999", headers=_headers(token))

    assert response.status_code == 404
