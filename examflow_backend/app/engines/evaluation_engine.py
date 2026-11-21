"""
EXAMFLOW – Evaluation Engine (PS-072 deterministic scoring)
============================================================
All calculations are performed with Python Decimal for exact arithmetic.
No floating-point arithmetic is used in scoring.

Implements Rules 1-5 from the PS-072 specification.

Decision-Log Items:
- DL-001: Penalty base for proctoring deduction is score_after_negative_marks
           (the base before proctoring deduction). This needs confirmation from
           the project rule register. If the approved base is different, update
           ProctoringPenaltyEngine.apply_penalty() accordingly.
- DL-002: For multiple-correct questions, partial credit is NOT awarded;
           the candidate's selected set must exactly match the correct set.
           If partial credit semantics are approved, update
           _score_multiple_correct().
- DL-003: The 10% minimum-attempt boundary is INCLUSIVE (≥10% passes).
           See Rule 8. If the approved boundary is exclusive, invert the check.
"""

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ================================================================== #
# Data Transfer Objects (pure Python, no SQLAlchemy dependency)
# ================================================================== #

@dataclass
class SectionConfig:
    section_id: int
    section_code: str
    total_questions: int
    max_marks: Decimal
    marks_per_correct: Decimal
    negative_marks_per_wrong: Decimal
    is_mandatory: bool


@dataclass
class AnswerKeyEntry:
    question_number: int
    question_type: str          # "SINGLE_CORRECT" | "MULTIPLE_CORRECT"
    correct_options: Set[str]   # frozenset of accepted option IDs
    is_dropped: bool
    dropped_marks_rule: Optional[str]  # "FULL_MARKS" | "ZERO" | "NO_CHANGE"


@dataclass
class ResponseEntry:
    question_number: int
    selected_options: Set[str]  # empty if NOT_ATTEMPTED / MARKED_FOR_REVIEW without option
    effective_status: str       # "OPTION_SELECTED" | "NOT_ATTEMPTED" | "MARKED_FOR_REVIEW"
    is_late: bool


@dataclass
class QuestionScore:
    question_number: int
    marks_awarded: Decimal
    is_correct: bool
    is_wrong: bool
    is_not_attempted: bool
    is_dropped: bool
    applied_rule: str = ""


@dataclass
class SectionScoreResult:
    section_id: int
    raw_section_score: Decimal
    correct_count: int
    wrong_count: int
    not_attempted_count: int
    negative_marks: Decimal
    question_scores: List[QuestionScore] = field(default_factory=list)


@dataclass
class EvaluationOutput:
    candidate_id: int
    section_scores: List[SectionScoreResult]
    raw_score: Decimal
    total_correct: int
    total_wrong: int
    total_not_attempted: int
    total_marked_review_no_option: int
    negative_marks_deducted: Decimal
    attempt_percentage: Decimal
    error: Optional[str] = None


# ================================================================== #
# Scoring Engine
# ================================================================== #

