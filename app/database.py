from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Check the connection before using it, so a restarted Postgres does not
# break the next request with a stale connection.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# expire_on_commit=False keeps attributes readable after commit, so a route
# can return the user it just saved without another query.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
