"""Evaluation trigger endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.schemas.schemas import EvaluateRequest, EvaluationResultOut
from app.services.evaluation_service import EvaluationService
from app.models.user import User

router = APIRouter()


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_evaluation(
    body: EvaluateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR")),
):
    """
    Trigger evaluation for an examination (all candidates or a subset).
    Runs asynchronously in a background task.
    Returns job reference.
    """
    svc = EvaluationService(db)
    job_id = await svc.schedule_evaluation(body, actor=current_user)
    background_tasks.add_task(svc.run_evaluation_job, job_id)
    return {"message": "Evaluation scheduled", "job_id": job_id}


@router.get("/results/{candidate_id}", response_model=EvaluationResultOut)
async def get_candidate_result(
    candidate_id: int,
    version: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR", "AUDITOR")),
):
    svc = EvaluationService(db)
    result = await svc.get_result(candidate_id, version)
    if not result:
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    return result
