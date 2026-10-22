"""Fictional leads so the screens match a working week.

Nothing here is collected from the web. Google Places stays off.
The rows are inserted once, and only when SAMPLE_LEADS is on.
"""

import json
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Lead, LeadSource, LeadStatus, UserRole
from app.services import accounts
from app.services.users import EmailAlreadyRegistered, create_user, get_user_by_email

SAMPLE_PASSWORD = "password123"

# Ahmed's visible list, then the four waiting to be assigned.
NAMED = [
    {
        "name": "Juffair Grand Suites",
        "category": "Hotel",
        "area": "Juffair",
        "summary": "New hotel, opening March 2027",
        "score": 83,
        "status": LeadStatus.new,
        "phone": "+97333000083",
        "pitch_hook": "the opening of Juffair Grand Suites",
        "owner": "Ahmed",
        "on_time": True,
        "reasons": [
            (40, "New hotel, opening March 2027"),
            (25, "Large site: 180 rooms"),
            (18, "Phone number listed"),
            (0, "Within our delivery area"),
            (0, "Has a website"),
        ],
    },
    {
        "name": "Gulf Coast Fit-Out W.L.L.",
        "category": "Contractor",
        "area": "Sitra",
        "summary": "Won a hotel fit-out tender",
        "score": 78,
        "status": LeadStatus.contacted,
        "phone": "+97333000078",
        "pitch_hook": "winning the hotel fit-out",
        "owner": "Ahmed",
        "reasons": [(78, "Won a hotel fit-out tender")],
    },
    {
        "name": "Saffron Lane Kitchen",
        "category": "Restaurant",
        "area": "Hoora",
        "summary": "New restaurant, opening December",
        "score": 64,
        "status": LeadStatus.contacted,
        "phone": "+97333000064",
        "pitch_hook": "the opening of Saffron Lane Kitchen",
        "owner": "Ahmed",
        "reasons": [(64, "New restaurant, opening December")],
    },
    {
        "name": "Harbour FM Services",
        "category": "Facilities",
        "area": "Hamala",
        "summary": "Manages 12 commercial buildings",
        "score": 55,
        "status": LeadStatus.contacted,
        "phone": "+97333000055",
        "pitch_hook": "the buildings Harbour FM looks after",
        "owner": "Ahmed",
        "reasons": [(55, "Manages 12 commercial buildings")],
    },
    {
        "name": "Riffa Views Café",
        "category": "Restaurant",
        "area": "Riffa",
        "summary": "Phone lead, no website",
        "score": 41,
        "status": LeadStatus.quote_sent,
        "phone": "+97333000041",
        "pitch_hook": "Riffa Views Café getting ready to open",
        "owner": "Ahmed",
        "reasons": [(41, "Phone lead, no website")],
    },
]

WAITING = [
    {
        "name": "Seef Tower Hotel & Spa",
        "category": "Hotel",
        "area": "Seef",
        "summary": "Renovation tender awarded",
        "score": 81,
        "suggest": "Ahmed",
        "reasons": [(81, "Renovation tender awarded")],
    },
    {
        "name": "Al Noor Catering Co.",
        "category": "Restaurant",
        "area": "Manama",
        "summary": "New central kitchen",
        "score": 67,
        "suggest": "Yusuf",
        "reasons": [(67, "New central kitchen")],
    },
    {
        "name": "Delta MEP Contracting",
        "category": "Contractor",
        "area": "Hidd",
        "summary": "Exhibition contact",
        "score": 59,
        "suggest": "Ravi",
        "reasons": [(59, "Exhibition contact")],
    },
    {
        "name": "Budaiya Garden Bistro",
        "category": "Restaurant",
        "area": "Budaiya",
        "summary": "Phone listed only",
        "score": 38,
        "suggest": "Yusuf",
        "reasons": [(38, "Phone listed only")],
    },
]

# This week's assigned leads, including the five named ones above.
# won, quote_sent, contacted, new. Late is how many of the new ones are overdue.
QUOTAS = {
    "Ahmed": {"won": 2, "quote_sent": 2, "contacted": 8, "new": 4, "late": 1},
    "Yusuf": {"won": 1, "quote_sent": 2, "contacted": 6, "new": 5, "late": 3},
    "Ravi": {"won": 0, "quote_sent": 2, "contacted": 4, "new": 6, "late": 1},
}

SALESMEN = (
    ("ahmed@example.com", "Ahmed"),
    ("yusuf@example.com", "Yusuf"),
    ("ravi@example.com", "Ravi"),
)


