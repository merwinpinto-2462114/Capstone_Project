"""Reports endpoints – scorecards, audit logs, summary reports"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles, get_current_user
from app.services.reporting_service import ReportingService
from app.models.user import User

router = APIRouter()


@router.get("/scorecard/{candidate_id}")
async def get_scorecard(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ReportingService(db)
    return await svc.get_scorecard(candidate_id)


@router.get("/audit-logs")
async def get_audit_logs(
    entity_type: str = None,
    entity_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "AUDITOR")),
):
    svc = ReportingService(db)
    return await svc.get_audit_logs(entity_type, entity_id)


@router.get("/examination-summary/{exam_id}")
async def examination_summary(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR", "AUDITOR")),
):
    svc = ReportingService(db)
    return await svc.examination_summary(exam_id)
