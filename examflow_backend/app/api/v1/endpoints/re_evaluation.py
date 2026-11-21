"""Re-evaluation endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.schemas.schemas import ReEvaluationCreate, ReEvaluationOut
from app.services.re_evaluation_service import ReEvaluationService
from app.models.user import User

router = APIRouter()


@router.post("/request", response_model=ReEvaluationOut, status_code=201)
async def request_re_evaluation(
    body: ReEvaluationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    """
    Request a re-evaluation for a candidate.
    Enforces one-time-only restriction (Rule 11).
    Transactional: creates new result version, preserves old result.
    """
    svc = ReEvaluationService(db)
    return await svc.request_re_evaluation(body, actor=current_user)


@router.get("/{candidate_id}", response_model=ReEvaluationOut)
async def get_re_evaluation(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "AUDITOR")),
):
    svc = ReEvaluationService(db)
    req = await svc.get_by_candidate(candidate_id)
    if not req:
        raise HTTPException(status_code=404, detail="No re-evaluation request found")
    return req
