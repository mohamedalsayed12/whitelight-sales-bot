import pytest
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import User, UserRole
from app.services.passwords import verify_password
from app.services.users import ensure_initial_admin, get_user_by_email


def test_initial_admin_is_created_and_can_log_in(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "ceo@example.com")
    monkeypatch.setattr(settings, "admin_password", "password123")
    monkeypatch.setattr(settings, "admin_full_name", "Noor Ali")

    db = SessionLocal()
    try:
        ensure_initial_admin(db)
        ensure_initial_admin(db)
        count = db.scalar(select(func.count()).select_from(User))
    finally:
        db.close()

    assert count == 1
    login = client.post(
        "/auth/login",
        json={"email": "ceo@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    assert me.json()["full_name"] == "Noor Ali"
    assert me.json()["email"] == "ceo@example.com"


def test_existing_user_is_left_alone(add_user, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "ceo@example.com")
    monkeypatch.setattr(settings, "admin_password", "password123")
    monkeypatch.setattr(settings, "admin_full_name", "Noor Ali")
    add_user(
        email="ceo@example.com",
        role=UserRole.salesman,
        full_name="Existing User",
        password="sales-pass",
    )

    db = SessionLocal()
    try:
        ensure_initial_admin(db)
        user = get_user_by_email(db, "ceo@example.com")
        count = db.scalar(select(func.count()).select_from(User))
        assert user is not None
        assert user.role == UserRole.salesman
        assert user.full_name == "Existing User"
        assert verify_password("sales-pass", user.hashed_password)
        assert count == 1
    finally:
        db.close()


def test_seed_rejects_an_email_that_cannot_log_in(monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "ceo@whitelight.local")
    monkeypatch.setattr(settings, "admin_password", "password123")

    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="ADMIN_EMAIL"):
            ensure_initial_admin(db)
        count = db.scalar(select(func.count()).select_from(User))
    finally:
        db.close()

    assert count == 0


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("", "password123"),
        ("ceo@example.com", ""),
        ("", ""),
    ],
)
def test_seed_is_skipped_when_email_or_password_is_blank(monkeypatch, email, password):
    monkeypatch.setattr(settings, "admin_email", email)
    monkeypatch.setattr(settings, "admin_password", password)

    db = SessionLocal()
    try:
        ensure_initial_admin(db)
        count = db.scalar(select(func.count()).select_from(User))
    finally:
        db.close()

    assert count == 0
