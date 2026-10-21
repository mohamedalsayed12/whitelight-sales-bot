from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PriceList, PriceListItem, PriceListName, Product
from app.services.orders import ProductNotFound


class PriceListNotFound(Exception):
    """Hotel and restaurant are created by the migration. Anything else is missing."""


def set_unit_price(
    db: Session,
    price_list_name: PriceListName,
    sku: str,
    unit_price: Decimal,
) -> PriceListItem:
    """Save the price used the next time a salesman orders this product."""
    price_list = db.scalar(select(PriceList).where(PriceList.name == price_list_name))
    if price_list is None:
        raise PriceListNotFound
    product = db.scalar(select(Product).where(Product.sku == sku))
    if product is None:
        raise ProductNotFound(sku)

    item = db.scalar(
        select(PriceListItem).where(
            PriceListItem.price_list_id == price_list.id,
            PriceListItem.product_id == product.id,
        )
    )
    if item is None:
        item = PriceListItem(
            price_list_id=price_list.id,
            product_id=product.id,
            unit_price=unit_price,
        )
        db.add(item)
    else:
        item.unit_price = unit_price
    db.commit()
    db.refresh(item)
    return item
