from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Cheque, Order, OrderLine, OrderStatus
from app.services import accounts
from app.services.stock import PLACES, ReorderItem, reorder_list


@dataclass
class DailySummary:
    day: date
    orders_today: int
    orders_total: Decimal
    cheques_collected: Decimal
    total_overdue: Decimal
    reorder: list[ReorderItem]


def daily_summary(db: Session) -> DailySummary:
    """What the CEO needs for today in Asia/Bahrain.

    Orders are those created today, except cancelled ones. Cheques collected
    are those a salesman logged today, whatever status they have now. Overdue
    is money due today or earlier. There is no separate cash figure.
    """
    today = accounts.bahrain_today()
    start = datetime.combine(today, time.min, tzinfo=accounts.BAHRAIN)
    end = start + timedelta(days=1)
    placed = (
        Order.created_at >= start,
        Order.created_at < end,
        Order.status != OrderStatus.cancelled,
    )
    orders_today = db.scalar(select(func.count(Order.id)).where(*placed)) or 0
    orders_total = db.scalar(
        select(func.coalesce(func.sum(OrderLine.quantity * OrderLine.unit_price), 0))
        .join(Order, OrderLine.order_id == Order.id)
        .where(*placed)
    )
    collected = db.scalar(
        select(func.coalesce(func.sum(Cheque.amount), 0)).where(
            Cheque.collected_at >= start,
            Cheque.collected_at < end,
        )
    )
    return DailySummary(
        day=today,
        orders_today=int(orders_today),
        orders_total=_money(orders_total),
        cheques_collected=_money(collected),
        total_overdue=accounts.total_overdue(db),
        reorder=reorder_list(db),
    )


def _money(value: Decimal | int) -> Decimal:
    return Decimal(value).quantize(PLACES)
