from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, UserRole
from app.services.passwords import hash_password

_email_check = TypeAdapter(EmailStr)


class EmailAlreadyRegistered(Exception):
    """The email is already stored. Callers turn this into HTTP 409."""


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
) -> User:
    cleaned_name = full_name.strip()
    if not cleaned_name:
        raise ValueError("Full name is required")

    user = User(
        email=email.strip().lower(),
        full_name=cleaned_name,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered
    db.refresh(user)
    return user


def ensure_initial_admin(db: Session) -> None:
    """Create the CEO account from .env, once.

    If that email already exists we leave it alone, including its password
    and role. Startup must not reset a password the CEO has changed.
    """
    email = settings.admin_email.strip().lower()
    password = settings.admin_password
    if not email or not password:
        return
    try:
        _email_check.validate_python(email)
    except ValidationError as exc:
        raise RuntimeError(
            "ADMIN_EMAIL is not a valid email address. "
            "Use an address such as ceo@example.com."
        ) from exc
    if get_user_by_email(db, email) is not None:
        return

    full_name = settings.admin_full_name.strip() or "Admin"
    try:
        create_user(
            db,
            email=email,
            password=password,
            full_name=full_name,
            role=UserRole.admin,
        )
    except EmailAlreadyRegistered:
        return
    except ValueError as exc:
        raise RuntimeError(f"Could not create the initial admin: {exc}") from exc
