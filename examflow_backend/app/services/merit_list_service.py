"""
EXAMFLOW – Merit List Service
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.merit_list_engine import MeritListEngine, MeritCandidate, MeritEntry
from app.models.models import (
    Candidate, EvaluationResult, QualificationDecision, QualificationStatus,
    SectionResult, MeritList, MeritListEntry, MeritListStatus, AuditLog, AuditAction
)
from app.schemas.schemas import GenerateMeritListRequest


class MeritListService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(self, request: GenerateMeritListRequest, actor) -> MeritList:
        exam_id = request.examination_id

        # Load qualified candidates
        qd_result = await self.db.execute(
            select(QualificationDecision).where(
                QualificationDecision.status == QualificationStatus.QUALIFIED
            )
        )
        all_qd = list(qd_result.scalars().all())

        # Build merit candidates
        merit_candidates: List[MeritCandidate] = []
        for qd in all_qd:
            cand = await self.db.get(Candidate, qd.candidate_id)
            if not cand or cand.examination_id != exam_id:
                continue

            er_result = await self.db.execute(
                select(EvaluationResult).where(EvaluationResult.id == qd.evaluation_result_id)
            )
            er = er_result.scalar_one_or_none()
            if not er:
                continue

            sr_result = await self.db.execute(
                select(SectionResult).where(SectionResult.evaluation_result_id == er.id)
            )
            section_scores = {sr.section_id: sr.raw_section_score for sr in sr_result.scalars()}

            merit_candidates.append(
                MeritCandidate(
                    candidate_id=cand.id,
                    roll_number=cand.roll_number,
                    full_name=cand.full_name,
                    date_of_birth=cand.date_of_birth,
                    category=cand.category,
                    is_pwd=cand.is_pwd,
                    normalised_score=er.normalised_score or er.score_after_proctoring or Decimal("0"),
                    score_after_proctoring=er.score_after_proctoring or Decimal("0"),
                    total_wrong=er.total_wrong,
                    section_scores=section_scores,
                    is_qualified=True,
                    evaluation_result_id=er.id,
                )
            )

        # Determine section order for tie-breakers (DL-006 placeholder: ascending section_id)
        section_order = sorted(
            {sid for mc in merit_candidates for sid in mc.section_scores.keys()}
        )

        engine = MeritListEngine(section_order=section_order)
        entries = engine.build_merit_list(merit_candidates)

        # Determine version
        existing = await self.db.execute(
            select(MeritList).where(MeritList.examination_id == exam_id)
            .order_by(MeritList.version.desc())
        )
        last = existing.scalars().first()
        version = (last.version + 1) if last else 1

        ml = MeritList(
            examination_id=exam_id,
            version=version,
            status=MeritListStatus.DRAFT,
            description=request.description,
            generated_at=datetime.now(timezone.utc),
        )
        self.db.add(ml)
        await self.db.flush()

        for entry in entries:
            self.db.add(MeritListEntry(
                merit_list_id=ml.id,
                candidate_id=entry.candidate_id,
                evaluation_result_id=entry.evaluation_result_id,
                overall_rank=entry.overall_rank,
                category_rank=entry.category_rank,
                final_score=entry.final_score,
                tie_breaker_applied=entry.tie_breaker_applied,
                is_allocated=entry.is_allocated,
                allocation_category=entry.allocation_category,
            ))

        self.db.add(AuditLog(
            actor_id=actor.id,
            action=AuditAction.CREATE,
            entity_type="MeritList",
            entity_id=str(ml.id),
            description=f"Merit list v{version} generated for exam {exam_id}",
        ))
        await self.db.flush()
        return ml

    async def get_latest(self, exam_id: int) -> Optional[MeritList]:
        result = await self.db.execute(
            select(MeritList).where(MeritList.examination_id == exam_id)
            .order_by(MeritList.version.desc())
        )
        return result.scalars().first()

    async def publish(self, merit_list_id: int, actor) -> dict:
        ml = await self.db.get(MeritList, merit_list_id)
        if not ml:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Merit list not found")
        ml.status = MeritListStatus.PUBLISHED
        self.db.add(AuditLog(
            actor_id=actor.id,
            action=AuditAction.UPDATE,
            entity_type="MeritList",
            entity_id=str(ml.id),
            description="Merit list published",
        ))
        await self.db.flush()
        return {"message": "Published", "merit_list_id": merit_list_id}
