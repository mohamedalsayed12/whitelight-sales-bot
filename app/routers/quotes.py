from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import QuoteCreate, QuoteLineOut, QuoteOut
from app.services.accounts import ClientNotAllowed, ClientNotFound
from app.services.auth import get_current_user
from app.services.orders import NewLine, ProductNotFound
from app.services.quote_pdf import render_quote_pdf
from app.services.quotes import (
    InvalidQuote,
    QuoteNotAllowed,
    QuoteNotFound,
    QuoteView,
    create_quote,
    get_quote,
    list_quotes,
)

router = APIRouter(prefix="/quotes", tags=["quotes"])


def _require_salesman(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role != UserRole.salesman:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a salesman can create a quote",
        )
    return current_user


def _to_out(quote: QuoteView) -> QuoteOut:
    return QuoteOut(
        id=quote.id,
        client_id=quote.client_id,
        salesman_id=quote.salesman_id,
        valid_until=quote.valid_until,
        total=quote.total,
        lines=[
            QuoteLineOut(sku=line.sku, quantity=line.quantity, unit_price=line.unit_price)
            for line in quote.lines
        ],
    )


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def create(
    body: QuoteCreate,
    db: Annotated[Session, Depends(get_db)],
    salesman: Annotated[User, Depends(_require_salesman)],
) -> QuoteOut:
    try:
        quote = create_quote(
            db,
            salesman,
            body.client_id,
            body.valid_until,
            [NewLine(sku=line.sku, quantity=line.quantity) for line in body.lines],
        )
    except ClientNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found") from None
    except ProductNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {exc.sku} not found",
        ) from None
    except ClientNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only quote for clients assigned to you",
        ) from None
    except InvalidQuote as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    return _to_out(quote)


@router.get("", response_model=list[QuoteOut])
def quotes(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[QuoteOut]:
    return [_to_out(quote) for quote in list_quotes(db, current_user)]


@router.get("/{quote_id}", response_model=QuoteOut)
def quote_detail(
    quote_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> QuoteOut:
    try:
        return _to_out(get_quote(db, current_user, quote_id))
    except QuoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found") from None
    except QuoteNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own quotes",
        ) from None


@router.get("/{quote_id}/pdf")
def quote_pdf(
    quote_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        quote = get_quote(db, current_user, quote_id)
    except QuoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found") from None
    except QuoteNotAllowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own quotes",
        ) from None
    return Response(
        content=render_quote_pdf(quote),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="quote-{quote.id}.pdf"'},
    )