def seed_sample_leads(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(Lead)) :
        return
    people = {name: _salesman(db, email, name) for email, name in SALESMEN}
    today = accounts.bahrain_today()
    created = datetime.combine(today, time(12, 0), tzinfo=accounts.BAHRAIN)
    leads: list[Lead] = []
    for spec in NAMED:
        leads.append(
            _lead(
                spec,
                owner_id=people[spec["owner"]].id,
                status=spec["status"],
                created=created,
                today=today,
                on_time=spec.get("on_time", True),
                phone=spec.get("phone", ""),
                pitch_hook=spec.get("pitch_hook", ""),
            )
        )
    areas = ["Juffair", "Hoora", "Riffa", "Seef", "Sitra", "Budaiya"]
    categories = ["Hotel", "Restaurant", "Contractor", "Facilities"]
    number = 1
    for name, quota in QUOTAS.items():
        already = [lead for lead in leads if lead.assigned_salesman_id == people[name].id]
        have = {status: 0 for status in LeadStatus}
        for lead in already:
            have[lead.status] += 1
        late_left = quota["late"]
        if any(lead.contact_by and lead.contact_by < today for lead in already):
            late_left -= 1
        for status_name in ("won", "quote_sent", "contacted", "new"):
            status = LeadStatus(status_name)
            missing = quota[status_name] - have[status]
            for _ in range(missing):
                on_time = True
                if status == LeadStatus.new and late_left > 0:
                    on_time = False
                    late_left -= 1
                leads.append(
                    _lead(
                        {
                            "name": f"{areas[number % len(areas)]} {categories[number % len(categories)]} {number}",
                            "category": categories[number % len(categories)],
                            "area": areas[number % len(areas)],
                            "summary": "Sample follow-up for the weekly screen",
                            "score": 20 + (number % 15),
                            "reasons": [(20, "Sample follow-up")],
                        },
                        owner_id=people[name].id,
                        status=status,
                        created=created,
                        today=today,
                        on_time=on_time,
                        phone="",
                        pitch_hook="the project",
                    )
                )
                number += 1
    _apply_sources(leads)
    for spec in WAITING:
        leads.append(
            Lead(
                name=spec["name"],
                category=spec["category"],
                area=spec["area"],
                summary=spec["summary"],
                score=spec["score"],
                reasons=json.dumps(
                    [{"points": points, "text": text} for points, text in spec["reasons"]]
                ),
                status=LeadStatus.new,
                source=LeadSource.tender,
                phone="",
                pitch_hook="",
                contact_by=None,
                quote_sent_on=None,
                assigned_salesman_id=None,
                suggested_salesman_id=people[spec["suggest"]].id,
                is_sample=True,
                created_at=created,
            )
        )
    db.add_all(leads)
    db.commit()


def _salesman(db: Session, email: str, name: str):
    existing = get_user_by_email(db, email)
    if existing is not None:
        return existing
    try:
        return create_user(
            db,
            email=email,
            password=SAMPLE_PASSWORD,
            full_name=name,
            role=UserRole.salesman,
        )
    except EmailAlreadyRegistered:
        return get_user_by_email(db, email)


def _lead(spec, *, owner_id, status, created, today, on_time, phone, pitch_hook) -> Lead:
    contact_by = None
    quote_sent_on = None
    if status == LeadStatus.new:
        contact_by = today + timedelta(days=2) if on_time else today - timedelta(days=1)
    if status in (LeadStatus.quote_sent, LeadStatus.won):
        quote_sent_on = today
    return Lead(
        name=spec["name"],
        category=spec["category"],
        area=spec["area"],
        summary=spec["summary"],
        score=spec["score"],
        reasons=json.dumps([{"points": points, "text": text} for points, text in spec["reasons"]]),
        status=status,
        source=LeadSource.referral,
        phone=phone,
        pitch_hook=pitch_hook,
        contact_by=contact_by,
        quote_sent_on=quote_sent_on,
        assigned_salesman_id=owner_id,
        suggested_salesman_id=None,
        is_sample=True,
        created_at=created,
    )


def _apply_sources(leads: list[Lead]) -> None:
    """Line the source totals up with the weekly screen."""
    buckets: dict[LeadStatus, list[Lead]] = {status: [] for status in LeadStatus}
    for lead in leads:
        buckets[lead.status].append(lead)

    def take(status: LeadStatus, count: int, source: LeadSource) -> None:
        chosen = buckets[status][:count]
        del buckets[status][:count]
        for lead in chosen:
            lead.source = source

    take(LeadStatus.won, 2, LeadSource.tender)
    take(LeadStatus.won, 1, LeadSource.exhibition)
    take(LeadStatus.quote_sent, 2, LeadSource.tender)
    take(LeadStatus.quote_sent, 2, LeadSource.exhibition)
    take(LeadStatus.quote_sent, 2, LeadSource.hand)
    plan = (
        [(LeadSource.tender, 14), (LeadSource.exhibition, 9), (LeadSource.hand, 6), (LeadSource.referral, 4)]
    )
    rest = [lead for rows in buckets.values() for lead in rows]
    cursor = 0
    for source, count in plan:
        for lead in rest[cursor : cursor + count]:
            lead.source = source
        cursor += count
