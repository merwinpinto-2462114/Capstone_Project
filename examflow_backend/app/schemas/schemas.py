"""
EXAMFLOW – Pydantic Schemas (request / response models)
Covers all 20 entities with strict validation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.models import (
    CandidateCategory, ChallengeDecision, EvaluationStatus,
    MeritListStatus, QualificationStatus, QuestionType,
    ReEvaluationStatus, ResponseStatus, RoleName,
)


# ================================================================== #
# Base helpers
# ================================================================== #

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ================================================================== #
# Auth
# ================================================================== #

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


# ================================================================== #
# Role
# ================================================================== #

class RoleOut(OrmBase):
    id: int
    name: RoleName
    description: Optional[str]


# ================================================================== #
# User
# ================================================================== #

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=300)
    password: str = Field(..., min_length=8, max_length=128)
    role_id: int


class UserOut(OrmBase):
    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    role: RoleOut
    created_at: datetime


# ================================================================== #
# Examination
# ================================================================== #

class ExaminationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    exam_code: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Z0-9_\-]+$")
    description: Optional[str] = None
    duration_minutes: int = Field(..., ge=1)
    normalisation_enabled: bool = False


class ExaminationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=1)
    normalisation_enabled: Optional[bool] = None


class ExaminationOut(OrmBase):
    id: int
    name: str
    exam_code: str
    description: Optional[str]
    duration_minutes: int
    is_active: bool
    evaluation_locked: bool
    normalisation_enabled: bool
    created_at: datetime


# ================================================================== #
# ExaminationSection
# ================================================================== #

class ExaminationSectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    section_code: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Z0-9_\-]+$")
    section_order: int = Field(..., ge=1)
    total_questions: int = Field(..., ge=1)
    max_marks: Decimal = Field(..., gt=0)
    marks_per_correct: Decimal = Field(..., gt=0)
    negative_marks_per_wrong: Decimal = Field(Decimal("0"), ge=0)
    cutoff_gen: Optional[Decimal] = Field(None, ge=0)
    cutoff_obc: Optional[Decimal] = Field(None, ge=0)
    cutoff_sc: Optional[Decimal] = Field(None, ge=0)
    cutoff_st: Optional[Decimal] = Field(None, ge=0)
    cutoff_ews: Optional[Decimal] = Field(None, ge=0)
    is_mandatory: bool = True


class ExaminationSectionOut(OrmBase):
    id: int
    examination_id: int
    name: str
    section_code: str
    section_order: int
    total_questions: int
    max_marks: Decimal
    marks_per_correct: Decimal
    negative_marks_per_wrong: Decimal
    cutoff_gen: Optional[Decimal]
    cutoff_obc: Optional[Decimal]
    cutoff_sc: Optional[Decimal]
    cutoff_st: Optional[Decimal]
    cutoff_ews: Optional[Decimal]
    is_mandatory: bool


# ================================================================== #
# Shift
# ================================================================== #

class ShiftCreate(BaseModel):
    shift_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    shift_date: date
    shift_start_time: datetime
    shift_end_time: datetime
    answer_key_version: str = Field("v1", max_length=50)

    @field_validator("shift_end_time")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("shift_start_time")
        if start and v <= start:
            raise ValueError("shift_end_time must be after shift_start_time")
        return v


class ShiftOut(OrmBase):
    id: int
    examination_id: int
    shift_code: str
    name: str
    shift_date: date
    shift_start_time: datetime
    shift_end_time: datetime
    answer_key_version: str
    is_pooled: bool


# ================================================================== #
# Candidate
# ================================================================== #

class CandidateCreate(BaseModel):
    roll_number: str = Field(..., min_length=1, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=300)
    date_of_birth: date
    category: CandidateCategory
    is_pwd: bool = False
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    examination_id: int
    shift_id: int


class CandidateBulkCreate(BaseModel):
    candidates: List[CandidateCreate] = Field(..., min_length=1)


class CandidateOut(OrmBase):
    id: int
    roll_number: str
    full_name: str
    date_of_birth: date
    category: CandidateCategory
    is_pwd: bool
    email: Optional[str]
    phone: Optional[str]
    examination_id: int
    shift_id: int
    created_at: datetime


# ================================================================== #
# CandidateResponse
# ================================================================== #

class ResponseItem(BaseModel):
    section_id: int
    question_number: int = Field(..., ge=1)
    selected_option: Optional[str] = None
    status: ResponseStatus
    response_timestamp: Optional[datetime] = None
    is_late: bool = False

    @field_validator("selected_option")
    @classmethod
    def option_required_if_selected(cls, v: Optional[str], info) -> Optional[str]:
        status = info.data.get("status")
        if status == ResponseStatus.OPTION_SELECTED and not v:
            raise ValueError("selected_option must be provided when status is OPTION_SELECTED")
        # MARKED_FOR_REVIEW without an option → NOT_ATTEMPTED in scoring (Rule 4)
        return v


class ResponseIngest(BaseModel):
    candidate_id: int
    responses: List[ResponseItem] = Field(..., min_length=1)


class ResponseOut(OrmBase):
    id: int
    candidate_id: int
    section_id: int
    question_number: int
    selected_option: Optional[str]
    status: ResponseStatus
    effective_status: ResponseStatus
    is_late: bool
    response_timestamp: Optional[datetime]


# ================================================================== #
# AnswerKey
# ================================================================== #

class AnswerKeyItem(BaseModel):
    section_id: int
    question_number: int = Field(..., ge=1)
    question_type: QuestionType
    correct_options: str = Field(..., min_length=1)
    is_dropped: bool = False
    dropped_marks_rule: Optional[str] = Field(
        None, pattern=r"^(FULL_MARKS|ZERO|NO_CHANGE)$"
    )


class AnswerKeyVersionCreate(BaseModel):
    version_tag: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    is_official: bool = False
    keys: List[AnswerKeyItem] = Field(..., min_length=1)


class AnswerKeyVersionOut(OrmBase):
    id: int
    examination_id: int
    version_tag: str
    description: Optional[str]
    is_official: bool
    published_at: Optional[datetime]
    created_at: datetime


# ================================================================== #
# QuestionChallenge
# ================================================================== #

class ChallengeCreate(BaseModel):
    candidate_id: int
    section_id: int
    question_number: int = Field(..., ge=1)
    answer_key_version_id: int
    reason: str = Field(..., min_length=10)
    proposed_answer: Optional[str] = None


class ChallengeDecisionUpdate(BaseModel):
    decision: ChallengeDecision
    decision_reason: str = Field(..., min_length=5)


class ChallengeOut(OrmBase):
    id: int
    candidate_id: int
    section_id: int
    question_number: int
    answer_key_version_id: int
    reason: str
    proposed_answer: Optional[str]
    decision: ChallengeDecision
    decision_reason: Optional[str]
    decided_at: Optional[datetime]


# ================================================================== #
# DroppedQuestion
# ================================================================== #

class DroppedQuestionCreate(BaseModel):
    section_id: int
    question_number: int = Field(..., ge=1)
    answer_key_version_id: int
    marks_rule: str = Field(..., pattern=r"^(FULL_MARKS|ZERO|NO_CHANGE)$")
    reason: str = Field(..., min_length=10)


class DroppedQuestionOut(OrmBase):
    id: int
    section_id: int
    question_number: int
    answer_key_version_id: int
    marks_rule: str
    reason: str
    created_at: datetime


# ================================================================== #
# ProctoringEvent
# ================================================================== #

class ProctoringEventCreate(BaseModel):
    candidate_id: int
    event_type: str = Field(..., min_length=1, max_length=100)
    severity: int = Field(..., ge=1, le=10)
    description: Optional[str] = None
    is_confirmed_malpractice: bool = False
    event_timestamp: datetime


class ProctoringEventOut(OrmBase):
    id: int
    candidate_id: int
    event_type: str
    severity: int
    description: Optional[str]
    is_confirmed_malpractice: bool
    event_timestamp: datetime
    confirmed_at: Optional[datetime]


# ================================================================== #
# EvaluationResult
# ================================================================== #

class EvaluateRequest(BaseModel):
    examination_id: int
    answer_key_version_id: int
    candidate_ids: Optional[List[int]] = None  # None = evaluate all


class SectionResultOut(OrmBase):
    id: int
    section_id: int
    raw_section_score: Decimal
    correct_count: int
    wrong_count: int
    not_attempted_count: int
    negative_marks: Decimal
    is_section_qualified: Optional[bool]
    cutoff_applied: Optional[Decimal]
    failure_reason: Optional[str]


class EvaluationResultOut(OrmBase):
    id: int
    candidate_id: int
    version: int
    status: EvaluationStatus
    raw_score: Optional[Decimal]
    total_correct: int
    total_wrong: int
    total_not_attempted: int
    negative_marks_deducted: Decimal
    proctoring_penalty_percentage: Decimal
    proctoring_penalty_marks: Decimal
    score_after_proctoring: Optional[Decimal]
    normalised_score: Optional[Decimal]
    is_normalised: bool
    attempt_percentage: Optional[Decimal]
    evaluated_at: Optional[datetime]
    section_results: List[SectionResultOut] = []


# ================================================================== #
# Qualification
# ================================================================== #

class QualificationDecisionOut(OrmBase):
    id: int
    candidate_id: int
    evaluation_result_id: int
    status: QualificationStatus
    reasons: Optional[str]
    overall_cutoff_applied: Optional[Decimal]
    category_relaxation_percentage: Optional[Decimal]
    effective_cutoff: Optional[Decimal]
    decided_at: Optional[datetime]


# ================================================================== #
# MeritList
# ================================================================== #

class GenerateMeritListRequest(BaseModel):
    examination_id: int
    description: Optional[str] = None


class MeritListEntryOut(OrmBase):
    id: int
    candidate_id: int
    overall_rank: int
    category_rank: Optional[int]
    final_score: Decimal
    tie_breaker_applied: Optional[str]
    is_allocated: bool
    allocation_category: Optional[str]


class MeritListOut(OrmBase):
    id: int
    examination_id: int
    version: int
    status: MeritListStatus
    description: Optional[str]
    generated_at: Optional[datetime]
    entries: List[MeritListEntryOut] = []


# ================================================================== #
# Re-Evaluation
# ================================================================== #

class ReEvaluationCreate(BaseModel):
    candidate_id: int
    answer_key_version_id: int
    reason: str = Field(..., min_length=10)


class ReEvaluationOut(OrmBase):
    id: int
    candidate_id: int
    initiated_by_user_id: int
    previous_result_id: int
    new_result_id: Optional[int]
    answer_key_version_id: int
    reason: str
    status: ReEvaluationStatus
    request_count: int
    completed_at: Optional[datetime]
    created_at: datetime


# ================================================================== #
# AuditLog
# ================================================================== #

class AuditLogOut(OrmBase):
    id: int
    actor_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[str]
    description: Optional[str]
    created_at: datetime


# ================================================================== #
# Generic paginated response
# ================================================================== #

class Paginated(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]


# ================================================================== #
# API error
# ================================================================== #

class APIError(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
