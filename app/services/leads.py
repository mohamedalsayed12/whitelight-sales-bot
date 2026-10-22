import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, LeadSource, LeadStatus, User, UserRole
from app.services import accounts

SOURCE_LABELS = {
    LeadSource.tender: "Tender award lists",
    LeadSource.exhibition: "Exhibition contacts",
    LeadSource.hand: "Added by hand",
    LeadSource.referral: "Referral",
}


class LeadNotFound(Exception):
    """No lead has this id."""


class LeadNotAllowed(Exception):
    """A salesman asked for a lead that is not theirs."""


class SalesmanNotFound(Exception):
    """The person to assign is missing, or is not a salesman."""


@dataclass
class ReasonView:
    points: int
    text: str


@dataclass
class LeadView:
    id: int
    name: str
    category: str
    area: str
    summary: str
    score: int
    status: LeadStatus
    source: LeadSource
    phone: str
    contact_by: date | None
    quote_sent_on: date | None
    assigned_salesman_id: int | None
    suggested_salesman_id: int | None
    suggested_name: str
    reasons: list[ReasonView]
    message: str


@dataclass
class SalesmanStats:
    id: int
    name: str
    assigned: int
    contacted: int
    quotes: int
    won: int
    late: int


@dataclass
class SourceStats:
    key: str
    label: str
    enabled: bool
    leads: int | None
    quotes: int | None
    won: int | None


@dataclass
class Overview:
    sample_data: bool
    week_start: date
    week_end: date
    new_leads: int
    contacted: int
    quotes: int
    won: int
    contacted_pct: int | None
    quotes_pct: int | None
    won_pct: int | None
    by_salesman: list[SalesmanStats]
    sources: list[SourceStats]
    unassigned: list[LeadView]
    salesmen: list[tuple[int, str]]


def list_mine(db: Session, user: User) -> tuple[str, int, bool, list[LeadView]]:
    """Leads assigned to this user, highest score first."""
    leads = db.scalars(
        select(Lead)
        .where(Lead.assigned_salesman_id == user.id)
        .order_by(Lead.score.desc(), Lead.id)
    ).all()
    views = [_view(db, lead, user.full_name) for lead in leads]
    to_contact = sum(1 for lead in leads if lead.status == LeadStatus.new)
    return user.full_name, to_contact, _sample_data(db), views


def get_lead(db: Session, user: User, lead_id: int) -> LeadView:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise LeadNotFound
    if user.role == UserRole.salesman and lead.assigned_salesman_id != user.id:
        raise LeadNotAllowed
    owner = db.get(User, lead.assigned_salesman_id) if lead.assigned_salesman_id else None
    name = owner.full_name if owner is not None else user.full_name
    return _view(db, lead, name)


def change_status(db: Session, user: User, lead_id: int, status: LeadStatus) -> LeadView:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise LeadNotFound
    if user.role == UserRole.salesman and lead.assigned_salesman_id != user.id:
        raise LeadNotAllowed
    lead.status = status
    if status in (LeadStatus.quote_sent, LeadStatus.won) and lead.quote_sent_on is None:
        lead.quote_sent_on = accounts.bahrain_today()
    db.commit()
    return get_lead(db, user, lead.id)


def assign_lead(db: Session, lead_id: int, salesman_id: int) -> LeadView:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise LeadNotFound
    salesman = db.get(User, salesman_id)
    if salesman is None or salesman.role != UserRole.salesman:
        raise SalesmanNotFound
    lead.assigned_salesman_id = salesman.id
    db.commit()
    return _view(db, lead, salesman.full_name)


