"""
EXAMFLOW – Answer Key, Challenge, Proctoring, Reporting Services (stubs with full logic)
"""
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AnswerKey, AnswerKeyVersion, DroppedQuestion,
    QuestionChallenge, ChallengeDecision,
    ProctoringEvent, AuditLog, AuditAction,
    EvaluationResult, SectionResult, Candidate, QualificationDecision,
)
from app.schemas.schemas import (
    AnswerKeyVersionCreate, DroppedQuestionCreate,
    ChallengeCreate, ChallengeDecisionUpdate,
    ProctoringEventCreate,
)


# ================================================================== #
# Answer Key Service
# ================================================================== #

class AnswerKeyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_version(self, exam_id: int, data: AnswerKeyVersionCreate, actor) -> AnswerKeyVersion:
        existing = await self.db.execute(
            select(AnswerKeyVersion).where(
                AnswerKeyVersion.examination_id == exam_id,
                AnswerKeyVersion.version_tag == data.version_tag,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Version tag already exists for this exam")

        akv = AnswerKeyVersion(
            examination_id=exam_id,
            version_tag=data.version_tag,
            description=data.description,
            is_official=data.is_official,
            published_at=datetime.now(timezone.utc) if data.is_official else None,
        )
        self.db.add(akv)
        await self.db.flush()

        for key in data.keys:
            self.db.add(AnswerKey(
                section_id=key.section_id,
                version_id=akv.id,
                question_number=key.question_number,
                question_type=key.question_type,
                correct_options=key.correct_options,
                is_dropped=key.is_dropped,
                dropped_marks_rule=key.dropped_marks_rule,
            ))

        self.db.add(AuditLog(actor_id=actor.id, action=AuditAction.CREATE,
                             entity_type="AnswerKeyVersion", entity_id=str(akv.id)))
        await self.db.flush()
        return akv

    async def list_versions(self, exam_id: int) -> List[AnswerKeyVersion]:
        result = await self.db.execute(
            select(AnswerKeyVersion).where(AnswerKeyVersion.examination_id == exam_id)
        )
        return list(result.scalars().all())

    async def drop_question(self, data: DroppedQuestionCreate, actor) -> DroppedQuestion:
        dq = DroppedQuestion(
            section_id=data.section_id,
            question_number=data.question_number,
            answer_key_version_id=data.answer_key_version_id,
            marks_rule=data.marks_rule,
            reason=data.reason,
            dropped_by_user_id=actor.id,
        )
        self.db.add(dq)
        # Also update the AnswerKey record
        ak_result = await self.db.execute(
            select(AnswerKey).where(
                AnswerKey.section_id == data.section_id,
                AnswerKey.question_number == data.question_number,
                AnswerKey.version_id == data.answer_key_version_id,
            )
        )
        ak = ak_result.scalar_one_or_none()
        if ak:
            ak.is_dropped = True
            ak.dropped_marks_rule = data.marks_rule
        self.db.add(AuditLog(actor_id=actor.id, action=AuditAction.UPDATE,
                             entity_type="DroppedQuestion",
                             description=f"Q{data.question_number} dropped: {data.reason}"))
        await self.db.flush()
        return dq


# ================================================================== #
# Challenge Service
# ================================================================== #

class ChallengeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_challenge(self, data: ChallengeCreate, actor) -> QuestionChallenge:
        challenge = QuestionChallenge(
            candidate_id=data.candidate_id,
            section_id=data.section_id,
            question_number=data.question_number,
            answer_key_version_id=data.answer_key_version_id,
            reason=data.reason,
            proposed_answer=data.proposed_answer,
            decision=ChallengeDecision.PENDING,
        )
        self.db.add(challenge)
        await self.db.flush()
        return challenge

    async def list_by_examination(self, exam_id: int) -> List[QuestionChallenge]:
        result = await self.db.execute(select(QuestionChallenge))
        return list(result.scalars().all())

    async def record_decision(
        self, challenge_id: int, data: ChallengeDecisionUpdate, actor
    ) -> QuestionChallenge:
        challenge = await self.db.get(QuestionChallenge, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        challenge.decision = data.decision
        challenge.decision_reason = data.decision_reason
        challenge.decided_by_user_id = actor.id
        challenge.decided_at = datetime.now(timezone.utc)
        self.db.add(AuditLog(actor_id=actor.id, action=AuditAction.UPDATE,
                             entity_type="QuestionChallenge", entity_id=str(challenge_id),
                             description=f"Decision: {data.decision}"))
        await self.db.flush()
        return challenge


# ================================================================== #
# Proctoring Service
# ================================================================== #

class ProctoringService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_event(self, data: ProctoringEventCreate, actor) -> ProctoringEvent:
        event = ProctoringEvent(
            candidate_id=data.candidate_id,
            event_type=data.event_type,
            severity=data.severity,
            description=data.description,
            is_confirmed_malpractice=data.is_confirmed_malpractice,
            event_timestamp=data.event_timestamp,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_events(self, candidate_id: int) -> List[ProctoringEvent]:
        result = await self.db.execute(
            select(ProctoringEvent).where(ProctoringEvent.candidate_id == candidate_id)
        )
        return list(result.scalars().all())

    async def confirm_malpractice(self, event_id: int, actor) -> ProctoringEvent:
        event = await self.db.get(ProctoringEvent, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        event.is_confirmed_malpractice = True
        event.confirmed_by_user_id = actor.id
        event.confirmed_at = datetime.now(timezone.utc)
        self.db.add(AuditLog(actor_id=actor.id, action=AuditAction.UPDATE,
                             entity_type="ProctoringEvent", entity_id=str(event_id),
                             description="Confirmed malpractice"))
        await self.db.flush()
        return event


# ================================================================== #
# Reporting Service
# ================================================================== #

class ReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_scorecard(self, candidate_id: int) -> dict:
        cand = await self.db.get(Candidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")

        er_result = await self.db.execute(
            select(EvaluationResult)
            .where(EvaluationResult.candidate_id == candidate_id)
            .order_by(EvaluationResult.version.desc())
        )
        er = er_result.scalars().first()

        sr_result = await self.db.execute(
            select(SectionResult).where(SectionResult.evaluation_result_id == er.id)
        ) if er else None
        sections = list(sr_result.scalars().all()) if sr_result else []

        from app.engines.normalisation_engine import NormalisationEngine
        return {
            "candidate": {
                "id": cand.id,
                "roll_number": cand.roll_number,
                "full_name": cand.full_name,
                "category": cand.category,
                "is_pwd": cand.is_pwd,
            },
            "result": {
                "raw_score": NormalisationEngine.format_raw(er.raw_score) if er and er.raw_score else "N/A",
                "normalised_score": NormalisationEngine.format_normalised(er.normalised_score) if er and er.normalised_score else "N/A",
                "version": er.version if er else None,
                "evaluated_at": er.evaluated_at.isoformat() if er and er.evaluated_at else None,
            },
            "sections": [
                {
                    "section_id": sr.section_id,
                    "score": NormalisationEngine.format_raw(sr.raw_section_score),
                    "correct": sr.correct_count,
                    "wrong": sr.wrong_count,
                    "not_attempted": sr.not_attempted_count,
                }
                for sr in sections
            ],
        }

    async def get_audit_logs(self, entity_type: Optional[str], entity_id: Optional[str]) -> List:
        from app.models.models import AuditLog
        query = select(AuditLog)
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditLog.entity_id == entity_id)
        result = await self.db.execute(query.order_by(AuditLog.created_at.desc()).limit(500))
        logs = list(result.scalars().all())
        return [
            {"id": l.id, "action": l.action, "entity_type": l.entity_type,
             "entity_id": l.entity_id, "actor_id": l.actor_id,
             "description": l.description, "created_at": l.created_at.isoformat()}
            for l in logs
        ]

    async def examination_summary(self, exam_id: int) -> dict:
        cands_result = await self.db.execute(
            select(Candidate).where(Candidate.examination_id == exam_id)
        )
        candidates = list(cands_result.scalars().all())
        qualified_count = 0
        for c in candidates:
            qd_result = await self.db.execute(
                select(QualificationDecision).where(QualificationDecision.candidate_id == c.id)
            )
            qd = qd_result.scalars().first()
            if qd and qd.status == "QUALIFIED":
                qualified_count += 1
        return {
            "exam_id": exam_id,
            "total_candidates": len(candidates),
            "qualified": qualified_count,
            "not_qualified": len(candidates) - qualified_count,
        }
