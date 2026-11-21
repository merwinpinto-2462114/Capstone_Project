"""
EXAMFLOW – Re-Evaluation Service (Rule 11)
Enforces one-time restriction, creates versioned result, preserves history.
Fully transactional.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Candidate, ReEvaluationRequest, ReEvaluationStatus,
    EvaluationResult, AuditLog, AuditAction
)
from app.schemas.schemas import ReEvaluationCreate
from app.services.evaluation_service import EvaluationService
from app.schemas.schemas import EvaluateRequest

logger = logging.getLogger(__name__)


class ReEvaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def request_re_evaluation(
        self, data: ReEvaluationCreate, actor
    ) -> ReEvaluationRequest:
        # Rule 11: Exactly one re-evaluation per candidate
        existing = await self.db.execute(
            select(ReEvaluationRequest).where(
                ReEvaluationRequest.candidate_id == data.candidate_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=(
                    "Re-evaluation already requested for this candidate. "
                    "Only one re-evaluation is permitted per candidate (Rule 11)."
                ),
            )

        # Get the latest evaluation result to preserve as previous
        prev_result = await self.db.execute(
            select(EvaluationResult)
            .where(EvaluationResult.candidate_id == data.candidate_id)
            .order_by(EvaluationResult.version.desc())
        )
        prev = prev_result.scalars().first()
        if not prev:
            raise HTTPException(status_code=404, detail="No evaluation result found for candidate")

        # Get examination_id
        cand = await self.db.get(Candidate, data.candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")

        # Create re-evaluation request record
        req = ReEvaluationRequest(
            candidate_id=data.candidate_id,
            initiated_by_user_id=actor.id,
            previous_result_id=prev.id,
            answer_key_version_id=data.answer_key_version_id,
            reason=data.reason,
            status=ReEvaluationStatus.IN_PROGRESS,
            request_count=1,
        )
        self.db.add(req)
        await self.db.flush()

        # Run the new evaluation (synchronously for re-eval to ensure atomicity)
        eval_svc = EvaluationService(self.db)
        eval_request = EvaluateRequest(
            examination_id=cand.examination_id,
            answer_key_version_id=data.answer_key_version_id,
            candidate_ids=[data.candidate_id],
        )
        await eval_svc._run_evaluation(eval_request)

        # Get the new result
        new_result = await self.db.execute(
            select(EvaluationResult)
            .where(EvaluationResult.candidate_id == data.candidate_id)
            .order_by(EvaluationResult.version.desc())
        )
        new = new_result.scalars().first()

        req.new_result_id = new.id if new else None
        req.status = ReEvaluationStatus.COMPLETED
        req.completed_at = datetime.now(timezone.utc)

        # Audit
        self.db.add(AuditLog(
            actor_id=actor.id,
            action=AuditAction.RE_EVALUATE,
            entity_type="ReEvaluationRequest",
            entity_id=str(req.id),
            description=f"Re-evaluation for candidate {data.candidate_id}. Reason: {data.reason}",
        ))

        await self.db.flush()
        return req

    async def get_by_candidate(self, candidate_id: int) -> Optional[ReEvaluationRequest]:
        result = await self.db.execute(
            select(ReEvaluationRequest).where(
                ReEvaluationRequest.candidate_id == candidate_id
            )
        )
        return result.scalar_one_or_none()
