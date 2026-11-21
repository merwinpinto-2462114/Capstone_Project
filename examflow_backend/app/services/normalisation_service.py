"""
EXAMFLOW – Normalisation Service
Loads raw scores from DB, runs NormalisationEngine, persists results.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.normalisation_engine import (
    NormalisationEngine, ShiftRawData, NormalisationDenominatorError
)
from app.models.models import (
    Candidate, EvaluationResult, Shift, ShiftStatistics, AuditLog, AuditAction
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class NormalisationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._engine = NormalisationEngine(
            min_shift_size=settings.NORMALISATION_MIN_SHIFT_SIZE
        )

    async def normalise_examination(self, exam_id: int, actor) -> int:
        """
        Run normalisation for all shifts of an examination.
        Updates normalised_score on EvaluationResult records.
        Returns count of normalised candidates.
        """
        # Load latest evaluation results per candidate
        cands_result = await self.db.execute(
            select(Candidate).where(Candidate.examination_id == exam_id)
        )
        candidates = list(cands_result.scalars().all())

        # Build shift → candidate → raw_score map
        shift_data: Dict[int, Dict[int, any]] = {}
        for cand in candidates:
            eval_result = await self.db.execute(
                select(EvaluationResult)
                .where(EvaluationResult.candidate_id == cand.id)
                .order_by(EvaluationResult.version.desc())
            )
            er = eval_result.scalars().first()
            if er and er.score_after_proctoring is not None:
                shift_data.setdefault(cand.shift_id, {})[cand.id] = er.score_after_proctoring

        all_shift_data = [
            ShiftRawData(shift_id=sid, candidate_scores=scores)
            for sid, scores in shift_data.items()
        ]

        if not all_shift_data:
            return 0

        try:
            outputs = self._engine.normalise_all(all_shift_data)
        except NormalisationDenominatorError as exc:
            logger.error("Normalisation failed: %s", exc)
            self.db.add(AuditLog(
                actor_id=actor.id if actor else None,
                action=AuditAction.EVALUATE,
                entity_type="Normalisation",
                entity_id=str(exam_id),
                description=f"DECISION_LOG DL-005: {str(exc)}",
            ))
            raise

        # Persist normalised scores
        normalised_count = 0
        for out in outputs:
            er_result = await self.db.execute(
                select(EvaluationResult)
                .where(EvaluationResult.candidate_id == out.candidate_id)
                .order_by(EvaluationResult.version.desc())
            )
            er = er_result.scalars().first()
            if er:
                er.normalised_score = out.normalised_score
                er.is_normalised = True
                normalised_count += 1

        # Persist shift statistics
        for shift_raw in all_shift_data:
            stats = self._engine.compute_shift_statistics(shift_raw)
            existing_stats = await self.db.execute(
                select(ShiftStatistics).where(ShiftStatistics.shift_id == shift_raw.shift_id)
            )
            ss_obj = existing_stats.scalar_one_or_none()
            if not ss_obj:
                ss_obj = ShiftStatistics(shift_id=shift_raw.shift_id)
                self.db.add(ss_obj)
            ss_obj.candidate_count = stats.candidate_count
            ss_obj.mean_raw_score = stats.mean
            ss_obj.std_dev_raw_score = stats.std_dev
            ss_obj.computed_at = datetime.now(timezone.utc)

        await self.db.flush()
        return normalised_count
