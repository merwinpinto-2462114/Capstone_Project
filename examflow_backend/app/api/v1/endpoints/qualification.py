"""Qualification endpoints"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.schemas.schemas import QualificationDecisionOut
from app.services.qualification_service import QualificationService
from app.models.user import User

router = APIRouter()


@router.post("/run/{examination_id}", status_code=202)
async def run_qualification(
    examination_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR")),
):
    svc = QualificationService(db)
    count = await svc.run_qualification(examination_id, actor=current_user)
    return {"message": "Qualification complete", "decisions_recorded": count}


@router.get("/candidate/{candidate_id}", response_model=QualificationDecisionOut)
async def get_qualification(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR", "AUDITOR")),
):
    svc = QualificationService(db)
    return await svc.get_decision(candidate_id)
