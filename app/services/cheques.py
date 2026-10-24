from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cheque, ChequeStatus, Client, User, UserRole, utcnow
from app.services import accounts
from app.services.accounts import PENDING, ClientNotAllowed, ClientNotFound

NEXT_STATUS = {
    ChequeStatus.received: {ChequeStatus.deposited, ChequeStatus.bounced},
    ChequeStatus.deposited: {ChequeStatus.cleared, ChequeStatus.bounced},
    ChequeStatus.cleared: set(),
    ChequeStatus.bounced: set(),
}


class ChequeNotFound(Exception):
    """No cheque has this id."""


class InvalidChequeStatus(Exception):
    """The status change skips a step, or the cheque is already finished."""


@dataclass
class ChequeView:
    id: int
    client_id: int
    client_name: str
    cheque_number: str
    bank: str
    amount: Decimal
    due_date: date
    status: ChequeStatus
    collected_by_id: int | None


def log_cheque(
    db: Session,
    salesman: User,
    client_id: int,
    cheque_number: str,
    bank: str,
    amount: Decimal,
    due_date: date,
) -> ChequeView:
    """Record a cheque the salesman collected. It starts as received."""
    client = db.get(Client, client_id)
    if client is None:
        raise ClientNotFound
    if client.assigned_salesman_id != salesman.id:
        raise ClientNotAllowed

    cheque = Cheque(
        client_id=client.id,
        cheque_number=cheque_number,
        bank=bank,
        amount=amount,
        due_date=due_date,
        status=ChequeStatus.received,
        collected_by_id=salesman.id,
        collected_at=utcnow(),
    )
    db.add(cheque)
    db.commit()
    db.refresh(cheque)
    return _view(cheque, client.name)


def change_status(db: Session, cheque_id: int, new_status: ChequeStatus) -> ChequeView:
    cheque = db.get(Cheque, cheque_id)
    if cheque is None:
        raise ChequeNotFound
    if new_status not in NEXT_STATUS[cheque.status]:
        raise InvalidChequeStatus(
            f"Cannot change a cheque from {cheque.status.value} to {new_status.value}"
        )
    cheque.status = new_status
    db.commit()
    client = db.get(Client, cheque.client_id)
    return _view(cheque, "" if client is None else client.name)


def due_cheques(db: Session, user: User) -> list[ChequeView]:
    """Received or deposited cheques due today through seven days ahead.

    The dates use Asia/Bahrain. Cleared and bounced cheques are left out.
    A salesman only sees clients assigned to them.
    """
    today = accounts.bahrain_today()
    last = today + timedelta(days=7)
    query = (
        select(Cheque, Client.name)
        .join(Client, Cheque.client_id == Client.id)
        .where(
            Cheque.status.in_(PENDING),
            Cheque.due_date >= today,
            Cheque.due_date <= last,
        )
        .order_by(Cheque.due_date, Cheque.id)
    )
    return [_view(cheque, name) for cheque, name in _for_user(db, user, query)]


def bounced_cheques(db: Session, user: User) -> list[ChequeView]:
    """Every bounced cheque. A salesman only sees clients assigned to them."""
    query = (
        select(Cheque, Client.name)
        .join(Client, Cheque.client_id == Client.id)
        .where(Cheque.status == ChequeStatus.bounced)
        .order_by(Cheque.id.desc())
    )
    return [_view(cheque, name) for cheque, name in _for_user(db, user, query)]


def _for_user(db: Session, user: User, query):
    if user.role == UserRole.salesman:
        query = query.where(Client.assigned_salesman_id == user.id)
    return db.execute(query).all()


def _view(cheque: Cheque, client_name: str) -> ChequeView:
    return ChequeView(
        id=cheque.id,
        client_id=cheque.client_id,
        client_name=client_name,
        cheque_number=cheque.cheque_number,
        bank=cheque.bank,
        amount=cheque.amount,
        due_date=cheque.due_date,
        status=cheque.status,
        collected_by_id=cheque.collected_by_id,
    )
