"""Answer key management endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.schemas.schemas import AnswerKeyVersionCreate, AnswerKeyVersionOut, DroppedQuestionCreate, DroppedQuestionOut
from app.services.answer_key_service import AnswerKeyService
from app.models.user import User

router = APIRouter()


@router.post("/versions", response_model=AnswerKeyVersionOut, status_code=201)
async def create_answer_key_version(
    exam_id: int,
    body: AnswerKeyVersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = AnswerKeyService(db)
    return await svc.create_version(exam_id, body, actor=current_user)


@router.get("/versions", response_model=List[AnswerKeyVersionOut])
async def list_versions(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR", "AUDITOR")),
):
    svc = AnswerKeyService(db)
    return await svc.list_versions(exam_id)


@router.post("/dropped-questions", response_model=DroppedQuestionOut, status_code=201)
async def mark_question_dropped(
    body: DroppedQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = AnswerKeyService(db)
    return await svc.drop_question(body, actor=current_user)
