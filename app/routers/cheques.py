from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import ChequeCreate, ChequeOut, ChequeStatusChange
from app.services.accounts import ClientNotAllowed, ClientNotFound
from app.services.auth import get_current_user
from app.services.cheques import (
    ChequeNotFound,
    ChequeView,
    InvalidChequeStatus,
    bounced_cheques,
    change_status,
    due_cheques,
    log_cheque,
)

router = APIRouter(prefix="/cheques", tags=["cheques"])


def _require_salesman(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role != UserRole.salesman:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a salesman can log a cheque",
        )
    return current_user


def _require_manager(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager or admin can update a cheque",
        )
    return current_user


def _to_out(cheque: ChequeView) -> ChequeOut:
    return ChequeOut(
        id=cheque.id,
        client_id=cheque.client_id,
        client_name=cheque.client_name,
        cheque_number=cheque.cheque_number,
        bank=cheque.bank,
        amount=cheque.amount,
        due_date=cheque.due_date,
        status=cheque.status,
        collected_by_id=cheque.collected_by_id,
    )


@router.post("", response_model=ChequeOut, status_code=status.HTTP_201_CREATED)
def create_cheque(
    body: ChequeCreate,
    db: Annotated[Session, Depends(get_db)],
    salesman: Annotated[User, Depends(_require_salesman)],
) -> ChequeOut:
    try:
        cheque = log_cheque(
            db,
            salesman,
            body.client_id,
            body.cheque_number,
            body.bank,
            body.amount,
            body.due_date,
        )
    except ClientNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found") from None
    except ClientNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only log cheques for clients assigned to you",
        ) from None
    return _to_out(cheque)


@router.get("/due", response_model=list[ChequeOut])
def cheques_due(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ChequeOut]:
    return [_to_out(cheque) for cheque in due_cheques(db, current_user)]


@router.get("/bounced", response_model=list[ChequeOut])
def cheques_bounced(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ChequeOut]:
    return [_to_out(cheque) for cheque in bounced_cheques(db, current_user)]


@router.post("/{cheque_id}/status", response_model=ChequeOut)
def update_status(
    cheque_id: int,
    body: ChequeStatusChange,
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> ChequeOut:
    try:
        return _to_out(change_status(db, cheque_id, body.status))
    except ChequeNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cheque not found") from None
    except InvalidChequeStatus as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
