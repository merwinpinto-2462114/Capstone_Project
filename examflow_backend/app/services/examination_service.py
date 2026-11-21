"""
EXAMFLOW – Examination Service
Handles creation, update and validation of examinations, sections and shifts.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Examination, ExaminationSection, Shift, AuditLog, AuditAction
from app.schemas.schemas import (
    ExaminationCreate, ExaminationUpdate,
    ExaminationSectionCreate, ShiftCreate,
)


class ExaminationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_examination(self, data: ExaminationCreate, actor) -> Examination:
        # Duplicate code check
        existing = await self.db.execute(
            select(Examination).where(Examination.exam_code == data.exam_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="exam_code already exists")

        exam = Examination(
            name=data.name,
            exam_code=data.exam_code,
            description=data.description,
            duration_minutes=data.duration_minutes,
            normalisation_enabled=data.normalisation_enabled,
        )
        self.db.add(exam)
        await self.db.flush()
        await self.db.refresh(exam)
        self._audit(actor, AuditAction.CREATE, "Examination", str(exam.id))
        return exam

    async def get_by_id(self, exam_id: int) -> Optional[Examination]:
        result = await self.db.execute(
            select(Examination).where(Examination.id == exam_id)
        )
        return result.scalar_one_or_none()

    async def list_examinations(self, offset: int, limit: int) -> List[Examination]:
        result = await self.db.execute(
            select(Examination).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def update_examination(self, exam_id: int, data: ExaminationUpdate, actor) -> Examination:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Examination not found")
        if exam.evaluation_locked:
            raise HTTPException(status_code=409, detail="Examination is locked for evaluation")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(exam, field, value)

        await self.db.flush()
        self._audit(actor, AuditAction.UPDATE, "Examination", str(exam_id))
        return exam

    async def add_section(self, exam_id: int, data: ExaminationSectionCreate, actor) -> ExaminationSection:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Examination not found")

        section = ExaminationSection(
            examination_id=exam_id,
            name=data.name,
            section_code=data.section_code,
            section_order=data.section_order,
            total_questions=data.total_questions,
            max_marks=data.max_marks,
            marks_per_correct=data.marks_per_correct,
            negative_marks_per_wrong=data.negative_marks_per_wrong,
            cutoff_gen=data.cutoff_gen,
            cutoff_obc=data.cutoff_obc,
            cutoff_sc=data.cutoff_sc,
            cutoff_st=data.cutoff_st,
            cutoff_ews=data.cutoff_ews,
            is_mandatory=data.is_mandatory,
        )
        self.db.add(section)
        await self.db.flush()
        self._audit(actor, AuditAction.CREATE, "ExaminationSection", str(section.id))
        return section

    async def list_sections(self, exam_id: int) -> List[ExaminationSection]:
        result = await self.db.execute(
            select(ExaminationSection)
            .where(ExaminationSection.examination_id == exam_id)
            .order_by(ExaminationSection.section_order)
        )
        return list(result.scalars().all())

    async def add_shift(self, exam_id: int, data: ShiftCreate, actor) -> Shift:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Examination not found")

        shift = Shift(
            examination_id=exam_id,
            shift_code=data.shift_code,
            name=data.name,
            shift_date=data.shift_date,
            shift_start_time=data.shift_start_time,
            shift_end_time=data.shift_end_time,
            answer_key_version=data.answer_key_version,
        )
        self.db.add(shift)
        await self.db.flush()
        self._audit(actor, AuditAction.CREATE, "Shift", str(shift.id))
        return shift

    async def list_shifts(self, exam_id: int) -> List[Shift]:
        result = await self.db.execute(
            select(Shift).where(Shift.examination_id == exam_id)
        )
        return list(result.scalars().all())

    def _audit(self, actor, action: AuditAction, entity_type: str, entity_id: str):
        log = AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self.db.add(log)
