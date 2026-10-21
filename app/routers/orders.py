from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import OrderCreate, OrderHistoryOut, OrderLineOut, OrderOut, OrderStatusChange
from app.services.accounts import ClientNotAllowed, ClientNotFound
from app.services.auth import get_current_user
from app.services.orders import (
    InvalidOrder,
    NewLine,
    NotEnoughStock,
    OrderNotAllowed,
    OrderNotFound,
    OrderView,
    ProductNotFound,
    change_status,
    get_order,
    list_orders,
    submit_order,
)

router = APIRouter(prefix="/orders", tags=["orders"])


def _require_salesman(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role != UserRole.salesman:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a salesman can submit an order",
        )
    return current_user


def _require_manager(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager or admin can change an order",
        )
    return current_user


def _to_out(order: OrderView) -> OrderOut:
    return OrderOut(
        id=order.id,
        client_id=order.client_id,
        salesman_id=order.salesman_id,
        status=order.status,
        warning=order.warning,
        lines=[
            OrderLineOut(sku=line.sku, quantity=line.quantity, unit_price=line.unit_price)
            for line in order.lines
        ],
        history=[
            OrderHistoryOut(
                status=entry.status,
                changed_by_id=entry.changed_by_id,
                changed_at=entry.changed_at,
            )
            for entry in order.history
        ],
    )


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: OrderCreate,
    db: Annotated[Session, Depends(get_db)],
    salesman: Annotated[User, Depends(_require_salesman)],
) -> OrderOut:
    try:
        order = submit_order(
            db,
            salesman,
            body.client_id,
            [NewLine(sku=line.sku, quantity=line.quantity) for line in body.lines],
        )
    except ClientNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found") from None
    except ProductNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {exc.sku} not found",
        ) from None
    except ClientNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only order for clients assigned to you",
        ) from None
    except NotEnoughStock as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except InvalidOrder as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    return _to_out(order)


@router.get("", response_model=list[OrderOut])
def orders(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[OrderOut]:
    return [_to_out(order) for order in list_orders(db, current_user)]


@router.get("/{order_id}", response_model=OrderOut)
def order_detail(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OrderOut:
    try:
        return _to_out(get_order(db, current_user, order_id))
    except OrderNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found") from None
    except OrderNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own orders",
        ) from None


@router.post("/{order_id}/status", response_model=OrderOut)
def update_status(
    order_id: int,
    body: OrderStatusChange,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[User, Depends(_require_manager)],
) -> OrderOut:
    try:
        return _to_out(change_status(db, manager, order_id, body.status))
    except OrderNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found") from None
    except NotEnoughStock as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except InvalidOrder as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
