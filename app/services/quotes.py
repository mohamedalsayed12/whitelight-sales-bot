from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, Product, Quote, QuoteLine, User, UserRole, utcnow
from app.services.accounts import ClientNotAllowed, ClientNotFound, bahrain_today
from app.services.orders import InvalidOrder, NewLine, price_lines

PLACES = Decimal("0.001")


class QuoteNotFound(Exception):
    """No quote has this id."""


class QuoteNotAllowed(Exception):
    """A salesman asked for another salesman's quote."""


class InvalidQuote(Exception):
    """The quote cannot be priced, or valid_until is already past."""


@dataclass
class QuoteLineView:
    sku: str
    name: str
    quantity: Decimal
    unit_price: Decimal


@dataclass
class QuoteView:
    id: int
    client_id: int
    client_name: str
    salesman_id: int
    salesman_name: str
    valid_until: date
    lines: list[QuoteLineView]

    @property
    def total(self) -> Decimal:
        amount = sum((line.quantity * line.unit_price for line in self.lines), Decimal("0"))
        return amount.quantize(PLACES)


def create_quote(
    db: Session,
    salesman: User,
    client_id: int,
    valid_until: date,
    lines: list[NewLine],
) -> QuoteView:
    """Save a quote at the client's current prices.

    A quote does not reserve stock. The unit price is copied onto the line,
    so a later price change does not rewrite it.
    """
    client = db.get(Client, client_id)
    if client is None:
        raise ClientNotFound
    if client.assigned_salesman_id != salesman.id:
        raise ClientNotAllowed
    if valid_until < bahrain_today():
        raise InvalidQuote("valid_until cannot be in the past")
    if client.price_list is None:
        raise InvalidQuote("Client has no price list")

    try:
        priced = price_lines(db, client.price_list, lines)
    except InvalidOrder as exc:
        raise InvalidQuote(str(exc)) from None

    quote = Quote(
        client_id=client.id,
        salesman_id=salesman.id,
        valid_until=valid_until,
        created_at=utcnow(),
    )
    db.add(quote)
    db.flush()
    for product, quantity, unit_price in priced:
        db.add(
            QuoteLine(
                quote_id=quote.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    db.commit()
    return _view(db, quote)


def list_quotes(db: Session, user: User) -> list[QuoteView]:
    query = select(Quote).order_by(Quote.id.desc())
    if user.role == UserRole.salesman:
        query = query.where(Quote.salesman_id == user.id)
    return [_view(db, quote) for quote in db.scalars(query)]


def get_quote(db: Session, user: User, quote_id: int) -> QuoteView:
    quote = db.get(Quote, quote_id)
    if quote is None:
        raise QuoteNotFound
    if user.role == UserRole.salesman and quote.salesman_id != user.id:
        raise QuoteNotAllowed
    return _view(db, quote)


def _view(db: Session, quote: Quote) -> QuoteView:
    client = db.get(Client, quote.client_id)
    salesman = db.get(User, quote.salesman_id)
    rows = db.execute(
        select(QuoteLine, Product)
        .join(Product, QuoteLine.product_id == Product.id)
        .where(QuoteLine.quote_id == quote.id)
        .order_by(QuoteLine.id)
    ).all()
    return QuoteView(
        id=quote.id,
        client_id=quote.client_id,
        client_name="" if client is None else client.name,
        salesman_id=quote.salesman_id,
        salesman_name="" if salesman is None else salesman.full_name,
        valid_until=quote.valid_until,
        lines=[
            QuoteLineView(
                sku=product.sku,
                name=product.name,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
            for line, product in rows
        ],
    )
