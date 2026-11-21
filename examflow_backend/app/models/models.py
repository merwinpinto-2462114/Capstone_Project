"""
EXAMFLOW – SQLAlchemy ORM Models
All 20 required entities from the PS-072 specification.
Every model inherits TimestampMixin for created_at / updated_at.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime,
    Enum, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ================================================================== #
# Enumerations
# ================================================================== #

class RoleName(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    EXAM_ADMIN = "EXAM_ADMIN"
    EVALUATOR = "EVALUATOR"
    PROCTOR = "PROCTOR"
    CANDIDATE = "CANDIDATE"
    AUDITOR = "AUDITOR"


class CandidateCategory(str, enum.Enum):
    GEN = "GEN"
    OBC = "OBC"
    SC = "SC"
    ST = "ST"
    EWS = "EWS"


class ResponseStatus(str, enum.Enum):
    OPTION_SELECTED = "OPTION_SELECTED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    MARKED_FOR_REVIEW = "MARKED_FOR_REVIEW"


class QuestionType(str, enum.Enum):
    SINGLE_CORRECT = "SINGLE_CORRECT"
    MULTIPLE_CORRECT = "MULTIPLE_CORRECT"


class ChallengeDecision(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EvaluationStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class QualificationStatus(str, enum.Enum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"


class MeritListStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ReEvaluationStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EVALUATE = "EVALUATE"
    RE_EVALUATE = "RE_EVALUATE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"


class ProctoringEventSeverity(int, enum.Enum):
    LOW_1 = 1
    LOW_2 = 2
    LOW_3 = 3
    MEDIUM_4 = 4
    MEDIUM_5 = 5
    MEDIUM_6 = 6
    HIGH_7 = 7
    HIGH_8 = 8
    HIGH_9 = 9
    CRITICAL_10 = 10


# ================================================================== #
# Mixins
# ================================================================== #

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ================================================================== #
# 1. Role
# ================================================================== #

class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        Enum(RoleName, name="role_name_enum"), unique=True, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")


# ================================================================== #
# 2. User
# ================================================================== #

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    role: Mapped["Role"] = relationship("Role", back_populates="users")

    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="actor")
    re_evaluation_requests: Mapped[List["ReEvaluationRequest"]] = relationship(
        "ReEvaluationRequest", back_populates="initiated_by_user"
    )


# ================================================================== #
# 3. Examination
# ================================================================== #

class Examination(Base, TimestampMixin):
    __tablename__ = "examinations"
    __table_args__ = (
        UniqueConstraint("exam_code", name="uq_examination_code"),
        CheckConstraint("duration_minutes > 0", name="ck_exam_duration_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    exam_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    evaluation_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    normalisation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sections: Mapped[List["ExaminationSection"]] = relationship(
        "ExaminationSection", back_populates="examination", cascade="all, delete-orphan"
    )
    shifts: Mapped[List["Shift"]] = relationship(
        "Shift", back_populates="examination", cascade="all, delete-orphan"
    )
    candidates: Mapped[List["Candidate"]] = relationship(
        "Candidate", back_populates="examination"
    )
    merit_lists: Mapped[List["MeritList"]] = relationship(
        "MeritList", back_populates="examination"
    )


# ================================================================== #
# 4. ExaminationSection
# ================================================================== #

class ExaminationSection(Base, TimestampMixin):
    __tablename__ = "examination_sections"
    __table_args__ = (
        UniqueConstraint("examination_id", "section_code", name="uq_exam_section_code"),
        CheckConstraint("total_questions > 0", name="ck_section_questions_positive"),
        CheckConstraint("max_marks > 0", name="ck_section_max_marks_positive"),
        CheckConstraint("marks_per_correct > 0", name="ck_section_correct_marks_positive"),
        CheckConstraint("negative_marks_per_wrong >= 0", name="ck_section_neg_marks_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    section_code: Mapped[str] = mapped_column(String(50), nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    max_marks: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    marks_per_correct: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    negative_marks_per_wrong: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    # Cut-off per category stored as separate columns for auditability
    cutoff_gen: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    cutoff_obc: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    cutoff_sc: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    cutoff_st: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    cutoff_ews: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    examination: Mapped["Examination"] = relationship("Examination", back_populates="sections")
    answer_keys: Mapped[List["AnswerKey"]] = relationship(
        "AnswerKey", back_populates="section"
    )
    section_results: Mapped[List["SectionResult"]] = relationship(
        "SectionResult", back_populates="section"
    )

    __table_args__ = (
        UniqueConstraint("examination_id", "section_code", name="uq_exam_section_code"),
        CheckConstraint("total_questions > 0", name="ck_section_questions_positive"),
        CheckConstraint("max_marks > 0", name="ck_section_max_marks_positive"),
        CheckConstraint("marks_per_correct > 0", name="ck_section_correct_marks_positive"),
        CheckConstraint("negative_marks_per_wrong >= 0", name="ck_section_neg_marks_non_negative"),
        Index("ix_exam_section_exam_id", "examination_id"),
    )


# ================================================================== #
# 5. Shift
# ================================================================== #

class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("examination_id", "shift_code", name="uq_shift_code_per_exam"),
        CheckConstraint("shift_end_time > shift_start_time", name="ck_shift_end_after_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id"), nullable=False)
    shift_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shift_end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answer_key_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
    is_pooled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pool_shift_ids: Mapped[Optional[str]] = mapped_column(
        Text, comment="Comma-separated shift IDs pooled with this shift for normalisation"
    )

    examination: Mapped["Examination"] = relationship("Examination", back_populates="shifts")
    candidates: Mapped[List["Candidate"]] = relationship("Candidate", back_populates="shift")
    shift_statistics: Mapped[Optional["ShiftStatistics"]] = relationship(
        "ShiftStatistics", back_populates="shift", uselist=False
    )


# ================================================================== #
# 6. Candidate
# ================================================================== #

class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("roll_number", "examination_id", name="uq_roll_exam"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roll_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(
        Enum(CandidateCategory, name="candidate_category_enum"), nullable=False
    )
    is_pwd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(254))
    phone: Mapped[Optional[str]] = mapped_column(String(20))

    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id"), nullable=False)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    examination: Mapped["Examination"] = relationship("Examination", back_populates="candidates")
    shift: Mapped["Shift"] = relationship("Shift", back_populates="candidates")
    responses: Mapped[List["CandidateResponse"]] = relationship(
        "CandidateResponse", back_populates="candidate", cascade="all, delete-orphan"
    )
    evaluation_results: Mapped[List["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="candidate"
    )
    proctoring_events: Mapped[List["ProctoringEvent"]] = relationship(
        "ProctoringEvent", back_populates="candidate"
    )
    qualification_decisions: Mapped[List["QualificationDecision"]] = relationship(
        "QualificationDecision", back_populates="candidate"
    )
    re_evaluation_requests: Mapped[List["ReEvaluationRequest"]] = relationship(
        "ReEvaluationRequest", back_populates="candidate"
    )
    merit_list_entries: Mapped[List["MeritListEntry"]] = relationship(
        "MeritListEntry", back_populates="candidate"
    )


# ================================================================== #
# 7. CandidateResponse
# ================================================================== #

class CandidateResponse(Base, TimestampMixin):
    __tablename__ = "candidate_responses"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "section_id", "question_number",
            name="uq_candidate_question_response"
        ),
        Index("ix_candidate_response_candidate_section", "candidate_id", "section_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("examination_sections.id"), nullable=False
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_option: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="Comma-separated for multiple-correct; NULL if not attempted",
    )
    status: Mapped[str] = mapped_column(
        Enum(ResponseStatus, name="response_status_enum"), nullable=False
    )
    response_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # After is_late override: effective status used in scoring
    effective_status: Mapped[str] = mapped_column(
        Enum(ResponseStatus, name="response_status_enum"),
        nullable=False,
    )

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="responses")
    section: Mapped["ExaminationSection"] = relationship("ExaminationSection")


# ================================================================== #
# 8. AnswerKey
# ================================================================== #

class AnswerKey(Base, TimestampMixin):
    __tablename__ = "answer_keys"
    __table_args__ = (
        UniqueConstraint(
            "section_id", "question_number", "version_id",
            name="uq_answer_key_question_version"
        ),
        Index("ix_answer_key_section_version", "section_id", "version_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("examination_sections.id"), nullable=False
    )
    version_id: Mapped[int] = mapped_column(
        ForeignKey("answer_key_versions.id"), nullable=False
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(
        Enum(QuestionType, name="question_type_enum"), nullable=False
    )
    correct_options: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Comma-separated correct option identifiers"
    )
    is_dropped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dropped_marks_rule: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="FULL_MARKS | ZERO | NO_CHANGE – applied when question is dropped"
    )

    section: Mapped["ExaminationSection"] = relationship("ExaminationSection", back_populates="answer_keys")
    version: Mapped["AnswerKeyVersion"] = relationship("AnswerKeyVersion", back_populates="answer_keys")


# ================================================================== #
# 9. AnswerKeyVersion
# ================================================================== #

class AnswerKeyVersion(Base, TimestampMixin):
    __tablename__ = "answer_key_versions"
    __table_args__ = (
        UniqueConstraint("examination_id", "version_tag", name="uq_answer_key_version_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id"), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    answer_keys: Mapped[List["AnswerKey"]] = relationship(
        "AnswerKey", back_populates="version"
    )
    challenges: Mapped[List["QuestionChallenge"]] = relationship(
        "QuestionChallenge", back_populates="answer_key_version"
    )


# ================================================================== #
# 10. QuestionChallenge
# ================================================================== #

class QuestionChallenge(Base, TimestampMixin):
    __tablename__ = "question_challenges"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "section_id", "question_number", "answer_key_version_id",
            name="uq_challenge_per_candidate_question_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("examination_sections.id"), nullable=False
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_key_version_id: Mapped[int] = mapped_column(
        ForeignKey("answer_key_versions.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_answer: Mapped[Optional[str]] = mapped_column(String(500))
    decision: Mapped[str] = mapped_column(
        Enum(ChallengeDecision, name="challenge_decision_enum"),
        default=ChallengeDecision.PENDING,
        nullable=False,
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    candidate: Mapped["Candidate"] = relationship("Candidate")
    answer_key_version: Mapped["AnswerKeyVersion"] = relationship(
        "AnswerKeyVersion", back_populates="challenges"
    )


# ================================================================== #
# 11. DroppedQuestion
# ================================================================== #

class DroppedQuestion(Base, TimestampMixin):
    __tablename__ = "dropped_questions"
    __table_args__ = (
        UniqueConstraint(
            "section_id", "question_number", "answer_key_version_id",
            name="uq_dropped_question_per_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("examination_sections.id"), nullable=False
    )
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_key_version_id: Mapped[int] = mapped_column(
        ForeignKey("answer_key_versions.id"), nullable=False
    )
    marks_rule: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="FULL_MARKS | ZERO | NO_CHANGE – consistently applied to all candidates"
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    dropped_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


# ================================================================== #
# 12. ProctoringEvent
# ================================================================== #

class ProctoringEvent(Base, TimestampMixin):
    __tablename__ = "proctoring_events"
    __table_args__ = (
        CheckConstraint("severity >= 1 AND severity <= 10", name="ck_severity_range"),
        Index("ix_proctoring_candidate_id", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_confirmed_malpractice: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    confirmed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="proctoring_events")


# ================================================================== #
# 13. EvaluationResult
# ================================================================== #

class EvaluationResult(Base, TimestampMixin):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_eval_result_candidate_version"),
        Index("ix_eval_result_candidate_id", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    answer_key_version_id: Mapped[int] = mapped_column(
        ForeignKey("answer_key_versions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        Enum(EvaluationStatus, name="evaluation_status_enum"), nullable=False
    )

    # Raw score (2 dp display, full precision stored)
    raw_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    total_correct: Mapped[int] = mapped_column(Integer, default=0)
    total_wrong: Mapped[int] = mapped_column(Integer, default=0)
    total_not_attempted: Mapped[int] = mapped_column(Integer, default=0)
    total_marked_review_no_option: Mapped[int] = mapped_column(Integer, default=0)

    # Deductions
    negative_marks_deducted: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), default=Decimal("0")
    )
    proctoring_penalty_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )
    proctoring_penalty_marks: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), default=Decimal("0")
    )
    score_after_proctoring: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))

    # Normalisation (5 dp display, full precision stored)
    normalised_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))
    is_normalised: Mapped[bool] = mapped_column(Boolean, default=False)

    attempt_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    candidate: Mapped["Candidate"] = relationship(
        "Candidate", back_populates="evaluation_results"
    )
    section_results: Mapped[List["SectionResult"]] = relationship(
        "SectionResult", back_populates="evaluation_result", cascade="all, delete-orphan"
    )
    qualification_decisions: Mapped[List["QualificationDecision"]] = relationship(
        "QualificationDecision", back_populates="evaluation_result"
    )


# ================================================================== #
# 14. SectionResult
# ================================================================== #

class SectionResult(Base, TimestampMixin):
    __tablename__ = "section_results"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_result_id", "section_id", name="uq_section_result_eval_section"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluation_result_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_results.id"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        ForeignKey("examination_sections.id"), nullable=False
    )
    raw_section_score: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    not_attempted_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_marks: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), default=Decimal("0")
    )
    is_section_qualified: Mapped[Optional[bool]] = mapped_column(Boolean)
    cutoff_applied: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)

    evaluation_result: Mapped["EvaluationResult"] = relationship(
        "EvaluationResult", back_populates="section_results"
    )
    section: Mapped["ExaminationSection"] = relationship(
        "ExaminationSection", back_populates="section_results"
    )


# ================================================================== #
# 15. ShiftStatistics
# ================================================================== #

class ShiftStatistics(Base, TimestampMixin):
    __tablename__ = "shift_statistics"
    __table_args__ = (
        UniqueConstraint("shift_id", name="uq_shift_statistics_shift_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_raw_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))
    std_dev_raw_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))
    # Pooled statistics (if shift is pooled)
    pooled_mean: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))
    pooled_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))
    top_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 6))
    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    shift: Mapped["Shift"] = relationship("Shift", back_populates="shift_statistics")


# ================================================================== #
# 16. QualificationDecision
# ================================================================== #

class QualificationDecision(Base, TimestampMixin):
    __tablename__ = "qualification_decisions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "evaluation_result_id", name="uq_qual_decision_candidate_eval"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    evaluation_result_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_results.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(QualificationStatus, name="qualification_status_enum"), nullable=False
    )
    # Detailed failure/disqualification reasons (never just a boolean)
    reasons: Mapped[Optional[str]] = mapped_column(
        Text, comment="JSON-serialised list of QualificationFailureReason objects"
    )
    overall_cutoff_applied: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    category_relaxation_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    effective_cutoff: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    candidate: Mapped["Candidate"] = relationship(
        "Candidate", back_populates="qualification_decisions"
    )
    evaluation_result: Mapped["EvaluationResult"] = relationship(
        "EvaluationResult", back_populates="qualification_decisions"
    )


# ================================================================== #
# 17. MeritList
# ================================================================== #

class MeritList(Base, TimestampMixin):
    __tablename__ = "merit_lists"
    __table_args__ = (
        UniqueConstraint("examination_id", "version", name="uq_merit_list_exam_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("examinations.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        Enum(MeritListStatus, name="merit_list_status_enum"),
        default=MeritListStatus.DRAFT,
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    examination: Mapped["Examination"] = relationship(
        "Examination", back_populates="merit_lists"
    )
    entries: Mapped[List["MeritListEntry"]] = relationship(
        "MeritListEntry", back_populates="merit_list", cascade="all, delete-orphan"
    )


# ================================================================== #
# 18. MeritListEntry
# ================================================================== #

class MeritListEntry(Base, TimestampMixin):
    __tablename__ = "merit_list_entries"
    __table_args__ = (
        UniqueConstraint(
            "merit_list_id", "candidate_id", name="uq_merit_entry_list_candidate"
        ),
        Index("ix_merit_list_entry_rank", "merit_list_id", "overall_rank"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merit_list_id: Mapped[int] = mapped_column(ForeignKey("merit_lists.id"), nullable=False)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    evaluation_result_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_results.id"), nullable=False
    )

    overall_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    category_rank: Mapped[Optional[int]] = mapped_column(Integer)
    final_score: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)

    # Tie-breaker audit columns
    tie_breaker_applied: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Which tie-breaker resolved ordering: SECTION_SCORE|WRONG_COUNT|DOB|NAME|UNRESOLVED"
    )
    is_allocated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allocation_category: Mapped[Optional[str]] = mapped_column(
        String(10),
        comment="Category under which candidate is allocated (may differ from candidate category for GEN threshold)"
    )

    merit_list: Mapped["MeritList"] = relationship("MeritList", back_populates="entries")
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="merit_list_entries")


# ================================================================== #
# 19. ReEvaluationRequest
# ================================================================== #

class ReEvaluationRequest(Base, TimestampMixin):
    __tablename__ = "re_evaluation_requests"
    __table_args__ = (
        # Enforce one re-evaluation per candidate at DB level
        CheckConstraint(
            "request_count <= 1",
            name="ck_re_eval_max_one_per_candidate"
        ),
        UniqueConstraint("candidate_id", name="uq_re_eval_one_per_candidate"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    initiated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    previous_result_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_results.id"), nullable=False
    )
    new_result_id: Mapped[Optional[int]] = mapped_column(ForeignKey("evaluation_results.id"))
    answer_key_version_id: Mapped[int] = mapped_column(
        ForeignKey("answer_key_versions.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ReEvaluationStatus, name="re_evaluation_status_enum"),
        default=ReEvaluationStatus.REQUESTED,
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    candidate: Mapped["Candidate"] = relationship(
        "Candidate", back_populates="re_evaluation_requests"
    )
    initiated_by_user: Mapped["User"] = relationship(
        "User", back_populates="re_evaluation_requests"
    )


# ================================================================== #
# 20. AuditLog
# ================================================================== #

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_log_actor_id", "actor_id"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(
        Enum(AuditAction, name="audit_action_enum"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # JSON snapshot of old and new values
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    actor: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
