from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import SessionLocal
from app.routers import (
    auth,
    cheques,
    clients,
    health,
    imports,
    leads,
    orders,
    prices,
    quotes,
    reorder,
    stock,
    summary,
    users,
)
from app.services.sample_leads import seed_sample_leads
from app.services.users import ensure_initial_admin

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # FastAPI asks for an async lifespan. The database code itself stays synchronous.
    db = SessionLocal()
    try:
        ensure_initial_admin(db)
        if settings.sample_leads:
            seed_sample_leads(db)
    finally:
        db.close()
    yield


app = FastAPI(title="White Light Sales Bot", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(imports.router)
app.include_router(stock.router)
app.include_router(clients.router)
app.include_router(prices.router)
app.include_router(orders.router)
app.include_router(quotes.router)
app.include_router(cheques.router)
app.include_router(reorder.router)
app.include_router(summary.router)
app.include_router(leads.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
