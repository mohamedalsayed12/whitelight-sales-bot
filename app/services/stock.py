from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, OrderStatus, Product

# These orders still need the goods, so they reduce what a salesman can sell.
OPEN_ORDER_STATUSES = (
    OrderStatus.submitted,
    OrderStatus.approved,
    OrderStatus.out_for_delivery,
)
PLACES = Decimal("0.001")


class SearchTermRequired(Exception):
    """The search text was blank. Callers turn this into HTTP 422."""


@dataclass
class StockMatch:
    sku: str
    name: str
    unit: str
    available: Decimal
    low_stock: bool


def available_quantity(db: Session, product: Product) -> Decimal:
    """Stock still free to sell.

    Tally sets stock_on_hand. Open orders reserve some of it until they are
    delivered or cancelled. Delivery then reduces stock_on_hand itself.
    """
    reserved = db.scalar(
        select(func.coalesce(func.sum(OrderLine.quantity), 0))
        .join(Order, OrderLine.order_id == Order.id)
        .where(
            OrderLine.product_id == product.id,
            Order.status.in_(OPEN_ORDER_STATUSES),
        )
    )
    return (product.stock_on_hand - Decimal(reserved)).quantize(PLACES)


def search_stock(db: Session, term: str) -> list[StockMatch]:
    """Find active products whose sku or name contains the term.

    Low stock means the available quantity is at or below the reorder level.
    """
    cleaned = term.strip()
    if cleaned == "":
        raise SearchTermRequired
    # Treat % and _ as ordinary characters, not "match anything".
    escaped = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    products = db.scalars(
        select(Product)
        .where(
            Product.active.is_(True),
            or_(
                Product.sku.ilike(pattern, escape="\\"),
                Product.name.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Product.sku)
    )
    matches: list[StockMatch] = []
    for product in products:
        available = available_quantity(db, product)
        matches.append(
            StockMatch(
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                available=available,
                low_stock=available <= product.reorder_level,
            )
        )
    return matches


@dataclass
class ReorderItem:
    sku: str
    name: str
    stock_on_hand: Decimal
    available: Decimal
    reorder_level: Decimal
    on_order: Decimal


def reorder_list(db: Session) -> list[ReorderItem]:
    """Active products whose available quantity is at or below the reorder level.

    on_order is the quantity still reserved by open orders. Available is
    stock_on_hand minus that quantity, the same figure stock search uses.
    """
    reserved_rows = db.execute(
        select(OrderLine.product_id, func.coalesce(func.sum(OrderLine.quantity), 0))
        .join(Order, OrderLine.order_id == Order.id)
        .where(Order.status.in_(OPEN_ORDER_STATUSES))
        .group_by(OrderLine.product_id)
    ).all()
    reserved = {product_id: Decimal(quantity) for product_id, quantity in reserved_rows}
    items: list[ReorderItem] = []
    products = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.sku))
    for product in products:
        on_order = reserved.get(product.id, Decimal("0")).quantize(PLACES)
        available = (product.stock_on_hand - on_order).quantize(PLACES)
        if available <= product.reorder_level:
            items.append(
                ReorderItem(
                    sku=product.sku,
                    name=product.name,
                    stock_on_hand=product.stock_on_hand.quantize(PLACES),
                    available=available,
                    reorder_level=product.reorder_level.quantize(PLACES),
                    on_order=on_order,
                )
            )
    return items
