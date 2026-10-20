from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.schemas import LoginRequest, Token, UserCreate, UserOut
from app.services.auth import authenticate, create_access_token, get_current_user
from app.services.users import EmailAlreadyRegistered, create_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
    # Public registration is always a salesman. An admin creates other roles.
    try:
        return create_user(
            db,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            role=UserRole.salesman,
        )
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None


@router.post("/login", response_model=Token)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> Token:
    user = authenticate(db, email=body.email, password=body.password)
    if user is None:
        # Same message either way, so a caller cannot learn which emails exist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
