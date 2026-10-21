from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PriceListName, User, UserRole
from app.schemas import PriceInput
from app.services.auth import get_current_user
from app.services.orders import ProductNotFound
from app.services.prices import PriceListNotFound, set_unit_price

router = APIRouter(prefix="/price-lists", tags=["prices"])


def _require_manager(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager or admin can set prices",
        )
    return current_user


@router.put("/{price_list}/items", status_code=status.HTTP_200_OK)
def put_price(
    price_list: PriceListName,
    body: PriceInput,
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> dict[str, str]:
    try:
        item = set_unit_price(db, price_list, body.sku, body.unit_price)
    except PriceListNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price list not found") from None
    except ProductNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {exc.sku} not found",
        ) from None
    return {"sku": body.sku, "price_list": price_list.value, "unit_price": str(item.unit_price)}
