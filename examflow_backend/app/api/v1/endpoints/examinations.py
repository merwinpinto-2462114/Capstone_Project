"""Examination configuration endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles, PaginationParams
from app.schemas.schemas import (
    ExaminationCreate, ExaminationUpdate, ExaminationOut,
    ExaminationSectionCreate, ExaminationSectionOut,
    ShiftCreate, ShiftOut,
)
from app.services.examination_service import ExaminationService
from app.models.user import User

router = APIRouter()


@router.post("/", response_model=ExaminationOut, status_code=status.HTTP_201_CREATED)
async def create_examination(
    body: ExaminationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = ExaminationService(db)
    return await svc.create_examination(body, actor=current_user)


@router.get("/", response_model=List[ExaminationOut])
async def list_examinations(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ExaminationService(db)
    return await svc.list_examinations(pagination.offset, pagination.page_size)


@router.get("/{exam_id}", response_model=ExaminationOut)
async def get_examination(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ExaminationService(db)
    exam = await svc.get_by_id(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Examination not found")
    return exam


@router.patch("/{exam_id}", response_model=ExaminationOut)
async def update_examination(
    exam_id: int,
    body: ExaminationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = ExaminationService(db)
    return await svc.update_examination(exam_id, body, actor=current_user)


# ---- Sections ----

@router.post("/{exam_id}/sections", response_model=ExaminationSectionOut, status_code=201)
async def add_section(
    exam_id: int,
    body: ExaminationSectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = ExaminationService(db)
    return await svc.add_section(exam_id, body, actor=current_user)


@router.get("/{exam_id}/sections", response_model=List[ExaminationSectionOut])
async def list_sections(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ExaminationService(db)
    return await svc.list_sections(exam_id)


# ---- Shifts ----

@router.post("/{exam_id}/shifts", response_model=ShiftOut, status_code=201)
async def add_shift(
    exam_id: int,
    body: ShiftCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = ExaminationService(db)
    return await svc.add_shift(exam_id, body, actor=current_user)


@router.get("/{exam_id}/shifts", response_model=List[ShiftOut])
async def list_shifts(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ExaminationService(db)
    return await svc.list_shifts(exam_id)
