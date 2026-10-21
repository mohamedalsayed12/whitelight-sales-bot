from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Client, PriceListName
from app.services.accounts import ClientNotFound


def update_client_terms(
    db: Session,
    client_id: int,
    *,
    price_list: PriceListName | None,
    credit_limit: Decimal | None,
) -> Client:
    """Set the list used to price orders, or the credit limit used for on_hold."""
    client = db.get(Client, client_id)
    if client is None:
        raise ClientNotFound
    if price_list is not None:
        client.price_list = price_list
    if credit_limit is not None:
        client.credit_limit = credit_limit
    db.commit()
    db.refresh(client)
    return client
