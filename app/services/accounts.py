import enum
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Cheque, ChequeStatus, Client, Invoice, User, UserRole

BAHRAIN = ZoneInfo("Asia/Bahrain")
PLACES = Decimal("0.001")
ZERO = Decimal("0.000")
PENDING = (ChequeStatus.received, ChequeStatus.deposited)


class AccountStatus(str, enum.Enum):
    ok = "ok"
    warning = "warning"
    on_hold = "on_hold"


class ClientNotFound(Exception):
    """No client has this id. Callers turn this into HTTP 404."""


class ClientNotAllowed(Exception):
    """A salesman asked for a client who is not assigned to them."""


@dataclass
class OverdueBuckets:
    days_0_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    over_90: Decimal


@dataclass
class ClientAccount:
    client_id: int
    name: str
    total_outstanding: Decimal
    overdue: OverdueBuckets
    pending_cheques: Decimal
    status: AccountStatus


def bahrain_today() -> date:
    return datetime.now(BAHRAIN).date()


ON_HOLD_WARNING = "Client is on hold. A manager must approve."


def get_client_account(db: Session, client_id: int, user: User) -> ClientAccount:
    """Summarise what the client still owes.

    Outstanding is amount minus amount_paid. Money that is not yet due
    stays in the total, but not in an overdue bucket. Days past due use
    today's date in Asia/Bahrain.

    on_hold means the outstanding total is over the credit limit, or any
    money is more than 90 days past due. warning means something is overdue
    but the client is not on hold. Equal to the credit limit is still ok.
    """
    client = db.get(Client, client_id)
    if client is None:
        raise ClientNotFound
    if user.role == UserRole.salesman and client.assigned_salesman_id != user.id:
        raise ClientNotAllowed
    outstanding, overdue, pending = _figures(db, client)
    return ClientAccount(
        client_id=client.id,
        name=client.name,
        total_outstanding=outstanding,
        overdue=overdue,
        pending_cheques=pending,
        status=_status(outstanding, client.credit_limit, overdue),
    )


def on_hold_warning(db: Session, client: Client) -> str | None:
    """The submit-order warning. None when the client can be served normally."""
    outstanding, overdue, _pending = _figures(db, client)
    if _status(outstanding, client.credit_limit, overdue) == AccountStatus.on_hold:
        return ON_HOLD_WARNING
    return None


def _figures(db: Session, client: Client) -> tuple[Decimal, OverdueBuckets, Decimal]:
    today = bahrain_today()
    buckets = {"0_30": ZERO, "31_60": ZERO, "61_90": ZERO, "over_90": ZERO}
    outstanding = ZERO
    invoices = db.scalars(select(Invoice).where(Invoice.client_id == client.id))
    for invoice in invoices:
        remaining = _money(invoice.amount - invoice.amount_paid)
        if remaining == 0:
            continue
        outstanding += remaining
        days_late = (today - invoice.due_date).days
        if days_late < 0:
            continue
        if days_late <= 30:
            buckets["0_30"] += remaining
        elif days_late <= 60:
            buckets["31_60"] += remaining
        elif days_late <= 90:
            buckets["61_90"] += remaining
        else:
            buckets["over_90"] += remaining

    pending = db.scalar(
        select(func.coalesce(func.sum(Cheque.amount), 0)).where(
            Cheque.client_id == client.id,
            Cheque.status.in_(PENDING),
        )
    )
    overdue = OverdueBuckets(
        days_0_30=_money(buckets["0_30"]),
        days_31_60=_money(buckets["31_60"]),
        days_61_90=_money(buckets["61_90"]),
        over_90=_money(buckets["over_90"]),
    )
    return _money(outstanding), overdue, _money(Decimal(pending))


def _status(outstanding: Decimal, credit_limit: Decimal, overdue: OverdueBuckets) -> AccountStatus:
    if outstanding > credit_limit or overdue.over_90 > 0:
        return AccountStatus.on_hold
    if overdue.days_0_30 > 0 or overdue.days_31_60 > 0 or overdue.days_61_90 > 0:
        return AccountStatus.warning
    return AccountStatus.ok


def total_overdue(db: Session) -> Decimal:
    """Money that is due today or earlier, across every client."""
    today = bahrain_today()
    total = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount - Invoice.amount_paid), 0)).where(
            Invoice.due_date <= today,
            Invoice.amount_paid < Invoice.amount,
        )
    )
    return _money(Decimal(total))


def _money(value: Decimal) -> Decimal:
    return value.quantize(PLACES)
