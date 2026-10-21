from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import SessionLocal
from app.routers import (
    auth,
    cheques,
    clients,
    health,
    imports,
    orders,
    prices,
    quotes,
    reorder,
    stock,
    summary,
    users,
)
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
app.include_router(stock.router)
app.include_router(clients.router)
app.include_router(prices.router)
app.include_router(orders.router)
app.include_router(quotes.router)
app.include_router(cheques.router)
app.include_router(reorder.router)
app.include_router(summary.router)
