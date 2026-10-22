import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import (
    LeadAssign,
    LeadOut,
    LeadOverviewOut,
    LeadReasonOut,
    LeadStatusChange,
    MyLeadsOut,
    SalesmanOption,
    SalesmanStatOut,
    SourceStatOut,
)
from app.services.auth import get_current_user
from app.services.leads import (
    LeadNotAllowed,
    LeadNotFound,
    LeadView,
    Overview,
    SalesmanNotFound,
    assign_lead,
    change_status,
    get_lead,
    list_mine,
    overview,
    rows_for_export,
)

router = APIRouter(prefix="/leads", tags=["leads"])


def _require_manager(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager or admin can view the lead desk",
        )
    return current_user


def _to_out(lead: LeadView) -> LeadOut:
    return LeadOut(
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
        suggested_salesman_id=lead.suggested_salesman_id,
        suggested_name=lead.suggested_name,
        reasons=[LeadReasonOut(points=reason.points, text=reason.text) for reason in lead.reasons],
        message=lead.message,
    )


def _overview_out(report: Overview) -> LeadOverviewOut:
    return LeadOverviewOut(
        sample_data=report.sample_data,
        week_start=report.week_start,
        week_end=report.week_end,
        new_leads=report.new_leads,
        contacted=report.contacted,
        quotes=report.quotes,
        won=report.won,
        contacted_pct=report.contacted_pct,
        quotes_pct=report.quotes_pct,
        won_pct=report.won_pct,
        by_salesman=[
            SalesmanStatOut(
                id=row.id,
                name=row.name,
                assigned=row.assigned,
                contacted=row.contacted,
                quotes=row.quotes,
                won=row.won,
                late=row.late,
            )
            for row in report.by_salesman
        ],
        sources=[
            SourceStatOut(
                key=row.key,
                label=row.label,
                enabled=row.enabled,
                leads=row.leads,
                quotes=row.quotes,
                won=row.won,
            )
            for row in report.sources
        ],
        unassigned=[_to_out(lead) for lead in report.unassigned],
        salesmen=[SalesmanOption(id=user_id, name=name) for user_id, name in report.salesmen],
    )


@router.get("/mine", response_model=MyLeadsOut)
def mine(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MyLeadsOut:
    name, to_contact, sample_data, leads = list_mine(db, current_user)
    return MyLeadsOut(
        salesman_name=name,
        to_contact=to_contact,
        sample_data=sample_data,
        leads=[_to_out(lead) for lead in leads],
    )


@router.get("/overview", response_model=LeadOverviewOut)
def weekly(
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> LeadOverviewOut:
    return _overview_out(overview(db))


@router.get("/export")
def export_csv(
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> Response:
    report = overview(db)
    names = {user_id: name for user_id, name in report.salesmen}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "category", "area", "score", "status", "source", "salesman", "phone"])
    for lead in rows_for_export(db):
        writer.writerow(
            [
                lead.name,
                lead.category,
                lead.area,
                lead.score,
                lead.status.value,
                lead.source.value,
                names.get(lead.assigned_salesman_id, ""),
                lead.phone,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )


@router.get("/{lead_id}", response_model=LeadOut)
def lead_detail(
    lead_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LeadOut:
    try:
        return _to_out(get_lead(db, current_user, lead_id))
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found") from None
    except LeadNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own leads",
        ) from None


@router.post("/{lead_id}/status", response_model=LeadOut)
def update_status(
    lead_id: int,
    body: LeadStatusChange,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LeadOut:
    try:
        return _to_out(change_status(db, current_user, lead_id, body.status))
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found") from None
    except LeadNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own leads",
        ) from None


@router.post("/{lead_id}/assign", response_model=LeadOut)
def update_assignment(
    lead_id: int,
    body: LeadAssign,
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(_require_manager)],
) -> LeadOut:
    try:
        return _to_out(assign_lead(db, lead_id, body.salesman_id))
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found") from None
    except SalesmanNotFound:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a salesman",
        ) from None
