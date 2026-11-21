"""
EXAMFLOW – Runnable Demo Dataset
Seeds the database with sample data for demonstration and testing.
Run after migrations:
    python scripts/seed_demo.py
"""
import asyncio
import os
from datetime import date, datetime, timezone
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://examflow:examflow_dev_password@localhost:5432/examflow_db")
os.environ.setdefault("SECRET_KEY", "demo-only-secret-key-32-chars-min!")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.models.models import (
    Role, User, Examination, ExaminationSection, Shift,
    Candidate, CandidateResponse, AnswerKeyVersion, AnswerKey,
    ResponseStatus, RoleName, CandidateCategory, QuestionType,
)
from app.core.security import get_password_hash

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with SessionLocal() as db:
        # Roles
        roles = {}
        for rname in RoleName:
            role = Role(name=rname, description=f"{rname.value} role")
            db.add(role)
            await db.flush()
            roles[rname.value] = role

        # Admin user
        admin = User(
            username="admin",
            email="admin@examflow.local",
            full_name="System Administrator",
            hashed_password=get_password_hash("Admin@12345"),
            is_active=True,
            role_id=roles["SUPER_ADMIN"].id,
        )
        db.add(admin)
        await db.flush()

        # Examination
        exam = Examination(
            name="EXAMFLOW Demo Examination 2026",
            exam_code="DEMO2026",
            description="PS-072 demo with 2 sections, 3 shifts",
            duration_minutes=180,
            normalisation_enabled=True,
        )
        db.add(exam)
        await db.flush()

        # Sections
        sec1 = ExaminationSection(
            examination_id=exam.id,
            name="General Intelligence", section_code="GI",
            section_order=1, total_questions=50,
            max_marks=Decimal("50"), marks_per_correct=Decimal("1"),
            negative_marks_per_wrong=Decimal("0.25"),
            cutoff_gen=Decimal("20"), cutoff_obc=Decimal("17.5"),
            cutoff_sc=Decimal("15"), cutoff_st=Decimal("15"),
            cutoff_ews=Decimal("17.5"), is_mandatory=True,
        )
        sec2 = ExaminationSection(
            examination_id=exam.id,
            name="Quantitative Aptitude", section_code="QA",
            section_order=2, total_questions=50,
            max_marks=Decimal("50"), marks_per_correct=Decimal("1"),
            negative_marks_per_wrong=Decimal("0.25"),
            cutoff_gen=Decimal("20"), cutoff_obc=Decimal("17.5"),
            cutoff_sc=Decimal("15"), cutoff_st=Decimal("15"),
            cutoff_ews=Decimal("17.5"), is_mandatory=True,
        )
        db.add_all([sec1, sec2])
        await db.flush()

        # Shifts (3 shifts to demo normalisation)
        shifts = []
        for i, (code, name, n_cands) in enumerate([
            ("SHIFT_A", "Morning Shift", 120),
            ("SHIFT_B", "Afternoon Shift", 95),   # <100 → will be pooled
            ("SHIFT_C", "Evening Shift", 110),
        ]):
            shift = Shift(
                examination_id=exam.id,
                shift_code=code,
                name=name,
                shift_date=date(2026, 12, 1),
                shift_start_time=datetime(2026, 12, 1, 9 + i * 3, 0, tzinfo=timezone.utc),
                shift_end_time=datetime(2026, 12, 1, 12 + i * 3, 0, tzinfo=timezone.utc),
                answer_key_version="v1",
            )
            db.add(shift)
            await db.flush()
            shifts.append((shift, n_cands))

        # Answer key version
        akv = AnswerKeyVersion(
            examination_id=exam.id,
            version_tag="v1",
            description="Official answer key",
            is_official=True,
            published_at=datetime.now(timezone.utc),
        )
        db.add(akv)
        await db.flush()

        # Answer keys (Q1–Q50 for each section; all correct = "A")
        for section in [sec1, sec2]:
            for q in range(1, 51):
                q_type = QuestionType.MULTIPLE_CORRECT if q == 10 else QuestionType.SINGLE_CORRECT
                correct = "A,C" if q == 10 else "A"
                db.add(AnswerKey(
                    section_id=section.id,
                    version_id=akv.id,
                    question_number=q,
                    question_type=q_type,
                    correct_options=correct,
                    is_dropped=(q == 25),  # Q25 dropped
                    dropped_marks_rule="FULL_MARKS" if q == 25 else None,
                ))

        # Candidates
        categories = [
            CandidateCategory.GEN, CandidateCategory.OBC,
            CandidateCategory.SC, CandidateCategory.ST, CandidateCategory.EWS
        ]
        roll = 1
        for shift, n_cands in shifts:
            for i in range(n_cands):
                cat = categories[i % len(categories)]
                cand = Candidate(
                    roll_number=f"R{roll:06d}",
                    full_name=f"Candidate {roll}",
                    date_of_birth=date(1995, (i % 12) + 1, (i % 28) + 1),
                    category=cat,
                    is_pwd=(i % 20 == 0),
                    examination_id=exam.id,
                    shift_id=shift.id,
                )
                db.add(cand)
                roll += 1

        await db.commit()
        print(f"✓ Demo seed complete. {roll - 1} candidates seeded.")
        print(f"  Admin login: admin / Admin@12345")
        print(f"  Exam code: DEMO2026")
        print(f"  Sections: GI, QA")
        print(f"  Shifts: SHIFT_A (120), SHIFT_B (95→pooled), SHIFT_C (110)")


if __name__ == "__main__":
    asyncio.run(seed())