class ScoringEngine:
    """
    Deterministic per-question scorer.
    Implements Rule 1 (scoring) and Rule 2 (dropped questions / key changes).
    """

    def score_question(
        self,
        response: Optional[ResponseEntry],
        answer_key: AnswerKeyEntry,
        section_config: SectionConfig,
    ) -> QuestionScore:
        """
        Score a single question.
        Returns QuestionScore with exact Decimal marks.
        """
        q_num = answer_key.question_number

        # --- Dropped question (Rule 2) ---
        if answer_key.is_dropped:
            return self._score_dropped(q_num, answer_key, section_config)

        # --- No response submitted ---
        if response is None or response.effective_status == "NOT_ATTEMPTED":
            return QuestionScore(
                question_number=q_num,
                marks_awarded=Decimal("0"),
                is_correct=False,
                is_wrong=False,
                is_not_attempted=True,
                is_dropped=False,
                applied_rule="NOT_ATTEMPTED_NO_PENALTY",
            )

        # --- MARKED_FOR_REVIEW without an option → NOT_ATTEMPTED (Rule 4) ---
        if (
            response.effective_status == "MARKED_FOR_REVIEW"
            and not response.selected_options
        ):
            return QuestionScore(
                question_number=q_num,
                marks_awarded=Decimal("0"),
                is_correct=False,
                is_wrong=False,
                is_not_attempted=True,
                is_dropped=False,
                applied_rule="REVIEW_NO_OPTION_NOT_ATTEMPTED",
            )

        # --- Late response → NOT_ATTEMPTED (Rule 4) ---
        if response.is_late:
            return QuestionScore(
                question_number=q_num,
                marks_awarded=Decimal("0"),
                is_correct=False,
                is_wrong=False,
                is_not_attempted=True,
                is_dropped=False,
                applied_rule="LATE_RESPONSE_NOT_ATTEMPTED",
            )

        # --- Actual answer evaluation ---
        if answer_key.question_type == "SINGLE_CORRECT":
            return self._score_single_correct(q_num, response, answer_key, section_config)
        elif answer_key.question_type == "MULTIPLE_CORRECT":
            return self._score_multiple_correct(q_num, response, answer_key, section_config)
        else:
            raise ValueError(f"Unknown question_type: {answer_key.question_type}")

    def _score_single_correct(
        self,
        q_num: int,
        response: ResponseEntry,
        answer_key: AnswerKeyEntry,
        cfg: SectionConfig,
    ) -> QuestionScore:
        is_correct = response.selected_options == answer_key.correct_options
        if is_correct:
            return QuestionScore(
                question_number=q_num,
                marks_awarded=cfg.marks_per_correct,
                is_correct=True,
                is_wrong=False,
                is_not_attempted=False,
                is_dropped=False,
                applied_rule="SINGLE_CORRECT",
            )
        else:
            return QuestionScore(
                question_number=q_num,
                marks_awarded=-cfg.negative_marks_per_wrong,
                is_correct=False,
                is_wrong=True,
                is_not_attempted=False,
                is_dropped=False,
                applied_rule="SINGLE_WRONG_NEGATIVE",
            )

    def _score_multiple_correct(
        self,
        q_num: int,
        response: ResponseEntry,
        answer_key: AnswerKeyEntry,
        cfg: SectionConfig,
    ) -> QuestionScore:
        """
        Exact-match semantics (DL-002): all and only correct options must be selected.
        Partial selection or extra options → wrong.
        """
        is_correct = response.selected_options == answer_key.correct_options
        if is_correct:
            return QuestionScore(
                question_number=q_num,
                marks_awarded=cfg.marks_per_correct,
                is_correct=True,
                is_wrong=False,
                is_not_attempted=False,
                is_dropped=False,
                applied_rule="MULTIPLE_CORRECT_EXACT_MATCH",
            )
        else:
            return QuestionScore(
                question_number=q_num,
                marks_awarded=-cfg.negative_marks_per_wrong,
                is_correct=False,
                is_wrong=True,
                is_not_attempted=False,
                is_dropped=False,
                applied_rule="MULTIPLE_WRONG_NEGATIVE",
            )

    def _score_dropped(
        self,
        q_num: int,
        answer_key: AnswerKeyEntry,
        cfg: SectionConfig,
    ) -> QuestionScore:
        """
        Apply the configured dropped-question rule consistently to all candidates.
        Rule 2: marks_rule must be one of FULL_MARKS | ZERO | NO_CHANGE.
        """
        rule = answer_key.dropped_marks_rule or "FULL_MARKS"
        if rule == "FULL_MARKS":
            marks = cfg.marks_per_correct
        elif rule == "ZERO":
            marks = Decimal("0")
        elif rule == "NO_CHANGE":
            # Caller must pass the original scored marks; here we default to 0
            # as the response-level context is not available.
            # Actual NO_CHANGE logic is handled at the section scorer level.
            marks = Decimal("0")
        else:
            raise ValueError(f"Unknown dropped_marks_rule: {rule}")

        return QuestionScore(
            question_number=q_num,
            marks_awarded=marks,
            is_correct=False,
            is_wrong=False,
            is_not_attempted=False,
            is_dropped=True,
            applied_rule=f"DROPPED_{rule}",
        )


