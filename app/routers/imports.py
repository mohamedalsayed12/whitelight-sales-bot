from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import ImportResultOut, ImportRowError
from app.services.auth import require_manager
from app.services.imports import InvalidImportFile, import_receivables, import_stock

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/stock", response_model=ImportResultOut)
def upload_stock(
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(require_manager)],
    file: Annotated[UploadFile, File()],
) -> ImportResultOut:
    return _run_import(db, file, import_stock)


@router.post("/receivables", response_model=ImportResultOut)
def upload_receivables(
    db: Annotated[Session, Depends(get_db)],
    _manager: Annotated[User, Depends(require_manager)],
    file: Annotated[UploadFile, File()],
) -> ImportResultOut:
    return _run_import(db, file, import_receivables)


def _run_import(db: Session, file: UploadFile, import_fn) -> ImportResultOut:
    try:
        result = import_fn(db, file.file.read())
    except InvalidImportFile as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    return ImportResultOut(
        imported=result.imported,
        failed=result.failed,
        errors=[ImportRowError(row=error.row, message=error.message) for error in result.errors],
    )
