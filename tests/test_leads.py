from datetime import timedelta

from app.database import SessionLocal
from app.models import Lead, LeadSource, LeadStatus, UserRole
from app.services.accounts import bahrain_today
from app.services.sample_leads import seed_sample_leads


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_lead_screen_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "White Light" in response.text


def test_sample_week_matches_the_lead_desk(client, login):
    db = SessionLocal()
    try:
        seed_sample_leads(db)
    finally:
        db.close()
    ahmed = login("ahmed@example.com")
    yusuf = login("yusuf@example.com")

    denied = client.get("/leads/overview", headers=_headers(ahmed))
    mine = client.get("/leads/mine", headers=_headers(ahmed))
    lead_id = mine.json()["leads"][0]["id"]
    hidden = client.get(f"/leads/{lead_id}", headers=_headers(yusuf))

    assert denied.status_code == 403
    assert mine.status_code == 200
    body = mine.json()
    assert body["salesman_name"] == "Ahmed"
    assert body["leads"][0]["name"] == "Juffair Grand Suites"
    assert body["leads"][0]["score"] == 83
    assert "Juffair Grand Suites" in body["leads"][0]["message"]
    assert "Ahmed" in body["leads"][0]["message"]
    assert hidden.status_code == 403


def test_manager_sees_the_week_and_assigns_a_lead(client, add_user, login):
    db = SessionLocal()
    try:
        seed_sample_leads(db)
    finally:
        db.close()
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    yusuf = login("yusuf@example.com")
    ahmed = login("ahmed@example.com")
    overview = client.get("/leads/overview", headers=_headers(manager))
    hidden = client.get(f"/leads/{overview.json()['unassigned'][0]['id']}", headers=_headers(yusuf))

    assert overview.status_code == 200
    report = overview.json()
    assert report["new_leads"] == 42
    assert report["contacted"] == 27
    assert report["quotes"] == 9
    assert report["won"] == 3
    assert report["contacted_pct"] == 64
    assert [row["name"] for row in report["by_salesman"]] == ["Ahmed", "Yusuf", "Ravi"]
    assert report["by_salesman"][0]["late"] == 1
    assert report["sources"][-1]["key"] == "google_places"
    assert report["sources"][-1]["enabled"] is False
    assert hidden.status_code == 403

    waiting = report["unassigned"][0]
    assigned = client.post(
        f"/leads/{waiting['id']}/assign",
        headers=_headers(manager),
        json={"salesman_id": waiting["suggested_salesman_id"]},
    )
    exported = client.get("/leads/export", headers=_headers(manager))
    blocked = client.get("/leads/export", headers=_headers(ahmed))

    assert assigned.status_code == 200
    assert assigned.json()["name"] == waiting["name"]
    assert exported.status_code == 200
    assert "Juffair Grand Suites" in exported.text
    assert blocked.status_code == 403


def test_a_late_new_lead_is_counted(client, add_user, login):
    salesman = add_user(email="sam@example.com", role=UserRole.salesman, full_name="Sam")
    add_user(email="manager@example.com", role=UserRole.manager, full_name="Maha")
    manager = login("manager@example.com")
    db = SessionLocal()
    try:
        db.add(
            Lead(
                name="Late Cafe",
                category="Restaurant",
                area="Hoora",
                summary="Called yesterday",
                score=40,
                reasons="[]",
                status=LeadStatus.new,
                source=LeadSource.hand,
                phone="",
                pitch_hook="",
                contact_by=bahrain_today() - timedelta(days=1),
                assigned_salesman_id=salesman.id,
                is_sample=False,
            )
        )
        db.commit()
    finally:
        db.close()

    report = client.get("/leads/overview", headers=_headers(manager)).json()

    assert report["new_leads"] == 1
    assert report["by_salesman"][0]["late"] == 1
    assert report["sample_data"] is False
