from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Client, ClientType, Invoice, Product, UserRole

FIXTURES = Path(__file__).parent / "fixtures"


def _upload(client, path: str, token: str | None, content: bytes, filename: str = "upload.csv"):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        path,
        headers=headers,
        files={"file": (filename, content, "text/csv")},
    )


def _manager(add_user, login, email: str = "manager@example.com") -> str:
    add_user(email=email, role=UserRole.manager, full_name="Maha Manager")
    return login(email)


def test_stock_import_requires_a_token(client):
    response = _upload(client, "/imports/stock", None, b"sku,name,quantity\n")

    assert response.status_code == 401


def test_receivables_import_requires_a_token(client):
    response = _upload(client, "/imports/receivables", None, b"client,invoice_number\n")

    assert response.status_code == 401


def test_salesman_cannot_import(client, add_user, login):
    add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    token = login("sam@example.com")
    stock = (FIXTURES / "stock.csv").read_bytes()

    stock_response = _upload(client, "/imports/stock", token, stock)
    receivables_response = _upload(
        client,
        "/imports/receivables",
        token,
        (FIXTURES / "receivables.csv").read_bytes(),
    )

    assert stock_response.status_code == 403
    assert receivables_response.status_code == 403
    assert stock_response.json()["detail"] == "Only a manager or admin can import Tally files"
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(Product)) == 0
        assert db.scalar(select(func.count()).select_from(Invoice)) == 0
    finally:
        db.close()


def test_manager_imports_the_sample_stock_file(client, add_user, login):
    token = _manager(add_user, login)

    response = _upload(client, "/imports/stock", token, (FIXTURES / "stock.csv").read_bytes())

    assert response.status_code == 200
    assert response.json() == {"imported": 2, "failed": 0, "errors": []}
    db = SessionLocal()
    try:
        lamp = db.scalar(select(Product).where(Product.sku == "WL-100"))
        towel = db.scalar(select(Product).where(Product.sku == "WL-200"))
        assert lamp is not None
        assert lamp.name == "Floor lamp"
        assert lamp.stock_on_hand == Decimal("12")
        assert lamp.unit == "pcs"
        assert lamp.category == ""
        assert towel is not None
        assert towel.stock_on_hand == Decimal("40.500")
    finally:
        db.close()


def test_reimporting_stock_replaces_quantity_and_does_not_duplicate(client, add_user, login):
    token = _manager(add_user, login)
    original = (FIXTURES / "stock.csv").read_bytes()
    _upload(client, "/imports/stock", token, original)

    db = SessionLocal()
    try:
        lamp = db.scalar(select(Product).where(Product.sku == "WL-100"))
        lamp.category = "Lighting"
        lamp.unit = "box"
        lamp.reorder_level = Decimal("4")
        lamp.active = False
        db.commit()
    finally:
        db.close()

    updated = b"sku,name,quantity\nWL-100,Floor lamp large,3\n"
    response = _upload(client, "/imports/stock", token, updated)

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    db = SessionLocal()
    try:
        products = db.scalars(select(Product).order_by(Product.sku)).all()
        assert [product.sku for product in products] == ["WL-100", "WL-200"]
        lamp = products[0]
        assert lamp.name == "Floor lamp large"
        assert lamp.stock_on_hand == Decimal("3")
        assert lamp.category == "Lighting"
        assert lamp.unit == "box"
        assert lamp.reorder_level == Decimal("4")
        assert lamp.active is False
        assert products[1].stock_on_hand == Decimal("40.500")
    finally:
        db.close()


def test_admin_can_import_stock(client, add_user, login):
    add_user(email="admin@example.com", role=UserRole.admin, full_name="Ada Admin")
    token = login("admin@example.com")

    response = _upload(client, "/imports/stock", token, b"SKU,Name,Quantity\nWL-1,Chair,1\n")

    assert response.status_code == 200
    assert response.json()["imported"] == 1


def test_stock_import_saves_good_rows_and_reports_bad_ones(client, add_user, login):
    token = _manager(add_user, login)
    content = (
        "sku,name,quantity\n"
        "WL-1,Chair,2\n"
        "WL-2,Table,-1\n"
        "WL-1,Chair again,4\n"
        ",Missing sku,1\n"
        "WL-3,Too fine,1.2345\n"
    ).encode()

    response = _upload(client, "/imports/stock", token, content)

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["failed"] == 4
    assert body["errors"] == [
        {"row": 3, "message": "quantity cannot be negative"},
        {"row": 4, "message": "duplicate sku in this file"},
        {"row": 5, "message": "sku is required"},
        {"row": 6, "message": "quantity can have at most 3 decimal places"},
    ]
    db = SessionLocal()
    try:
        chair = db.scalar(select(Product).where(Product.sku == "WL-1"))
        assert chair is not None
        assert chair.stock_on_hand == Decimal("2")
        assert chair.name == "Chair"
    finally:
        db.close()


