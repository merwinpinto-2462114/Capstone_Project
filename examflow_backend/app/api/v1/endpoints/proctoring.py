"""Proctoring event endpoints"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.schemas.schemas import ProctoringEventCreate, ProctoringEventOut
from app.services.proctoring_service import ProctoringService
from app.models.user import User

router = APIRouter()


@router.post("/events", response_model=ProctoringEventOut, status_code=201)
async def record_event(
    body: ProctoringEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "PROCTOR", "EXAM_ADMIN")),
):
    svc = ProctoringService(db)
    return await svc.record_event(body, actor=current_user)


@router.get("/events/{candidate_id}", response_model=List[ProctoringEventOut])
async def list_candidate_events(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "PROCTOR", "EXAM_ADMIN", "AUDITOR")),
):
    svc = ProctoringService(db)
    return await svc.list_events(candidate_id)


@router.patch("/events/{event_id}/confirm-malpractice", response_model=ProctoringEventOut)
async def confirm_malpractice(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = ProctoringService(db)
    return await svc.confirm_malpractice(event_id, actor=current_user)
