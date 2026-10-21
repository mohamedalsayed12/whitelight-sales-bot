from decimal import Decimal

from app.database import SessionLocal
from app.models import Product, UserRole


def _login(add_user, login, role=UserRole.salesman, email="sam@example.com") -> str:
    add_user(email=email, role=role, full_name="Sam Sales")
    return login(email)


def _add_product(
    *,
    sku: str,
    name: str,
    stock: str,
    reorder: str = "0",
    unit: str = "pcs",
    active: bool = True,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            Product(
                sku=sku,
                name=name,
                category="",
                unit=unit,
                stock_on_hand=Decimal(stock),
                reorder_level=Decimal(reorder),
                active=active,
            )
        )
        db.commit()
    finally:
        db.close()


def test_stock_search_requires_a_token(client):
    response = client.get("/stock", params={"q": "lamp"})

    assert response.status_code == 401


def test_stock_search_requires_a_term(client, add_user, login):
    token = _login(add_user, login)

    missing = client.get("/stock", headers={"Authorization": f"Bearer {token}"})
    blank = client.get("/stock", params={"q": "   "}, headers={"Authorization": f"Bearer {token}"})

    assert missing.status_code == 422
    assert blank.status_code == 422
    assert blank.json()["detail"] == "Search term is required"


def test_salesman_can_search_stock_by_name_or_sku(client, add_user, login):
    token = _login(add_user, login)
    _add_product(sku="WL-100", name="Floor lamp", stock="12", reorder="5", unit="pcs")
    _add_product(sku="WL-200", name="Bath towel", stock="2", reorder="2", unit="pcs")
    _add_product(sku="WL-300", name="Old lamp", stock="4", reorder="1", active=False)
    headers = {"Authorization": f"Bearer {token}"}

    by_name = client.get("/stock", params={"q": "LAMP"}, headers=headers)
    by_sku = client.get("/stock", params={"q": "wl-200"}, headers=headers)

    assert by_name.status_code == 200
    assert by_name.json() == [
        {
            "sku": "WL-100",
            "name": "Floor lamp",
            "unit": "pcs",
            "available": "12.000",
            "low_stock": False,
        }
    ]
    assert by_sku.status_code == 200
    assert by_sku.json() == [
        {
            "sku": "WL-200",
            "name": "Bath towel",
            "unit": "pcs",
            "available": "2.000",
            "low_stock": True,
        }
    ]


def test_stock_search_treats_underscore_as_a_normal_character(client, add_user, login):
    token = _login(add_user, login)
    _add_product(sku="A_B", name="Underscore item", stock="1")
    _add_product(sku="AXB", name="Other item", stock="1")

    response = client.get(
        "/stock",
        params={"q": "A_B"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [item["sku"] for item in response.json()] == ["A_B"]


def test_stock_search_with_no_matches_returns_an_empty_list(client, add_user, login):
    token = _login(add_user, login)

    response = client.get(
        "/stock",
        params={"q": "missing"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == []
