from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Client,
    Order,
    OrderHistory,
    OrderLine,
    OrderStatus,
    PriceList,
    PriceListItem,
    PriceListName,
    Product,
    User,
    UserRole,
    utcnow,
)
from app.services.accounts import ClientNotAllowed, ClientNotFound, on_hold_warning
from app.services.stock import available_quantity

NEXT_STATUS = {
    OrderStatus.submitted: {OrderStatus.approved, OrderStatus.cancelled},
    OrderStatus.approved: {OrderStatus.out_for_delivery, OrderStatus.cancelled},
    OrderStatus.out_for_delivery: {OrderStatus.delivered, OrderStatus.cancelled},
    OrderStatus.delivered: set(),
    OrderStatus.cancelled: set(),
}


class ProductNotFound(Exception):
    def __init__(self, sku: str) -> None:
        self.sku = sku
        super().__init__(sku)


class OrderNotFound(Exception):
    """No order has this id."""


class OrderNotAllowed(Exception):
    """A salesman asked for another salesman's order."""


class NotEnoughStock(Exception):
    """One or more lines ask for more than the available quantity."""


class InvalidOrder(Exception):
    """The order cannot be priced or the status change is not allowed."""


@dataclass
class OrderLineView:
    sku: str
    quantity: Decimal
    unit_price: Decimal


@dataclass
class HistoryView:
    status: OrderStatus
    changed_by_id: int
    changed_at: datetime


@dataclass
class OrderView:
    id: int
    client_id: int
    salesman_id: int
    status: OrderStatus
    warning: str | None
    lines: list[OrderLineView]
    history: list[HistoryView]


@dataclass
class NewLine:
    sku: str
    quantity: Decimal