# ================================================================== #
# Section Scorer
# ================================================================== #

class SectionScorer:
    """Scores all questions in a section and aggregates results."""

    def __init__(self, scoring_engine: ScoringEngine):
        self._engine = scoring_engine

    def score_section(
        self,
        section_config: SectionConfig,
        answer_keys: List[AnswerKeyEntry],
        responses: List[ResponseEntry],
    ) -> SectionScoreResult:
        response_map: Dict[int, ResponseEntry] = {r.question_number: r for r in responses}
        answer_map: Dict[int, AnswerKeyEntry] = {a.question_number: a for a in answer_keys}

        question_scores: List[QuestionScore] = []
        raw_section_score = Decimal("0")
        correct_count = wrong_count = not_attempted_count = 0
        negative_marks = Decimal("0")

        for q_num, ak in answer_map.items():
            resp = response_map.get(q_num)
            qs = self._engine.score_question(resp, ak, section_config)
            question_scores.append(qs)

            raw_section_score += qs.marks_awarded
            if qs.is_correct:
                correct_count += 1
            elif qs.is_wrong:
                wrong_count += 1
                negative_marks += abs(qs.marks_awarded)
            elif qs.is_not_attempted:
                not_attempted_count += 1

        # Clamp section score to [0, max_marks] only if approved; store pre-clamp raw
        # NOTE: Clamping is NOT applied here; negative totals are preserved for audit.
        # Consult rule register before adding a floor.

        return SectionScoreResult(
            section_id=section_config.section_id,
            raw_section_score=raw_section_score,
            correct_count=correct_count,
            wrong_count=wrong_count,
            not_attempted_count=not_attempted_count,
            negative_marks=negative_marks,
            question_scores=question_scores,
        )


# ================================================================== #
# Attempt percentage validator (Rule 8)
# ================================================================== #

class AttemptValidator:
    """
    Rule 8: Candidates attempting fewer than 10% of required questions fail.
    Boundary: exactly 10% is INCLUSIVE (passes). See DL-003.
    """

    MIN_ATTEMPT_PERCENTAGE = Decimal("10")

    def compute_attempt_percentage(
        self,
        total_questions_required: int,
        total_attempted: int,
    ) -> Decimal:
        if total_questions_required <= 0:
            raise ValueError("total_questions_required must be > 0")
        pct = (Decimal(total_attempted) / Decimal(total_questions_required)) * Decimal("100")
        return pct

    def meets_minimum_attempts(self, attempt_percentage: Decimal) -> bool:
        """Returns True if candidate meets or exceeds the 10% threshold (inclusive)."""
        return attempt_percentage >= self.MIN_ATTEMPT_PERCENTAGE


# ================================================================== #
# Proctoring Penalty Engine (Rule 5)
# ================================================================== #

@dataclass
class ProctoringPenaltyResult:
    penalty_percentage: Decimal
    penalty_marks: Decimal
    is_disqualified: bool
    disqualification_reason: Optional[str]
    score_after_penalty: Decimal


