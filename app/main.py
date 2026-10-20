from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import SessionLocal
from app.routers import auth, health, imports, users
from app.services.users import ensure_initial_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # FastAPI asks for an async lifespan. The database code itself stays synchronous.
    db = SessionLocal()
    try:
        ensure_initial_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title="White Light Sales Bot", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(imports.router)
