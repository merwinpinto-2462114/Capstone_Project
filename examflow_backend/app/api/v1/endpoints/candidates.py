"""Candidate management endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles, PaginationParams
from app.schemas.schemas import CandidateCreate, CandidateBulkCreate, CandidateOut, ResponseIngest, ResponseOut
from app.services.candidate_service import CandidateService
from app.models.user import User

router = APIRouter()


@router.post("/", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def register_candidate(
    body: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = CandidateService(db)
    return await svc.register_candidate(body, actor=current_user)


@router.post("/bulk", response_model=List[CandidateOut], status_code=status.HTTP_201_CREATED)
async def bulk_register_candidates(
    body: CandidateBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = CandidateService(db)
    return await svc.bulk_register(body.candidates, actor=current_user)


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = CandidateService(db)
    c = await svc.get_by_id(candidate_id)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return c


@router.get("/", response_model=List[CandidateOut])
async def list_candidates(
    examination_id: int,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR", "AUDITOR")),
):
    svc = CandidateService(db)
    return await svc.list_by_examination(examination_id, pagination.offset, pagination.page_size)


# ---- Response ingestion ----

@router.post("/responses", response_model=List[ResponseOut], status_code=201)
async def ingest_responses(
    body: ResponseIngest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    """
    Ingest candidate responses.
    Late responses are auto-converted to NOT_ATTEMPTED.
    MARKED_FOR_REVIEW without an option is preserved but scored as NOT_ATTEMPTED.
    """
    svc = CandidateService(db)
    return await svc.ingest_responses(body, actor=current_user)
