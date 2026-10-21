from decimal import Decimal

from app.database import SessionLocal
from app.models import Client, ClientType, Product, UserRole


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_product(sku: str, name: str, stock: str = "10") -> None:
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
                active=True,
            )
        )
        db.commit()
    finally:
        db.close()


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


def _set_price(client, token: str, sku: str, price: str, price_list: str = "hotel") -> None:
    response = client.put(
        f"/price-lists/{price_list}/items",
        headers=_headers(token),
        json={"sku": sku, "unit_price": price},
    )
    assert response.status_code == 200, response.text


def _assign_list(client, token: str, client_id: int) -> None:
    response = client.patch(
        f"/clients/{client_id}",
        headers=_headers(token),
        json={"price_list": "hotel"},
    )
    assert response.status_code == 200, response.text


def _quote(client, token: str, client_id: int, lines: list[dict] | None = None, valid_until: str = "2099-12-31"):
    if lines is None:
        lines = [{"sku": "WL-100", "quantity": "4"}]
    return client.post(
        "/quotes",
        headers=_headers(token),
        json={"client_id": client_id, "valid_until": valid_until, "lines": lines},
    )


def test_quote_requires_a_token(client):
    response = client.post(
        "/quotes",
        json={"client_id": 1, "valid_until": "2099-12-31", "lines": [{"sku": "WL-100", "quantity": "1"}]},
    )

    assert response.status_code == 401


def test_manager_cannot_create_a_quote(client, add_user, login):
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    token = login("manager@example.com")

    response = _quote(client, token, 1)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only a salesman can create a quote"


def test_salesman_quotes_at_the_price_list_price(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp")
    _add_product("WL-200", "Bath towel")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _set_price(client, manager, "WL-200", "1.250")
    _assign_list(client, manager, client_id)

    created = _quote(
        client,
        salesman,
        client_id,
        lines=[
            {"sku": "WL-100", "quantity": "4"},
            {"sku": "WL-200", "quantity": "1"},
        ],
    )

    assert created.status_code == 201
    body = created.json()
    assert body["valid_until"] == "2099-12-31"
    assert body["salesman_id"] == sam.id
    assert body["total"] == "11.250"
    assert body["lines"] == [
        {"sku": "WL-100", "quantity": "4.000", "unit_price": "2.500"},
        {"sku": "WL-200", "quantity": "1.000", "unit_price": "1.250"},
    ]
    stock = client.get("/stock", params={"q": "WL-100"}, headers=_headers(salesman))
    assert stock.json()[0]["available"] == "10.000"


def test_a_later_price_change_does_not_change_the_quote(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)
    created = _quote(client, salesman, client_id)
    _set_price(client, manager, "WL-100", "9.000")

    fetched = client.get(f"/quotes/{created.json()['id']}", headers=_headers(salesman))

    assert fetched.status_code == 200
    assert fetched.json()["lines"][0]["unit_price"] == "2.500"
    assert fetched.json()["total"] == "10.000"


def test_quote_pdf_includes_the_client_and_the_total(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp")
    client_id = _add_client("Gulf Hotel", sam.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)
    quote_id = _quote(client, salesman, client_id).json()["id"]

    response = client.get(f"/quotes/{quote_id}/pdf", headers=_headers(salesman))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="quote-{quote_id}.pdf"'
    text = response.content.decode("latin-1")
    assert text.startswith("%PDF")
    assert "Gulf Hotel" in text
    assert "WL-100" in text
    assert "Floor lamp" in text
    assert "Total: 10.000 BHD" in text
    assert "Valid until: 2099-12-31" in text


def test_salesman_cannot_see_another_salesmans_quote(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    other_token = login("other@example.com")
    _add_product("WL-100", "Floor lamp")
    own_client = _add_client("Gulf Hotel", sam.id)
    other_client = _add_client("Marina Hotel", other.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, own_client)
    _assign_list(client, manager, other_client)
    own = _quote(client, salesman, own_client)
    theirs = _quote(client, other_token, other_client)

    hidden = client.get(f"/quotes/{theirs.json()['id']}", headers=_headers(salesman))
    hidden_pdf = client.get(f"/quotes/{theirs.json()['id']}/pdf", headers=_headers(salesman))
    visible = client.get("/quotes", headers=_headers(salesman))
    manager_list = client.get("/quotes", headers=_headers(manager))

    assert own.status_code == 201
    assert hidden.status_code == 403
    assert hidden.json()["detail"] == "You can only view your own quotes"
    assert hidden_pdf.status_code == 403
    assert [row["id"] for row in visible.json()] == [own.json()["id"]]
    assert {row["id"] for row in manager_list.json()} == {own.json()["id"], theirs.json()["id"]}


def test_salesman_cannot_quote_for_someone_elses_client(client, add_user, login):
    add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    other = add_user(email="other@example.com", role=UserRole.salesman, full_name="Other")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp")
    client_id = _add_client("Marina Hotel", other.id)
    _set_price(client, manager, "WL-100", "2.500")
    _assign_list(client, manager, client_id)

    response = _quote(client, salesman, client_id)

    assert response.status_code == 403
    assert response.json()["detail"] == "You can only quote for clients assigned to you"


def test_quote_rejects_a_missing_price_an_unknown_product_and_a_past_date(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    salesman = login("sam@example.com")
    _add_product("WL-100", "Floor lamp")
    client_id = _add_client("Gulf Hotel", sam.id)

    no_list = _quote(client, salesman, client_id)
    _assign_list(client, manager, client_id)
    _set_price(client, manager, "WL-100", "2.500", price_list="restaurant")
    wrong_list = _quote(client, salesman, client_id)
    missing = _quote(client, salesman, client_id, lines=[{"sku": "NO-SUCH", "quantity": "1"}])
    expired = _quote(client, salesman, client_id, valid_until="2000-01-01")

    assert no_list.status_code == 422
    assert no_list.json()["detail"] == "Client has no price list"
    assert wrong_list.status_code == 422
    assert wrong_list.json()["detail"] == "WL-100 is not on the hotel price list"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Product NO-SUCH not found"
    assert expired.status_code == 422
    assert expired.json()["detail"] == "valid_until cannot be in the past"


def test_duplicate_line_is_422_and_unknown_quote_is_404(client, add_user, login):
    sam = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    salesman = login("sam@example.com")
    manager = login("manager@example.com")
    client_id = _add_client("Gulf Hotel", sam.id)

    duplicate = _quote(
        client,
        salesman,
        client_id,
        lines=[{"sku": "WL-100", "quantity": "1"}, {"sku": "WL-100", "quantity": "1"}],
    )
    missing = client.get("/quotes/999", headers=_headers(manager))

    assert duplicate.status_code == 422
    assert missing.status_code == 404
