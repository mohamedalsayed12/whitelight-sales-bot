from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import ClientAccountOut, ClientTermsOut, ClientTermsUpdate, OverdueOut
from app.services.accounts import ClientNotAllowed, ClientNotFound, get_client_account
from app.services.auth import get_current_user
from app.services.clients import update_client_terms

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/{client_id}/account", response_model=ClientAccountOut)
def client_account(
    client_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ClientAccountOut:
    try:
        account = get_client_account(db, client_id, current_user)
    except ClientNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        ) from None
    except ClientNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view clients assigned to you",
        ) from None
    overdue = account.overdue
    return ClientAccountOut(
        client_id=account.client_id,
        name=account.name,
        total_outstanding=account.total_outstanding,
        overdue=OverdueOut(
            days_0_30=overdue.days_0_30,
            days_31_60=overdue.days_31_60,
            days_61_90=overdue.days_61_90,
            over_90=overdue.over_90,
        ),
        pending_cheques=account.pending_cheques,
        status=account.status,
    )


def _require_manager(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager or admin can update a client",
        )
    return current_user


@router.patch("/{client_id}", response_model=ClientTermsOut)
def update_client(
    client_id: int,
    body: ClientTermsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> ClientTermsOut:
    try:
        client = update_client_terms(
            db,
            client_id,
            price_list=body.price_list,
            credit_limit=body.credit_limit,
        )
    except ClientNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        ) from None
    return ClientTermsOut.model_validate(client)
