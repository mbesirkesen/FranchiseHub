from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal
from ..file_tokens import build_uploaded_file_url, decode_fdd_download_token
from ..models import Brand, BrandFDDDocument, BrandMedia, FranchiseOwnerDocument, UploadedFile, UserRole
from ..schemas import AuthenticatedPrincipal, FileUploadResponse
from ..storage import ALLOWED_GENERAL_UPLOAD_TYPES, resolve_upload_path, save_upload_file

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    relative_path, mime_type, size = save_upload_file(
        file,
        subdir=f"uploads/{current_user.role.value}/{current_user.user_id}",
        allowed_mime=ALLOWED_GENERAL_UPLOAD_TYPES,
    )
    record = UploadedFile(
        uploader_role=current_user.role,
        uploader_id=current_user.user_id,
        file_path=relative_path,
        mime_type=mime_type,
        original_filename=file.filename,
        file_size_bytes=size,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return FileUploadResponse(
        file_id=record.id,
        url=build_uploaded_file_url(record.id),
        mime_type=mime_type,
        original_filename=file.filename,
        file_size_bytes=size,
    )


@router.get("/uploads/{file_id}")
def download_uploaded_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    record = db.get(UploadedFile, file_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    is_owner = (
        record.uploader_role == current_user.role
        and record.uploader_id == current_user.user_id
    )
    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this file",
        )
    path = resolve_upload_path(record.file_path)
    return FileResponse(
        path,
        media_type=record.mime_type,
        filename=record.original_filename,
    )


@router.get("/media/{media_id}")
def serve_brand_media(media_id: int, db: Session = Depends(get_db)):
    media = db.get(BrandMedia, media_id)
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    brand = db.scalar(
        select(Brand).where(Brand.id == media.brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    path = resolve_upload_path(media.file_path)
    return FileResponse(path, media_type=media.mime_type, filename=media.original_filename)


@router.get("/fdd/download")
def download_fdd_file(token: str = Query(..., min_length=10), db: Session = Depends(get_db)):
    try:
        payload = decode_fdd_download_token(token)
        brand_id = int(payload["brand_id"])
        fdd_id = int(payload["fdd_id"])
    except (JWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired download token",
        ) from exc

    doc = db.scalar(
        select(BrandFDDDocument).where(
            BrandFDDDocument.id == fdd_id,
            BrandFDDDocument.brand_id == brand_id,
        )
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FDD document not found")

    brand = db.scalar(
        select(Brand).where(Brand.id == brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    path = resolve_upload_path(doc.file_path)
    filename = f"{doc.title}.pdf" if doc.title else "fdd.pdf"
    return FileResponse(path, media_type=doc.mime_type, filename=filename)


@router.get("/owner-documents/{document_id}")
def download_owner_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if current_user.role != UserRole.franchise_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only franchise owners can download these documents",
        )
    doc = db.scalar(
        select(FranchiseOwnerDocument).where(
            FranchiseOwnerDocument.id == document_id,
            FranchiseOwnerDocument.franchise_owner_id == current_user.user_id,
        )
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    path = resolve_upload_path(doc.file_path)
    filename = doc.original_filename or f"{doc.title}.pdf"
    return FileResponse(path, media_type=doc.mime_type, filename=filename)
