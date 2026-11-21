"""Challenge management endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles, get_current_user
from app.schemas.schemas import ChallengeCreate, ChallengeDecisionUpdate, ChallengeOut
from app.services.challenge_service import ChallengeService
from app.models.user import User

router = APIRouter()


@router.post("/", response_model=ChallengeOut, status_code=201)
async def submit_challenge(
    body: ChallengeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ChallengeService(db)
    return await svc.submit_challenge(body, actor=current_user)


@router.get("/", response_model=List[ChallengeOut])
async def list_challenges(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR")),
):
    svc = ChallengeService(db)
    return await svc.list_by_examination(exam_id)


@router.patch("/{challenge_id}/decision", response_model=ChallengeOut)
async def decide_challenge(
    challenge_id: int,
    body: ChallengeDecisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = ChallengeService(db)
    return await svc.record_decision(challenge_id, body, actor=current_user)
