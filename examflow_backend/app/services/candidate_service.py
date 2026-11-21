"""
EXAMFLOW – Candidate Service
Registration, bulk import, response ingestion.
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Candidate, CandidateResponse, ResponseStatus, AuditLog, AuditAction
)
from app.schemas.schemas import CandidateCreate, ResponseIngest, ResponseItem


class CandidateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_candidate(self, data: CandidateCreate, actor) -> Candidate:
        existing = await self.db.execute(
            select(Candidate).where(
                Candidate.roll_number == data.roll_number,
                Candidate.examination_id == data.examination_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Duplicate roll_number for this examination")

        c = Candidate(
            roll_number=data.roll_number,
            full_name=data.full_name,
            date_of_birth=data.date_of_birth,
            category=data.category,
            is_pwd=data.is_pwd,
            email=str(data.email) if data.email else None,
            phone=data.phone,
            examination_id=data.examination_id,
            shift_id=data.shift_id,
        )
        self.db.add(c)
        await self.db.flush()
        self._audit(actor, AuditAction.CREATE, "Candidate", str(c.id))
        return c

    async def bulk_register(self, candidates: List[CandidateCreate], actor) -> List[Candidate]:
        created = []
        for item in candidates:
            created.append(await self.register_candidate(item, actor))
        return created

    async def get_by_id(self, candidate_id: int) -> Optional[Candidate]:
        result = await self.db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def list_by_examination(self, exam_id: int, offset: int, limit: int) -> List[Candidate]:
        result = await self.db.execute(
            select(Candidate)
            .where(Candidate.examination_id == exam_id)
            .offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def ingest_responses(self, data: ResponseIngest, actor) -> List[CandidateResponse]:
        candidate = await self.get_by_id(data.candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        saved = []
        for item in data.responses:
            # Duplicate-response protection
            existing = await self.db.execute(
                select(CandidateResponse).where(
                    CandidateResponse.candidate_id == data.candidate_id,
                    CandidateResponse.section_id == item.section_id,
                    CandidateResponse.question_number == item.question_number,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate response: section={item.section_id} Q{item.question_number}",
                )

            effective_status = self._compute_effective_status(item)
            resp = CandidateResponse(
                candidate_id=data.candidate_id,
                section_id=item.section_id,
                question_number=item.question_number,
                selected_option=item.selected_option,
                status=item.status,
                effective_status=effective_status,
                response_timestamp=item.response_timestamp,
                is_late=item.is_late,
            )
            self.db.add(resp)
            saved.append(resp)

        await self.db.flush()
        return saved

    @staticmethod
    def _compute_effective_status(item: ResponseItem) -> str:
        """
        Rule 4: Late responses → NOT_ATTEMPTED.
        MARKED_FOR_REVIEW without an option → NOT_ATTEMPTED for scoring.
        """
        if item.is_late:
            return ResponseStatus.NOT_ATTEMPTED
        if item.status == ResponseStatus.MARKED_FOR_REVIEW and not item.selected_option:
            return ResponseStatus.NOT_ATTEMPTED
        return item.status

    def _audit(self, actor, action, entity_type, entity_id):
        self.db.add(AuditLog(
            actor_id=actor.id if actor else None,
            action=action, entity_type=entity_type, entity_id=entity_id
        ))