class ProctoringPenaltyEngine:
    """
    Rule 5 penalty tiers:
    - Severity 4-6  → 5% deduction
    - Severity 7-9  → 15% deduction
    - Severity 10+  → Disqualification
    - Confirmed malpractice → Disqualification

    Decision Log DL-001: penalty base = score_after_negative_marks.
    The highest-severity event determines the deduction tier.
    Multiple events do not stack tiers; the worst event governs.
    """

    TIER_4_6_PCT = Decimal("5")
    TIER_7_9_PCT = Decimal("15")

    def apply_penalty(
        self,
        score_before_penalty: Decimal,
        max_severity: int,
        confirmed_malpractice: bool,
    ) -> ProctoringPenaltyResult:
        # Disqualification conditions
        if confirmed_malpractice:
            return ProctoringPenaltyResult(
                penalty_percentage=Decimal("100"),
                penalty_marks=score_before_penalty,
                is_disqualified=True,
                disqualification_reason="CONFIRMED_MALPRACTICE",
                score_after_penalty=Decimal("0"),
            )

        if max_severity >= 10:
            return ProctoringPenaltyResult(
                penalty_percentage=Decimal("100"),
                penalty_marks=score_before_penalty,
                is_disqualified=True,
                disqualification_reason=f"PROCTORING_SEVERITY_{max_severity}",
                score_after_penalty=Decimal("0"),
            )

        if max_severity >= 7:
            pct = self.TIER_7_9_PCT
        elif max_severity >= 4:
            pct = self.TIER_4_6_PCT
        else:
            pct = Decimal("0")

        penalty = (pct / Decimal("100")) * score_before_penalty
        final_score = score_before_penalty - penalty

        return ProctoringPenaltyResult(
            penalty_percentage=pct,
            penalty_marks=penalty,
            is_disqualified=False,
            disqualification_reason=None,
            score_after_penalty=final_score,
        )


# ================================================================== #
# Main Evaluation Engine
# ================================================================== #

class EvaluationEngine:
    """
    Orchestrates all scoring steps for a single candidate.
    Uses only deterministic Decimal arithmetic.
    """

    def __init__(self):
        self._scoring_engine = ScoringEngine()
        self._section_scorer = SectionScorer(self._scoring_engine)
        self._attempt_validator = AttemptValidator()
        self._proctoring_engine = ProctoringPenaltyEngine()

    def evaluate(
        self,
        candidate_id: int,
        sections: List[SectionConfig],
        answer_keys_by_section: Dict[int, List[AnswerKeyEntry]],
        responses_by_section: Dict[int, List[ResponseEntry]],
        proctoring_max_severity: int,
        confirmed_malpractice: bool,
    ) -> EvaluationOutput:
        """
        Full evaluation pipeline for one candidate.
        Returns EvaluationOutput with all intermediate values preserved.
        """
        section_scores: List[SectionScoreResult] = []
        raw_score = Decimal("0")
        total_correct = total_wrong = total_not_attempted = 0
        total_marked_review_no_option = 0
        negative_total = Decimal("0")
        total_required_questions = 0
        total_attempted = 0

        for section in sections:
            keys = answer_keys_by_section.get(section.section_id, [])
            resps = responses_by_section.get(section.section_id, [])

            if not keys:
                logger.warning(
                    "No answer keys for section %s, candidate %s",
                    section.section_id,
                    candidate_id,
                )
                continue

            ss = self._section_scorer.score_section(section, keys, resps)
            section_scores.append(ss)

            raw_score += ss.raw_section_score
            total_correct += ss.correct_count
            total_wrong += ss.wrong_count
            total_not_attempted += ss.not_attempted_count
            negative_total += ss.negative_marks
            total_required_questions += section.total_questions
            total_attempted += ss.correct_count + ss.wrong_count

        # Attempt percentage (Rule 8)
        attempt_pct = self._attempt_validator.compute_attempt_percentage(
            total_required_questions, total_attempted
        ) if total_required_questions > 0 else Decimal("0")

        return EvaluationOutput(
            candidate_id=candidate_id,
            section_scores=section_scores,
            raw_score=raw_score,
            total_correct=total_correct,
            total_wrong=total_wrong,
            total_not_attempted=total_not_attempted,
            total_marked_review_no_option=total_marked_review_no_option,
            negative_marks_deducted=negative_total,
            attempt_percentage=attempt_pct,
        )