def overview(db: Session) -> Overview:
    """This week's leads, plus anything still waiting for a salesman.

    The week is the seven days ending today in Asia/Bahrain.
    Contacted means the lead has moved past new. Quotes include wins.
    """
    start_day, end_day = _week()
    start = datetime.combine(start_day, time.min, tzinfo=accounts.BAHRAIN)
    end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=accounts.BAHRAIN)
    week_leads = db.scalars(
        select(Lead).where(
            Lead.created_at >= start,
            Lead.created_at < end,
            Lead.assigned_salesman_id.is_not(None),
        )
    ).all()
    today = accounts.bahrain_today()
    by_id: dict[int, SalesmanStats] = {}
    source_counts: dict[LeadSource, list[int]] = {source: [0, 0, 0] for source in LeadSource}
    new_leads = contacted = quotes = won = 0
    for lead in week_leads:
        new_leads += 1
        moved = lead.status != LeadStatus.new
        quoted = lead.status in (LeadStatus.quote_sent, LeadStatus.won)
        did_win = lead.status == LeadStatus.won
        late = lead.status == LeadStatus.new and lead.contact_by is not None and lead.contact_by < today
        if moved:
            contacted += 1
        if quoted:
            quotes += 1
        if did_win:
            won += 1
        owner = db.get(User, lead.assigned_salesman_id)
        stats = by_id.get(lead.assigned_salesman_id)
        if stats is None:
            stats = SalesmanStats(
                id=lead.assigned_salesman_id,
                name="" if owner is None else owner.full_name,
                assigned=0,
                contacted=0,
                quotes=0,
                won=0,
                late=0,
            )
            by_id[lead.assigned_salesman_id] = stats
        stats.assigned += 1
        stats.contacted += int(moved)
        stats.quotes += int(quoted)
        stats.won += int(did_win)
        stats.late += int(late)
        bucket = source_counts[lead.source]
        bucket[0] += 1
        bucket[1] += int(quoted)
        bucket[2] += int(did_win)

    sources = [
        SourceStats(
            key=source.value,
            label=SOURCE_LABELS[source],
            enabled=True,
            leads=source_counts[source][0],
            quotes=source_counts[source][1],
            won=source_counts[source][2],
        )
        for source in LeadSource
    ]
    sources.append(
        SourceStats(
            key="google_places",
            label="Google Places (not switched on yet)",
            enabled=False,
            leads=None,
            quotes=None,
            won=None,
        )
    )
    waiting = db.scalars(
        select(Lead)
        .where(Lead.assigned_salesman_id.is_(None))
        .order_by(Lead.score.desc(), Lead.id)
    ).all()
    salesmen = db.scalars(
        select(User).where(User.role == UserRole.salesman).order_by(User.full_name)
    ).all()
    return Overview(
        sample_data=_sample_data(db),
        week_start=start_day,
        week_end=end_day,
        new_leads=new_leads,
        contacted=contacted,
        quotes=quotes,
        won=won,
        contacted_pct=_pct(contacted, new_leads),
        quotes_pct=_pct(quotes, contacted),
        won_pct=_pct(won, quotes),
        by_salesman=sorted(by_id.values(), key=lambda row: (-row.assigned, row.name)),
        sources=sources,
        unassigned=[_view(db, lead, "") for lead in waiting],
        salesmen=[(user.id, user.full_name) for user in salesmen],
    )


def rows_for_export(db: Session) -> list[Lead]:
    return list(db.scalars(select(Lead).order_by(Lead.score.desc(), Lead.id)).all())


def _week() -> tuple[date, date]:
    end = accounts.bahrain_today()
    return end - timedelta(days=6), end


def _pct(part: int, whole: int) -> int | None:
    if whole == 0:
        return None
    return round(part * 100 / whole)


def _sample_data(db: Session) -> bool:
    flags = db.scalars(select(Lead.is_sample)).all()
    return bool(flags) and all(flags)


def _view(db: Session, lead: Lead, salesman_name: str) -> LeadView:
    suggested = db.get(User, lead.suggested_salesman_id) if lead.suggested_salesman_id else None
    return LeadView(
        id=lead.id,
        name=lead.name,
        category=lead.category,
        area=lead.area,
        summary=lead.summary,
        score=lead.score,
        status=lead.status,
        source=lead.source,
        phone=lead.phone,
        contact_by=lead.contact_by,
        quote_sent_on=lead.quote_sent_on,
        assigned_salesman_id=lead.assigned_salesman_id,
        suggested_salesman_id=lead.suggested_salesman_id,
        suggested_name="" if suggested is None else suggested.full_name,
        reasons=_reasons(lead.reasons),
        message=_message(lead, salesman_name),
    )


def _reasons(raw: str) -> list[ReasonView]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    reasons: list[ReasonView] = []
    for item in parsed:
        reasons.append(ReasonView(points=int(item["points"]), text=str(item["text"])))
    return reasons


def _message(lead: Lead, salesman_name: str) -> str:
    first = salesman_name.split()[0] if salesman_name else "there"
    hook = lead.pitch_hook or f"the news about {lead.name}"
    return (
        f"Good morning, this is {first} from White Light Trading. "
        f"Congratulations on {hook}. We supply hotels across Bahrain with "
        "lighting, electrical and kitchen equipment from local stock and "
        "quick delivery. Could I send you our hotel catalogue and a quick quote?"
    )
