"""
EXAMFLOW – Qualification Service
Runs QualificationEngine for all candidates and persists decisions.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.qualification_engine import (
    QualificationEngine, QualificationInput, SectionScoreInput, SectionCutoffConfig
)
from app.models.models import (
    Candidate, EvaluationResult, ExaminationSection, SectionResult,
    QualificationDecision, QualificationStatus, ProctoringEvent, AuditLog, AuditAction
)
from app.schemas.schemas import QualificationDecisionOut

logger = logging.getLogger(__name__)


class QualificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._engine = QualificationEngine()

    async def run_qualification(self, exam_id: int, actor) -> int:
        # Load sections
        secs_result = await self.db.execute(
            select(ExaminationSection)
            .where(ExaminationSection.examination_id == exam_id)
        )
        sections = list(secs_result.scalars().all())
        section_configs = [
            SectionCutoffConfig(
                section_id=s.id,
                section_code=s.section_code,
                is_mandatory=s.is_mandatory,
                cutoff_gen=s.cutoff_gen,
                cutoff_obc=s.cutoff_obc,
                cutoff_sc=s.cutoff_sc,
                cutoff_st=s.cutoff_st,
                cutoff_ews=s.cutoff_ews,
            )
            for s in sections
        ]

        # Load candidates
        cands_result = await self.db.execute(
            select(Candidate).where(Candidate.examination_id == exam_id)
        )
        candidates = list(cands_result.scalars().all())
        count = 0

        for candidate in candidates:
            # Latest evaluation result
            er_result = await self.db.execute(
                select(EvaluationResult)
                .where(EvaluationResult.candidate_id == candidate.id)
                .order_by(EvaluationResult.version.desc())
            )
            er = er_result.scalars().first()
            if not er:
                continue

            # Section scores
            sr_result = await self.db.execute(
                select(SectionResult).where(SectionResult.evaluation_result_id == er.id)
            )
            section_scores = [
                SectionScoreInput(
                    section_id=sr.section_id,
                    raw_section_score=sr.raw_section_score,
                    was_attempted=sr.correct_count + sr.wrong_count > 0,
                )
                for sr in sr_result.scalars().all()
            ]

            # Proctoring
            proc_result = await self.db.execute(
                select(ProctoringEvent).where(ProctoringEvent.candidate_id == candidate.id)
            )
            events = list(proc_result.scalars().all())
            max_severity = max((e.severity for e in events), default=0)
            confirmed_malpractice = any(e.is_confirmed_malpractice for e in events)

            is_disq = max_severity >= 10 or confirmed_malpractice
            disq_reason = None
            if is_disq:
                disq_reason = "CONFIRMED_MALPRACTICE" if confirmed_malpractice else f"SEVERITY_{max_severity}"

            qinput = QualificationInput(
                candidate_id=candidate.id,
                category=candidate.category,
                is_pwd=candidate.is_pwd,
                attempt_percentage=er.attempt_percentage or 0,
                score_after_proctoring=er.score_after_proctoring or er.raw_score or 0,
                normalised_score=er.normalised_score,
                is_disqualified_by_proctoring=is_disq,
                disqualification_reason=disq_reason,
                section_scores=section_scores,
                overall_cutoff_gen=None,  # TODO: load from examination configuration
            )

            qresult = self._engine.qualify(qinput, section_configs)

            # Persist (upsert)
            existing_q = await self.db.execute(
                select(QualificationDecision).where(
                    QualificationDecision.candidate_id == candidate.id,
                    QualificationDecision.evaluation_result_id == er.id,
                )
            )
            qd = existing_q.scalar_one_or_none()
            if not qd:
                qd = QualificationDecision(
                    candidate_id=candidate.id,
                    evaluation_result_id=er.id,
                )
                self.db.add(qd)

            qd.status = qresult.status
            qd.reasons = qresult.to_reasons_json()
            qd.category_relaxation_percentage = qresult.category_relaxation_percentage
            qd.effective_cutoff = qresult.effective_overall_cutoff
            qd.overall_cutoff_applied = qresult.overall_cutoff_gen
            qd.decided_at = datetime.now(timezone.utc)

            count += 1

        await self.db.flush()
        return count

    async def get_decision(self, candidate_id: int) -> Optional[QualificationDecision]:
        result = await self.db.execute(
            select(QualificationDecision)
            .where(QualificationDecision.candidate_id == candidate_id)
            .order_by(QualificationDecision.decided_at.desc())
        )
        return result.scalars().first()
