from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import DailySummaryOut, ReorderItemOut
from app.services.auth import get_current_user
from app.services.summary import DailySummary, daily_summary

router = APIRouter(prefix="/summary", tags=["summary"])


def _require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an admin can view the daily summary",
        )
    return current_user


def _summary_out(summary: DailySummary) -> DailySummaryOut:
    return DailySummaryOut(
        day=summary.day,
        orders_today=summary.orders_today,
        orders_total=summary.orders_total,
        cheques_collected=summary.cheques_collected,
        total_overdue=summary.total_overdue,
        reorder=[
            ReorderItemOut(
                sku=item.sku,
                name=item.name,
                stock_on_hand=item.stock_on_hand,
                available=item.available,
                reorder_level=item.reorder_level,
                on_order=item.on_order,
            )
            for item in summary.reorder
        ],
    )


@router.get("", response_model=DailySummaryOut)
def today(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[User, Depends(_require_admin)],
) -> DailySummaryOut:
    return _summary_out(daily_summary(db))
