"""Test setup.

Tests must run against a database whose name ends with _test.
DATABASE_URL is pointed at that database before the app is imported,
so neither the app nor Alembic can touch the development database.
"""

import os
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines. Variables already set (for example in CI) win."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")

test_database_url = os.environ.get("TEST_DATABASE_URL", "")
if not test_database_url:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. Copy .env.example to .env and start Postgres."
    )

test_database_name = make_url(test_database_url).database
if test_database_name is None or not test_database_name.endswith("_test"):
    safe_url = make_url(test_database_url).render_as_string(hide_password=True)
    raise RuntimeError(
        f"Refusing to run tests against {safe_url}. The database name must end with _test."
    )

# Do this before importing the app. Settings reads DATABASE_URL at import time.
os.environ["DATABASE_URL"] = test_database_url
# Tests create their own users. Do not also create the CEO from .env.
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""

if not os.environ.get("JWT_SECRET"):
    raise RuntimeError("JWT_SECRET is not set. Copy .env.example to .env.")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.database import SessionLocal, engine
from app.main import app
from app.models import UserRole
from app.services.users import create_user

DEFAULT_PASSWORD = "password123"


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    database_name = make_url(settings.database_url).database
    if database_name is None or not database_name.endswith("_test"):
        raise RuntimeError(
            f"Refusing to migrate database {database_name!r}. The name must end with _test."
        )

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    try:
        command.upgrade(config, "head")
    except OperationalError as exc:
        raise RuntimeError(
            "Could not migrate the test database. Start Postgres with "
            "'docker compose up -d'. If whitelight_test is missing, run "
            "'docker compose down -v' and then 'docker compose up -d' so the "
            "init script can create it."
        ) from exc


@pytest.fixture(autouse=True)
def clean_database(migrated_database):
    """Each test starts with empty business tables."""
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM quote_lines"))
        connection.execute(text("DELETE FROM quotes"))
        connection.execute(text("DELETE FROM order_history"))
        connection.execute(text("DELETE FROM order_lines"))
        connection.execute(text("DELETE FROM orders"))
        connection.execute(text("DELETE FROM price_list_items"))
        connection.execute(text("DELETE FROM cheques"))
        connection.execute(text("DELETE FROM invoices"))
        connection.execute(text("DELETE FROM clients"))
        connection.execute(text("DELETE FROM products"))
        connection.execute(text("DELETE FROM users"))
    yield


@pytest.fixture
def client(clean_database):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def add_user():
    def _add_user(
        *,
        email: str,
        role: UserRole,
        full_name: str = "Test User",
        password: str = DEFAULT_PASSWORD,
    ):
        db = SessionLocal()
        try:
            return create_user(
                db,
                email=email,
                password=password,
                full_name=full_name,
                role=role,
            )
        finally:
            db.close()

    return _add_user


@pytest.fixture
def login(client):
    def _login(email: str, password: str = DEFAULT_PASSWORD) -> str:
        response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return _login
