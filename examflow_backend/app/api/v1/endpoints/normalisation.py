"""Normalisation endpoints"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.services.normalisation_service import NormalisationService
from app.models.user import User

router = APIRouter()


@router.post("/run/{examination_id}", status_code=202)
async def run_normalisation(
    examination_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR")),
):
    svc = NormalisationService(db)
    result = await svc.normalise_examination(examination_id, actor=current_user)
    return {"message": "Normalisation complete", "candidates_normalised": result}