def submit_order(db: Session, salesman: User, client_id: int, lines: list[NewLine]) -> OrderView:
    """Create an order at the client's current prices.

    The order is saved even when the client is on hold. The response then
    warns that a manager must approve it. Stock is reserved, not removed,
    until a manager marks the order delivered.
    """
    client = db.get(Client, client_id)
    if client is None:
        raise ClientNotFound
    if client.assigned_salesman_id != salesman.id:
        raise ClientNotAllowed
    if client.price_list is None:
        raise InvalidOrder("Client has no price list")

    priced = price_lines(db, client.price_list, lines)
    _ensure_available(db, priced)

    order = Order(
        client_id=client.id,
        salesman_id=salesman.id,
        status=OrderStatus.submitted,
    )
    db.add(order)
    db.flush()
    for product, quantity, unit_price in priced:
        db.add(
            OrderLine(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    _record(db, order, OrderStatus.submitted, salesman)
    db.commit()
    return _view(db, order)


def list_orders(db: Session, user: User) -> list[OrderView]:
    query = select(Order).order_by(Order.id.desc())
    if user.role == UserRole.salesman:
        query = query.where(Order.salesman_id == user.id)
    return [_view(db, order) for order in db.scalars(query)]


def get_order(db: Session, user: User, order_id: int) -> OrderView:
    return _view(db, _order_for_user(db, user, order_id))


def change_status(db: Session, manager: User, order_id: int, new_status: OrderStatus) -> OrderView:
    order = db.get(Order, order_id)
    if order is None:
        raise OrderNotFound
    if new_status not in NEXT_STATUS[order.status]:
        raise InvalidOrder(
            f"Cannot change an order from {order.status.value} to {new_status.value}"
        )

    rows = _lines(db, order.id)
    if new_status == OrderStatus.approved:
        _ensure_reservation_still_fits(db, rows)
    if new_status == OrderStatus.delivered:
        _take_stock(rows)

    order.status = new_status
    _record(db, order, new_status, manager)
    db.commit()
    return _view(db, order)


def price_lines(
    db: Session,
    price_list_name: PriceListName,
    lines: list[NewLine],
) -> list[tuple[Product, Decimal, Decimal]]:
    """Copy each line's price from the client's list. Quotes use this too."""
    price_list = db.scalar(select(PriceList).where(PriceList.name == price_list_name))
    if price_list is None:
        raise InvalidOrder("Client has no price list")

    priced: list[tuple[Product, Decimal, Decimal]] = []
    for line in lines:
        product = db.scalar(select(Product).where(Product.sku == line.sku))
        if product is None:
            raise ProductNotFound(line.sku)
        if not product.active:
            raise InvalidOrder(f"{line.sku} is not active")
        unit_price = db.scalar(
            select(PriceListItem.unit_price).where(
                PriceListItem.price_list_id == price_list.id,
                PriceListItem.product_id == product.id,
            )
        )
        if unit_price is None:
            raise InvalidOrder(f"{line.sku} is not on the {price_list_name.value} price list")
        priced.append((product, line.quantity, unit_price))
    return priced


def _ensure_available(db: Session, priced: list[tuple[Product, Decimal, Decimal]]) -> None:
    problems: list[str] = []
    for product, quantity, _unit_price in priced:
        available = available_quantity(db, product)
        if quantity > available:
            problems.append(
                f"Not enough stock for {product.sku}: available {available}, requested {quantity}"
            )
    if problems:
        raise NotEnoughStock("; ".join(problems))


def _ensure_reservation_still_fits(db: Session, rows: list[tuple[OrderLine, Product]]) -> None:
    """Approval fails when a newer stock import no longer covers this order."""
    problems: list[str] = []
    for line, product in rows:
        free = available_quantity(db, product) + line.quantity
        if line.quantity > free:
            problems.append(
                f"Not enough stock for {product.sku}: available {free}, requested {line.quantity}"
            )
    if problems:
        raise NotEnoughStock("; ".join(problems))


def _take_stock(rows: list[tuple[OrderLine, Product]]) -> None:
    """Delivery removes the goods from stock_on_hand.

    The order stops reserving them at the same time, so available stays down.
    The next Tally import can replace stock_on_hand with the warehouse figure.
    """
    problems: list[str] = []
    for line, product in rows:
        if product.stock_on_hand < line.quantity:
            problems.append(
                f"Not enough stock to deliver {product.sku}: "
                f"on hand {product.stock_on_hand}, requested {line.quantity}"
            )
    if problems:
        raise NotEnoughStock("; ".join(problems))
    for line, product in rows:
        product.stock_on_hand = (product.stock_on_hand - line.quantity).quantize(Decimal("0.001"))


def _order_for_user(db: Session, user: User, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise OrderNotFound
    if user.role == UserRole.salesman and order.salesman_id != user.id:
        raise OrderNotAllowed
    return order


def _record(db: Session, order: Order, status: OrderStatus, user: User) -> None:
    db.add(
        OrderHistory(
            order_id=order.id,
            status=status,
            changed_by_id=user.id,
            changed_at=utcnow(),
        )
    )


def _lines(db: Session, order_id: int) -> list[tuple[OrderLine, Product]]:
    rows = db.execute(
        select(OrderLine, Product)
        .join(Product, OrderLine.product_id == Product.id)
        .where(OrderLine.order_id == order_id)
        .order_by(OrderLine.id)
    ).all()
    return [(line, product) for line, product in rows]


def _view(db: Session, order: Order) -> OrderView:
    client = db.get(Client, order.client_id)
    warning = None
    if order.status == OrderStatus.submitted and client is not None:
        warning = on_hold_warning(db, client)
    history = db.scalars(
        select(OrderHistory).where(OrderHistory.order_id == order.id).order_by(OrderHistory.id)
    ).all()
    return OrderView(
        id=order.id,
        client_id=order.client_id,
        salesman_id=order.salesman_id,
        status=order.status,
        warning=warning,
        lines=[
            OrderLineView(sku=product.sku, quantity=line.quantity, unit_price=line.unit_price)
            for line, product in _lines(db, order.id)
        ],
        history=[
            HistoryView(
                status=entry.status,
                changed_by_id=entry.changed_by_id,
                changed_at=entry.changed_at,
            )
            for entry in history
        ],
    )