def test_stock_import_rejects_a_file_without_the_required_columns(client, add_user, login):
    token = _manager(add_user, login)

    response = _upload(client, "/imports/stock", token, b"sku,name\nWL-1,Chair\n")

    assert response.status_code == 422
    assert response.json()["detail"] == "Missing columns: quantity"


def test_stock_import_rejects_a_file_that_is_not_utf8(client, add_user, login):
    token = _manager(add_user, login)

    response = _upload(client, "/imports/stock", token, b"\xff\xfe")

    assert response.status_code == 422
    assert response.json()["detail"] == "The file must be a UTF-8 CSV."


def test_manager_imports_the_sample_receivables_file(client, add_user, login):
    token = _manager(add_user, login)

    response = _upload(
        client,
        "/imports/receivables",
        token,
        (FIXTURES / "receivables.csv").read_bytes(),
    )

    assert response.status_code == 200
    assert response.json() == {"imported": 2, "failed": 0, "errors": []}
    db = SessionLocal()
    try:
        client_row = db.scalar(select(Client).where(Client.name == "Gulf Hotel"))
        invoice = db.scalar(select(Invoice).where(Invoice.number == "INV-1001"))
        assert client_row is not None
        assert client_row.type == ClientType.other
        assert client_row.price_list is None
        assert client_row.credit_limit == Decimal("0")
        assert invoice is not None
        assert invoice.client_id == client_row.id
        assert invoice.issue_date == date(2026, 9, 1)
        assert invoice.due_date == date(2026, 10, 1)
        assert invoice.amount == Decimal("150.500")
        assert invoice.amount_paid == Decimal("50")
    finally:
        db.close()


def test_reimporting_receivables_updates_the_same_invoice(client, add_user, login):
    token = _manager(add_user, login)
    _upload(
        client,
        "/imports/receivables",
        token,
        (FIXTURES / "receivables.csv").read_bytes(),
    )
    updated = (
        "Client,Invoice Number,Issue Date,Due Date,Amount,Amount Paid\n"
        "gulf hotel,INV-1001,2026-09-01,2026-10-01,150.500,150.500\n"
    ).encode()

    response = _upload(client, "/imports/receivables", token, updated)

    assert response.status_code == 200
    assert response.json() == {"imported": 1, "failed": 0, "errors": []}
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(Client)) == 2
        assert db.scalar(select(func.count()).select_from(Invoice)) == 2
        hotel = db.scalar(select(Client).where(func.lower(Client.name) == "gulf hotel"))
        invoice = db.scalar(select(Invoice).where(Invoice.number == "INV-1001"))
        assert hotel.name == "Gulf Hotel"
        assert invoice.amount_paid == Decimal("150.500")
        assert invoice.client_id == hotel.id
    finally:
        db.close()


def test_receivables_import_reports_bad_rows(client, add_user, login):
    token = _manager(add_user, login)
    content = (
        "client,invoice_number,issue_date,due_date,amount,amount_paid\n"
        "Gulf Hotel,INV-1,2026-10-01,2026-09-01,10.000,0\n"
        "Gulf Hotel,INV-2,2026-10-01,2026-10-15,10.000,11\n"
        "Gulf Hotel,INV-3,not-a-date,2026-10-15,10,0\n"
        'Gulf Hotel,INV-4,2026-10-01,2026-10-15,"1,250.000",0\n'
    ).encode()

    response = _upload(client, "/imports/receivables", token, content)

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["errors"] == [
        {"row": 2, "message": "due_date cannot be before issue_date"},
        {"row": 3, "message": "amount_paid cannot be greater than amount"},
        {"row": 4, "message": "issue_date must be YYYY-MM-DD"},
    ]
    db = SessionLocal()
    try:
        invoice = db.scalar(select(Invoice).where(Invoice.number == "INV-4"))
        assert invoice is not None
        assert invoice.amount == Decimal("1250.000")
    finally:
        db.close()
