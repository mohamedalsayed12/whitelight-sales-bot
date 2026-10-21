from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import ReorderItemOut
from app.services.auth import get_current_user
from app.services.stock import ReorderItem, reorder_list

router = APIRouter(tags=["reorder"])


def _require_manager(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager or admin can view the reorder list",
        )
    return current_user


def _to_out(item: ReorderItem) -> ReorderItemOut:
    return ReorderItemOut(
        sku=item.sku,
        name=item.name,
        stock_on_hand=item.stock_on_hand,
        available=item.available,
        reorder_level=item.reorder_level,
        on_order=item.on_order,
    )


@router.get("/reorder", response_model=list[ReorderItemOut])
def reorder(
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> list[ReorderItemOut]:
    return [_to_out(item) for item in reorder_list(db)]
