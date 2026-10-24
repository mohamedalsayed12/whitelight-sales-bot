import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Client, ClientType, Invoice, Product

MONEY_PLACES = Decimal("0.001")
STOCK_COLUMNS = {"sku", "name", "quantity"}
INVOICE_COLUMNS = {
    "client",
    "invoice_number",
    "issue_date",
    "due_date",
    "amount",
    "amount_paid",
}


class InvalidImportFile(Exception):
    """The upload itself is unusable. Callers turn this into HTTP 422."""


@dataclass
class RowError:
    row: int
    message: str


@dataclass
class ImportResult:
    imported: int
    failed: int
    errors: list[RowError]


def import_stock(db: Session, content: bytes) -> ImportResult:
    """Set stock from a Tally stock summary.

    The quantity replaces stock_on_hand. Importing the same file again
    leaves the same quantities, and products missing from the file are
    left alone.
    """
    parsed, errors = _read_rows(content, STOCK_COLUMNS)
    ready: list[tuple[int, str, str, Decimal]] = []
    seen: set[str] = set()
    for row_number, row in parsed:
        try:
            sku, name, quantity = _parse_stock_row(row)
        except ValueError as exc:
            errors.append(RowError(row_number, str(exc)))
            continue
        if sku in seen:
            errors.append(RowError(row_number, "duplicate sku in this file"))
            continue
        seen.add(sku)
        ready.append((row_number, sku, name, quantity))

    for _row_number, sku, name, quantity in ready:
        _upsert_product(db, sku, name, quantity)
    db.commit()
    return ImportResult(imported=len(ready), failed=len(errors), errors=errors)


def import_receivables(db: Session, content: bytes) -> ImportResult:
    """Create or update invoices from a Tally receivables export.

    The invoice number is the identity. Importing the same file again
    updates those invoices instead of creating a second copy.
    """
    parsed, errors = _read_rows(content, INVOICE_COLUMNS)
    ready: list[tuple[str, str, date, date, Decimal, Decimal]] = []
    seen: set[str] = set()
    for row_number, row in parsed:
        try:
            invoice = _parse_invoice_row(row)
        except ValueError as exc:
            errors.append(RowError(row_number, str(exc)))
            continue
        number = invoice[1]
        if number in seen:
            errors.append(RowError(row_number, "duplicate invoice_number in this file"))
            continue
        seen.add(number)
        ready.append(invoice)

    for client_name, number, issue_date, due_date, amount, amount_paid in ready:
        client = _get_or_create_client(db, client_name)
        _upsert_invoice(db, client, number, issue_date, due_date, amount, amount_paid)
    db.commit()
    return ImportResult(imported=len(ready), failed=len(errors), errors=errors)


def _read_rows(content: bytes, required: set[str]) -> tuple[list[tuple[int, dict[str, str]]], list[RowError]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidImportFile("The file must be a UTF-8 CSV.") from exc
    if text.strip() == "":
        raise InvalidImportFile("The file is empty.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise InvalidImportFile("The CSV needs a header row.")

    headers = {_header(name) for name in reader.fieldnames}
    missing = sorted(required - headers)
    if missing:
        raise InvalidImportFile("Missing columns: " + ", ".join(missing))

    rows: list[tuple[int, dict[str, str]]] = []
    for row_number, raw in enumerate(reader, start=2):
        row = {
            _header(key): (value or "").strip()
            for key, value in raw.items()
            if key is not None
        }
        if all(value == "" for value in row.values()):
            continue
        rows.append((row_number, row))
    return rows, []


def _header(name: str | None) -> str:
    return (name or "").strip().lower().replace(" ", "_")


def _parse_stock_row(row: dict[str, str]) -> tuple[str, str, Decimal]:
    sku = row.get("sku", "")
    name = row.get("name", "")
    if sku == "":
        raise ValueError("sku is required")
    if name == "":
        raise ValueError("name is required")
    if len(sku) > 64:
        raise ValueError("sku is too long")
    if len(name) > 255:
        raise ValueError("name is too long")
    quantity = _parse_decimal(row.get("quantity", ""), "quantity")
    return sku, name, quantity


def _parse_invoice_row(
    row: dict[str, str],
) -> tuple[str, str, date, date, Decimal, Decimal]:
    client_name = row.get("client", "")
    number = row.get("invoice_number", "")
    if client_name == "":
        raise ValueError("client is required")
    if number == "":
        raise ValueError("invoice_number is required")
    if len(client_name) > 255:
        raise ValueError("client is too long")
    if len(number) > 64:
        raise ValueError("invoice_number is too long")

    issue_date = _parse_date(row.get("issue_date", ""), "issue_date")
    due_date = _parse_date(row.get("due_date", ""), "due_date")
    if due_date < issue_date:
        raise ValueError("due_date cannot be before issue_date")

    amount = _parse_decimal(row.get("amount", ""), "amount")
    amount_paid = _parse_decimal(row.get("amount_paid", ""), "amount_paid")
    if amount_paid > amount:
        raise ValueError("amount_paid cannot be greater than amount")
    return client_name, number, issue_date, due_date, amount, amount_paid


def _parse_decimal(value: str, field_name: str) -> Decimal:
    if value == "":
        raise ValueError(f"{field_name} is required")
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"{field_name} must be a number") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field_name} cannot be negative" if number < 0 else f"{field_name} must be a number")
    exponent = number.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -3:
        raise ValueError(f"{field_name} can have at most 3 decimal places")
    return number.quantize(MONEY_PLACES)


def _parse_date(value: str, field_name: str) -> date:
    if value == "":
        raise ValueError(f"{field_name} is required")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from None


def _upsert_product(db: Session, sku: str, name: str, quantity: Decimal) -> None:
    product = db.scalar(select(Product).where(Product.sku == sku))
    if product is None:
        db.add(
            Product(
                sku=sku,
                name=name,
                category="",
                unit="pcs",
                stock_on_hand=quantity,
                reorder_level=Decimal("0"),
                active=True,
            )
        )
        return
    product.name = name
    product.stock_on_hand = quantity


def _get_or_create_client(db: Session, name: str) -> Client:
    client = db.scalar(select(Client).where(func.lower(Client.name) == name.lower()))
    if client is not None:
        return client
    client = Client(
        name=name,
        type=ClientType.other,
        price_list=None,
        credit_limit=Decimal("0"),
        phone="",
    )
    db.add(client)
    db.flush()
    return client


def _upsert_invoice(
    db: Session,
    client: Client,
    number: str,
    issue_date: date,
    due_date: date,
    amount: Decimal,
    amount_paid: Decimal,
) -> None:
    invoice = db.scalar(select(Invoice).where(Invoice.number == number))
    if invoice is None:
        db.add(
            Invoice(
                client_id=client.id,
                number=number,
                issue_date=issue_date,
                due_date=due_date,
                amount=amount,
                amount_paid=amount_paid,
            )
        )
        return
    invoice.client_id = client.id
    invoice.issue_date = issue_date
    invoice.due_date = due_date
    invoice.amount = amount
    invoice.amount_paid = amount_paid
