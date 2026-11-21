"""
EXAMFLOW – Evaluation Service
Orchestrates the EvaluationEngine against database records.
Handles concurrent-request protection and versioning.
"""
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.engines.evaluation_engine import (
    EvaluationEngine, SectionConfig, AnswerKeyEntry, ResponseEntry, EvaluationOutput
)
from app.engines.normalisation_engine import NormalisationEngine
from app.engines.qualification_engine import QualificationEngine
from app.models.models import (
    Candidate, CandidateResponse, ExaminationSection,
    AnswerKey, AnswerKeyVersion, EvaluationResult, SectionResult,
    ProctoringEvent, EvaluationStatus, AuditLog, AuditAction, ResponseStatus
)
from app.schemas.schemas import EvaluateRequest

logger = logging.getLogger(__name__)

# In-memory job registry (use Redis/DB in production)
_job_registry: Dict[str, dict] = {}


class EvaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._engine = EvaluationEngine()

    async def schedule_evaluation(self, request: EvaluateRequest, actor) -> str:
        job_id = str(uuid.uuid4())
        _job_registry[job_id] = {
            "request": request,
            "actor_id": actor.id,
            "status": "SCHEDULED",
        }
        return job_id

    async def run_evaluation_job(self, job_id: str):
        job = _job_registry.get(job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return
        try:
            job["status"] = "RUNNING"
            request: EvaluateRequest = job["request"]
            await self._run_evaluation(request)
            job["status"] = "COMPLETE"
        except Exception as exc:
            logger.exception("Evaluation job %s failed", job_id)
            job["status"] = "FAILED"
            job["error"] = str(exc)

    async def _run_evaluation(self, request: EvaluateRequest):
        """Core evaluation pipeline for all candidates in an examination."""
        exam_id = request.examination_id
        akv_id = request.answer_key_version_id

        # Load sections
        sections_result = await self.db.execute(
            select(ExaminationSection)
            .where(ExaminationSection.examination_id == exam_id)
            .order_by(ExaminationSection.section_order)
        )
        sections = list(sections_result.scalars().all())
        section_configs = [
            SectionConfig(
                section_id=s.id,
                section_code=s.section_code,
                total_questions=s.total_questions,
                max_marks=s.max_marks,
                marks_per_correct=s.marks_per_correct,
                negative_marks_per_wrong=s.negative_marks_per_wrong,
                is_mandatory=s.is_mandatory,
            )
            for s in sections
        ]
        section_id_set = {s.id for s in sections}

        # Load answer keys for this version
        ak_result = await self.db.execute(
            select(AnswerKey)
            .where(
                AnswerKey.version_id == akv_id,
                AnswerKey.section_id.in_(section_id_set),
            )
        )
        all_keys = list(ak_result.scalars().all())
        keys_by_section: Dict[int, List[AnswerKeyEntry]] = {}
        for ak in all_keys:
            entry = AnswerKeyEntry(
                question_number=ak.question_number,
                question_type=ak.question_type,
                correct_options=set(ak.correct_options.split(",")),
                is_dropped=ak.is_dropped,
                dropped_marks_rule=ak.dropped_marks_rule,
            )
            keys_by_section.setdefault(ak.section_id, []).append(entry)

        # Load candidates
        cand_query = select(Candidate).where(Candidate.examination_id == exam_id)
        if request.candidate_ids:
            cand_query = cand_query.where(Candidate.id.in_(request.candidate_ids))
        cands_result = await self.db.execute(cand_query)
        candidates = list(cands_result.scalars().all())

        for candidate in candidates:
            await self._evaluate_candidate(candidate, section_configs, keys_by_section, akv_id)

    async def _evaluate_candidate(
        self,
        candidate: Candidate,
        section_configs: List[SectionConfig],
        keys_by_section: Dict[int, List[AnswerKeyEntry]],
        akv_id: int,
    ):
        # Load responses
        resp_result = await self.db.execute(
            select(CandidateResponse).where(CandidateResponse.candidate_id == candidate.id)
        )
        responses = list(resp_result.scalars().all())
        responses_by_section: Dict[int, List[ResponseEntry]] = {}
        for r in responses:
            opts = set(r.selected_option.split(",")) if r.selected_option else set()
            entry = ResponseEntry(
                question_number=r.question_number,
                selected_options=opts,
                effective_status=r.effective_status,
                is_late=r.is_late,
            )
            responses_by_section.setdefault(r.section_id, []).append(entry)

        # Load proctoring events
        proc_result = await self.db.execute(
            select(ProctoringEvent).where(ProctoringEvent.candidate_id == candidate.id)
        )
        events = list(proc_result.scalars().all())
        max_severity = max((e.severity for e in events), default=0)
        confirmed_malpractice = any(e.is_confirmed_malpractice for e in events)

        # Run engine
        output: EvaluationOutput = self._engine.evaluate(
            candidate_id=candidate.id,
            sections=section_configs,
            answer_keys_by_section=keys_by_section,
            responses_by_section=responses_by_section,
            proctoring_max_severity=max_severity,
            confirmed_malpractice=confirmed_malpractice,
        )

        # Apply proctoring penalty
        from app.engines.evaluation_engine import ProctoringPenaltyEngine
        penalty_engine = ProctoringPenaltyEngine()
        penalty_result = penalty_engine.apply_penalty(
            output.raw_score, max_severity, confirmed_malpractice
        )

        # Determine version (increment for re-eval)
        version_result = await self.db.execute(
            select(EvaluationResult).where(EvaluationResult.candidate_id == candidate.id)
        )
        existing = list(version_result.scalars().all())
        version = max((e.version for e in existing), default=0) + 1

        eval_result = EvaluationResult(
            candidate_id=candidate.id,
            answer_key_version_id=akv_id,
            version=version,
            status=EvaluationStatus.COMPLETED,
            raw_score=output.raw_score,
            total_correct=output.total_correct,
            total_wrong=output.total_wrong,
            total_not_attempted=output.total_not_attempted,
            total_marked_review_no_option=output.total_marked_review_no_option,
            negative_marks_deducted=output.negative_marks_deducted,
            proctoring_penalty_percentage=penalty_result.penalty_percentage,
            proctoring_penalty_marks=penalty_result.penalty_marks,
            score_after_proctoring=penalty_result.score_after_penalty,
            is_normalised=False,
            attempt_percentage=output.attempt_percentage,
            evaluated_at=datetime.now(timezone.utc),
        )
        self.db.add(eval_result)
        await self.db.flush()

        # Save section results
        for ss in output.section_scores:
            sr = SectionResult(
                evaluation_result_id=eval_result.id,
                section_id=ss.section_id,
                raw_section_score=ss.raw_section_score,
                correct_count=ss.correct_count,
                wrong_count=ss.wrong_count,
                not_attempted_count=ss.not_attempted_count,
                negative_marks=ss.negative_marks,
            )
            self.db.add(sr)

        await self.db.flush()

    async def get_result(self, candidate_id: int, version: int) -> Optional[EvaluationResult]:
        result = await self.db.execute(
            select(EvaluationResult)
            .where(
                EvaluationResult.candidate_id == candidate_id,
                EvaluationResult.version == version,
            )
            .options(selectinload(EvaluationResult.section_results))
        )
        return result.scalar_one_or_none()
