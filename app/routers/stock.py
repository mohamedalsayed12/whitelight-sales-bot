from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import StockItem
from app.services.auth import get_current_user
from app.services.stock import SearchTermRequired, search_stock

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("", response_model=list[StockItem])
def find_stock(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> list[StockItem]:
    try:
        matches = search_stock(db, q)
    except SearchTermRequired:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search term is required",
        ) from None
    return [
        StockItem(
            sku=match.sku,
            name=match.name,
            unit=match.unit,
            available=match.available,
            low_stock=match.low_stock,
        )
        for match in matches
    ]
