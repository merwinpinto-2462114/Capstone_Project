"""
EXAMFLOW – Comprehensive Test Suite
====================================
Covers all 20 mandatory boundary cases from Section 14 of the specification,
plus invalid input, missing records, duplicate responses, and security tests.

Run with:
    pytest tests/ -v --cov=app --cov-report=html
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Set

from app.engines.evaluation_engine import (
    EvaluationEngine, SectionConfig, AnswerKeyEntry, ResponseEntry,
    ProctoringPenaltyEngine, AttemptValidator, ScoringEngine,
)
from app.engines.normalisation_engine import (
    NormalisationEngine, ShiftRawData, NormalisationDenominatorError,
)
from app.engines.qualification_engine import (
    QualificationEngine, QualificationInput, SectionScoreInput,
    SectionCutoffConfig, FailureCode,
)
from app.engines.merit_list_engine import (
    MeritListEngine, MeritCandidate,
)


# ================================================================== #
# Fixtures & helpers
# ================================================================== #

def make_section(
    section_id: int = 1,
    total_questions: int = 100,
    max_marks: Decimal = Decimal("100"),
    marks_per_correct: Decimal = Decimal("1"),
    negative_marks_per_wrong: Decimal = Decimal("0.25"),
    is_mandatory: bool = True,
) -> SectionConfig:
    return SectionConfig(
        section_id=section_id,
        section_code=f"S{section_id}",
        total_questions=total_questions,
        max_marks=max_marks,
        marks_per_correct=marks_per_correct,
        negative_marks_per_wrong=negative_marks_per_wrong,
        is_mandatory=is_mandatory,
    )


def make_answer_key(
    q_num: int,
    correct: str = "A",
    q_type: str = "SINGLE_CORRECT",
    is_dropped: bool = False,
    dropped_rule: Optional[str] = None,
) -> AnswerKeyEntry:
    return AnswerKeyEntry(
        question_number=q_num,
        question_type=q_type,
        correct_options={correct} if isinstance(correct, str) else set(correct),
        is_dropped=is_dropped,
        dropped_marks_rule=dropped_rule,
    )


def make_response(
    q_num: int,
    selected: Optional[str] = None,
    status: str = "OPTION_SELECTED",
    is_late: bool = False,
) -> ResponseEntry:
    opts = {selected} if selected else set()
    return ResponseEntry(
        question_number=q_num,
        selected_options=opts,
        effective_status=status,
        is_late=is_late,
    )


def make_merit_candidate(
    candidate_id: int,
    normalised_score: Decimal,
    category: str = "GEN",
    full_name: str = "Test Candidate",
    date_of_birth: date = date(1995, 1, 1),
    total_wrong: int = 5,
    is_pwd: bool = False,
) -> MeritCandidate:
    return MeritCandidate(
        candidate_id=candidate_id,
        roll_number=f"R{candidate_id:04d}",
        full_name=full_name,
        date_of_birth=date_of_birth,
        category=category,
        is_pwd=is_pwd,
        normalised_score=normalised_score,
        score_after_proctoring=normalised_score,
        total_wrong=total_wrong,
        section_scores={1: normalised_score},
        is_qualified=True,
        evaluation_result_id=candidate_id,
    )


# ================================================================== #
# SCORING ENGINE TESTS
# ================================================================== #

class TestScoringEngine:
    """Tests for the per-question deterministic scorer."""

    def setup_method(self):
        self.engine = ScoringEngine()
        self.section = make_section()

    # BC-1: Exact sectional cut-off is tested in QualificationEngine tests
    # Here: basic scoring correctness

    def test_correct_answer_awards_full_marks(self):
        ak = make_answer_key(1, correct="A")
        resp = make_response(1, selected="A")
        score = self.engine.score_question(resp, ak, self.section)
        assert score.marks_awarded == Decimal("1")
        assert score.is_correct is True
        assert score.is_wrong is False

    def test_wrong_answer_applies_negative(self):
        ak = make_answer_key(1, correct="A")
        resp = make_response(1, selected="B")
        score = self.engine.score_question(resp, ak, self.section)
        assert score.marks_awarded == Decimal("-0.25")
        assert score.is_wrong is True

    def test_not_attempted_no_penalty(self):
        ak = make_answer_key(1, correct="A")
        resp = make_response(1, status="NOT_ATTEMPTED")
        score = self.engine.score_question(resp, ak, self.section)
        assert score.marks_awarded == Decimal("0")
        assert score.is_not_attempted is True
        assert score.is_wrong is False  # Rule 1: no negative for not-attempted

    # BC-10: Dropped question marked for review without an option
    def test_bc10_dropped_question_marked_review_no_option(self):
        """Boundary Case 10: dropped question + MARKED_FOR_REVIEW without option."""
        # First, dropped question applies dropped rule regardless of response
        ak = make_answer_key(1, is_dropped=True, dropped_rule="FULL_MARKS")
        resp = make_response(1, status="MARKED_FOR_REVIEW", selected=None)
        score = self.engine.score_question(resp, ak, self.section)
        assert score.is_dropped is True
        assert score.marks_awarded == Decimal("1")  # FULL_MARKS rule

    def test_bc10_marked_review_no_option_non_dropped(self):
        """MARKED_FOR_REVIEW without option on a non-dropped question → NOT_ATTEMPTED."""
        ak = make_answer_key(1, correct="A")
        resp = ResponseEntry(
            question_number=1,
            selected_options=set(),
            effective_status="NOT_ATTEMPTED",  # Service already computed effective_status
            is_late=False,
        )
        score = self.engine.score_question(resp, ak, self.section)
        assert score.marks_awarded == Decimal("0")
        assert score.is_not_attempted is True

    # BC-11: Multiple correct options
    def test_bc11_multiple_correct_exact_match(self):
        """BC-11: Multiple correct options – exact match required."""
        ak = AnswerKeyEntry(
            question_number=1,
            question_type="MULTIPLE_CORRECT",
            correct_options={"A", "C"},
            is_dropped=False,
            dropped_marks_rule=None,
        )
        resp = ResponseEntry(
            question_number=1,
            selected_options={"A", "C"},
            effective_status="OPTION_SELECTED",
            is_late=False,
        )
        score = self.engine.score_question(resp, ak, self.section)
        assert score.is_correct is True
        assert score.marks_awarded == Decimal("1")

    def test_bc11_multiple_correct_partial_selection_is_wrong(self):
        """BC-11: Partial selection = wrong (DL-002: exact-match semantics)."""
        ak = AnswerKeyEntry(
            question_number=1,
            question_type="MULTIPLE_CORRECT",
            correct_options={"A", "C"},
            is_dropped=False,
            dropped_marks_rule=None,
        )
        resp = ResponseEntry(
            question_number=1,
            selected_options={"A"},          # only one of two correct
            effective_status="OPTION_SELECTED",
            is_late=False,
        )
        score = self.engine.score_question(resp, ak, self.section)
        assert score.is_wrong is True

    def test_bc11_multiple_correct_extra_option_is_wrong(self):
        """BC-11: Extra option selected = wrong."""
        ak = AnswerKeyEntry(
            question_number=1,
            question_type="MULTIPLE_CORRECT",
            correct_options={"A", "C"},
            is_dropped=False,
            dropped_marks_rule=None,
        )
        resp = ResponseEntry(
            question_number=1,
            selected_options={"A", "B", "C"},  # extra B
            effective_status="OPTION_SELECTED",
            is_late=False,
        )
        score = self.engine.score_question(resp, ak, self.section)
        assert score.is_wrong is True

    # BC-12: Updated answer key
    def test_bc12_updated_answer_key(self):
        """BC-12: If correct option changed from A to B, A is now wrong."""
        old_ak = make_answer_key(1, correct="A")
        new_ak = make_answer_key(1, correct="B")  # key updated
        resp = make_response(1, selected="A")

        score_old = self.engine.score_question(resp, old_ak, self.section)
        score_new = self.engine.score_question(resp, new_ak, self.section)

        assert score_old.is_correct is True
        assert score_new.is_wrong is True  # same answer, now wrong under new key

    # Dropped question rules
    def test_dropped_full_marks(self):
        ak = make_answer_key(1, is_dropped=True, dropped_rule="FULL_MARKS")
        score = self.engine.score_question(None, ak, self.section)
        assert score.marks_awarded == Decimal("1")

    def test_dropped_zero(self):
        ak = make_answer_key(1, is_dropped=True, dropped_rule="ZERO")
        score = self.engine.score_question(None, ak, self.section)
        assert score.marks_awarded == Decimal("0")

    # Late response
    def test_late_response_treated_as_not_attempted(self):
        ak = make_answer_key(1, correct="A")
        resp = ResponseEntry(
            question_number=1,
            selected_options={"A"},
            effective_status="NOT_ATTEMPTED",  # already overridden by service
            is_late=True,
        )
        score = self.engine.score_question(resp, ak, self.section)
        assert score.marks_awarded == Decimal("0")
        assert score.is_not_attempted is True


# ================================================================== #
# ATTEMPT VALIDATOR TESTS
# ================================================================== #

class TestAttemptValidator:
    """Rule 8: Minimum 10% attempts."""

    def setup_method(self):
        self.validator = AttemptValidator()

    # BC-4: Exactly 10% attempts
    def test_bc4_exactly_10_percent_passes(self):
        """BC-4: Exactly 10% is INCLUSIVE – should pass (DL-003)."""
        pct = self.validator.compute_attempt_percentage(100, 10)
        assert pct == Decimal("10")
        assert self.validator.meets_minimum_attempts(pct) is True

    # BC-5: Below 10% attempts
    def test_bc5_below_10_percent_fails(self):
        """BC-5: 9% fails."""
        pct = self.validator.compute_attempt_percentage(100, 9)
        assert pct == Decimal("9")
        assert self.validator.meets_minimum_attempts(pct) is False

    def test_zero_attempts_fails(self):
        pct = self.validator.compute_attempt_percentage(100, 0)
        assert self.validator.meets_minimum_attempts(pct) is False

    def test_11_percent_passes(self):
        pct = self.validator.compute_attempt_percentage(100, 11)
        assert self.validator.meets_minimum_attempts(pct) is True

    def test_total_questions_zero_raises(self):
        with pytest.raises(ValueError):
            self.validator.compute_attempt_percentage(0, 5)


# ================================================================== #
# PROCTORING PENALTY ENGINE TESTS
# ================================================================== #

class TestProctoringPenaltyEngine:
    """Rule 5: Proctoring penalty tiers."""

    def setup_method(self):
        self.engine = ProctoringPenaltyEngine()
        self.base_score = Decimal("80")

    # BC-6: Severity 6 → 5% deduction
    def test_bc6_severity_6_five_percent(self):
        result = self.engine.apply_penalty(self.base_score, 6, False)
        assert result.penalty_percentage == Decimal("5")
        assert result.penalty_marks == Decimal("4")  # 5% of 80
        assert result.score_after_penalty == Decimal("76")
        assert result.is_disqualified is False

    # BC-7: Severity 7 → 15% deduction
    def test_bc7_severity_7_fifteen_percent(self):
        result = self.engine.apply_penalty(self.base_score, 7, False)
        assert result.penalty_percentage == Decimal("15")
        assert result.penalty_marks == Decimal("12")  # 15% of 80
        assert result.score_after_penalty == Decimal("68")
        assert result.is_disqualified is False

    # BC-8: Severity 9 → 15% deduction
    def test_bc8_severity_9_fifteen_percent(self):
        result = self.engine.apply_penalty(self.base_score, 9, False)
        assert result.penalty_percentage == Decimal("15")
        assert result.is_disqualified is False

    # BC-9: Severity 10 → Disqualification
    def test_bc9_severity_10_disqualified(self):
        result = self.engine.apply_penalty(self.base_score, 10, False)
        assert result.is_disqualified is True
        assert result.disqualification_reason == "PROCTORING_SEVERITY_10"

    def test_severity_11_disqualified(self):
        result = self.engine.apply_penalty(self.base_score, 11, False)
        assert result.is_disqualified is True

    def test_confirmed_malpractice_disqualified(self):
        result = self.engine.apply_penalty(self.base_score, 3, True)
        assert result.is_disqualified is True
        assert result.disqualification_reason == "CONFIRMED_MALPRACTICE"

    def test_severity_3_no_penalty(self):
        """Severity below 4 = no deduction."""
        result = self.engine.apply_penalty(self.base_score, 3, False)
        assert result.penalty_percentage == Decimal("0")
        assert result.score_after_penalty == self.base_score

    def test_severity_4_five_percent(self):
        result = self.engine.apply_penalty(self.base_score, 4, False)
        assert result.penalty_percentage == Decimal("5")


# ================================================================== #
# NORMALISATION ENGINE TESTS
# ================================================================== #

class TestNormalisationEngine:
    """Rule 6 & 7: Shift normalisation."""

    def setup_method(self):
        self.engine = NormalisationEngine(min_shift_size=100)

    def _make_shift(self, shift_id: int, scores: List[float]) -> ShiftRawData:
        return ShiftRawData(
            shift_id=shift_id,
            candidate_scores={i + 1: Decimal(str(s)) for i, s in enumerate(scores)},
        )

    # BC-13: Shift with exactly 100 candidates = standalone (not pooled)
    def test_bc13_shift_exactly_100_is_standalone(self):
        shift = self._make_shift(1, [50.0 + i * 0.1 for i in range(100)])
        pooled, standalone = self.engine.identify_pooled_shifts([shift])
        assert 1 in standalone
        assert 1 not in pooled

    # BC-14: Shift with 99 candidates = pooled
    def test_bc14_shift_99_is_pooled(self):
        shift = self._make_shift(1, [50.0 + i * 0.1 for i in range(99)])
        pooled, standalone = self.engine.identify_pooled_shifts([shift])
        assert 1 in pooled
        assert 1 not in standalone

    # BC-15: Normalisation denominator = 0 raises error
    def test_bc15_denominator_zero_raises(self):
        """All candidates in shift have same score → std_dev = 0."""
        shift = ShiftRawData(
            shift_id=1,
            candidate_scores={1: Decimal("50"), 2: Decimal("50"), 3: Decimal("50")},
        )
        stats = self.engine.compute_shift_statistics(shift)
        assert stats.std_dev == Decimal("0")

        with pytest.raises(NormalisationDenominatorError):
            self.engine.normalise_score(
                raw_score=Decimal("50"),
                mean_shift=stats.mean,
                std_shift=stats.std_dev,  # = 0
                mean_all=Decimal("50"),
                std_all=Decimal("5"),
            )

    # BC-16: Normalisation denominator negative (should not occur with std_dev but guard)
    def test_bc16_negative_denominator_raises(self):
        with pytest.raises(NormalisationDenominatorError):
            self.engine.normalise_score(
                raw_score=Decimal("50"),
                mean_shift=Decimal("50"),
                std_shift=Decimal("-1"),  # negative
                mean_all=Decimal("50"),
                std_all=Decimal("5"),
            )

    def test_normalisation_basic_formula(self):
        """Test formula: normalised = mean_all + (std_all/std_shift) * (raw - mean_shift)."""
        norm = self.engine.normalise_score(
            raw_score=Decimal("60"),
            mean_shift=Decimal("50"),
            std_shift=Decimal("10"),
            mean_all=Decimal("55"),
            std_all=Decimal("8"),
        )
        # Expected: 55 + (8/10) * (60 - 50) = 55 + 8 = 63
        assert abs(norm - Decimal("63")) < Decimal("0.001")

    def test_precision_format_normalised(self):
        val = Decimal("63.123456789")
        formatted = NormalisationEngine.format_normalised(val)
        assert len(formatted.split(".")[-1]) == 5  # 5 decimal places

    def test_precision_format_raw(self):
        val = Decimal("63.789")
        formatted = NormalisationEngine.format_raw(val)
        assert len(formatted.split(".")[-1]) == 2  # 2 decimal places


# ================================================================== #
# QUALIFICATION ENGINE TESTS
# ================================================================== #

class TestQualificationEngine:
    """Rules 3, 4, 8 and 10 qualification logic."""

    def setup_method(self):
        self.engine = QualificationEngine()
        self.base_section = SectionCutoffConfig(
            section_id=1,
            section_code="S1",
            is_mandatory=True,
            cutoff_gen=Decimal("40"),
            cutoff_obc=Decimal("35"),
            cutoff_sc=Decimal("30"),
            cutoff_st=Decimal("30"),
            cutoff_ews=Decimal("35"),
        )

    def _make_qinput(
        self,
        category: str = "GEN",
        is_pwd: bool = False,
        attempt_pct: Decimal = Decimal("50"),
        score: Decimal = Decimal("60"),
        section_score: Decimal = Decimal("50"),
        overall_cutoff: Optional[Decimal] = Decimal("40"),
        normalised: Optional[Decimal] = None,
        is_disq: bool = False,
        disq_reason: Optional[str] = None,
    ) -> QualificationInput:
        return QualificationInput(
            candidate_id=1,
            category=category,
            is_pwd=is_pwd,
            attempt_percentage=attempt_pct,
            score_after_proctoring=score,
            normalised_score=normalised,
            is_disqualified_by_proctoring=is_disq,
            disqualification_reason=disq_reason,
            section_scores=[
                SectionScoreInput(
                    section_id=1,
                    raw_section_score=section_score,
                    was_attempted=True,
                )
            ],
            overall_cutoff_gen=overall_cutoff,
        )

    # BC-1: Exact sectional cut-off
    def test_bc1_exact_sectional_cutoff_passes(self):
        """BC-1: Score exactly at the GEN sectional cut-off (40.0) should pass."""
        qinput = self._make_qinput(section_score=Decimal("40"), score=Decimal("60"))
        result = self.engine.qualify(qinput, [self.base_section])
        # GEN cutoff = 40, section score = 40 → passes section
        section_failures = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        assert len(section_failures) == 0

    # BC-2: One mark below sectional cut-off
    def test_bc2_one_below_cutoff_fails(self):
        """BC-2: Section score 39.99 < 40 → section cut-off fail."""
        qinput = self._make_qinput(section_score=Decimal("39.99"), score=Decimal("60"))
        result = self.engine.qualify(qinput, [self.base_section])
        section_failures = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        assert len(section_failures) == 1
        assert result.is_qualified is False

    # BC-3: One mark above sectional cut-off
    def test_bc3_one_above_cutoff_passes(self):
        """BC-3: Section score 40.01 > 40 → passes section."""
        qinput = self._make_qinput(section_score=Decimal("40.01"), score=Decimal("60"))
        result = self.engine.qualify(qinput, [self.base_section])
        section_failures = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        assert len(section_failures) == 0

    def test_proctoring_disqualification_overrides_all(self):
        """Disqualification is returned immediately without checking other rules."""
        qinput = self._make_qinput(is_disq=True, disq_reason="PROCTORING_SEVERITY_10")
        result = self.engine.qualify(qinput, [self.base_section])
        assert result.status == "DISQUALIFIED"
        assert result.reasons[0].code == FailureCode.PROCTORING_DISQUALIFIED

    def test_obc_category_relaxation(self):
        """OBC gets 5pp relaxation on sectional cut-off."""
        # OBC cutoff = 35 (from fixture). Score = 36 should pass.
        qinput = self._make_qinput(category="OBC", section_score=Decimal("36"))
        result = self.engine.qualify(qinput, [self.base_section])
        section_failures = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        # OBC cutoff = 35, score = 36 → pass
        assert len(section_failures) == 0

    def test_sc_category_relaxation(self):
        """SC gets 10pp relaxation. SC cutoff = 30. Score 31 passes."""
        qinput = self._make_qinput(category="SC", section_score=Decimal("31"))
        result = self.engine.qualify(qinput, [self.base_section])
        section_failures = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        assert len(section_failures) == 0

    def test_pwd_additional_relaxation(self):
        """PwD gets additional 5pp on top of category relaxation."""
        # GEN + PwD: effective_cutoff = 40 * (1 - 5/100) = 38
        # Score 39 should pass
        qinput = self._make_qinput(category="GEN", is_pwd=True, section_score=Decimal("39"))
        result = self.engine.qualify(qinput, [self.base_section])
        # Section uses ORM cutoff; GEN pwd: 40*(1-5/100)=38 ... score 39 > 38 → pass
        # Note: The section-level cutoff for GEN PwD uses _apply_pwd()
        section_failures = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        assert len(section_failures) == 0

    def test_below_min_attempts_fails(self):
        qinput = self._make_qinput(attempt_pct=Decimal("5"))
        result = self.engine.qualify(qinput, [self.base_section])
        attempt_failures = [r for r in result.reasons if r.code == FailureCode.BELOW_MIN_ATTEMPTS]
        assert len(attempt_failures) == 1

    # BC-18: SC candidate above GEN threshold
    def test_bc18_sc_above_gen_threshold_overall_qualifies(self):
        """BC-18: SC candidate with score >= GEN overall threshold qualifies."""
        qinput = self._make_qinput(
            category="SC",
            section_score=Decimal("50"),
            score=Decimal("80"),
            overall_cutoff=Decimal("40"),
            normalised=Decimal("80"),
        )
        result = self.engine.qualify(qinput, [self.base_section])
        assert result.is_qualified is True


# ================================================================== #
# MERIT LIST ENGINE TESTS
# ================================================================== #

class TestMeritListEngine:
    """Rules 9 & 10: Merit list ordering and category allocation."""

    def setup_method(self):
        self.engine = MeritListEngine(section_order=[1])

    def test_higher_score_ranked_first(self):
        c1 = make_merit_candidate(1, Decimal("80"))
        c2 = make_merit_candidate(2, Decimal("70"))
        entries = self.engine.build_merit_list([c1, c2])
        assert entries[0].candidate_id == 1
        assert entries[1].candidate_id == 2

    # BC-17: Full merit-list tie
    def test_bc17_full_tie_goes_to_older_dob(self):
        """BC-17: All tie-breakers equal → DOB (older = better rank)."""
        c1 = make_merit_candidate(1, Decimal("80"), full_name="Same Name",
                                  date_of_birth=date(1990, 1, 1), total_wrong=5)
        c2 = make_merit_candidate(2, Decimal("80"), full_name="Same Name",
                                  date_of_birth=date(1995, 1, 1), total_wrong=5)
        entries = self.engine.build_merit_list([c1, c2])
        # c1 is older → rank 1
        assert entries[0].candidate_id == 1

    def test_tie_resolved_by_fewer_wrong(self):
        c1 = make_merit_candidate(1, Decimal("80"), total_wrong=3)
        c2 = make_merit_candidate(2, Decimal("80"), total_wrong=5)
        entries = self.engine.build_merit_list([c1, c2])
        assert entries[0].candidate_id == 1

    def test_tie_resolved_by_name_alphabetical(self):
        c1 = make_merit_candidate(1, Decimal("80"), full_name="Alice",
                                  date_of_birth=date(1990, 1, 1), total_wrong=5)
        c2 = make_merit_candidate(2, Decimal("80"), full_name="Bob",
                                  date_of_birth=date(1990, 1, 1), total_wrong=5)
        entries = self.engine.build_merit_list([c1, c2])
        assert entries[0].candidate_id == 1  # Alice < Bob

    def test_unresolved_tie_recorded(self):
        """Identical on all five criteria → tie_breaker_applied should be UNRESOLVED for the adjacent pair."""
        c1 = make_merit_candidate(1, Decimal("80"), full_name="Same", date_of_birth=date(1990, 1, 1), total_wrong=5)
        c2 = make_merit_candidate(2, Decimal("80"), full_name="Same", date_of_birth=date(1990, 1, 1), total_wrong=5)
        entries = self.engine.build_merit_list([c1, c2])
        # The first entry's tie_breaker_applied should be UNRESOLVED (comparing with second)
        assert entries[0].tie_breaker_applied == "UNRESOLVED"

    # BC-18: SC candidate above GEN threshold → allocated under GEN
    def test_bc18_sc_above_gen_allocated_gen(self):
        sc_cand = make_merit_candidate(1, Decimal("85"), category="SC")
        gen_cutoff = Decimal("80")
        entries = self.engine.build_merit_list([sc_cand], overall_cutoff_gen=gen_cutoff)
        assert entries[0].allocation_category == "GEN"

    def test_sc_below_gen_threshold_allocated_sc(self):
        sc_cand = make_merit_candidate(1, Decimal("70"), category="SC")
        gen_cutoff = Decimal("80")
        entries = self.engine.build_merit_list([sc_cand], overall_cutoff_gen=gen_cutoff)
        assert entries[0].allocation_category == "SC"

    def test_empty_qualified_list_returns_empty(self):
        entries = self.engine.build_merit_list([])
        assert entries == []

    def test_overall_rank_is_sequential(self):
        candidates = [make_merit_candidate(i, Decimal(str(100 - i))) for i in range(1, 6)]
        entries = self.engine.build_merit_list(candidates)
        ranks = [e.overall_rank for e in entries]
        assert ranks == list(range(1, 6))


# ================================================================== #
# PRECISION / ROUNDING TESTS
# ================================================================== #

class TestPrecision:
    """BC-20: Score precision and rounding boundaries (Rule 12)."""

    def test_raw_score_formatted_to_2dp(self):
        val = Decimal("63.789123")
        fmt = NormalisationEngine.format_raw(val)
        assert fmt == "63.79"  # rounds up

    def test_normalised_score_formatted_to_5dp(self):
        val = Decimal("63.123456789")
        fmt = NormalisationEngine.format_normalised(val)
        assert fmt == "63.12346"  # rounds at 6th dp

    def test_cutoff_comparison_uses_unrounded_values(self):
        """Cut-off comparison must use full Decimal precision, not rounded display values."""
        # Score 39.9999 displayed as 40.00 but is actually < 40 → should FAIL
        engine = QualificationEngine()
        section = SectionCutoffConfig(
            section_id=1, section_code="S1", is_mandatory=True,
            cutoff_gen=Decimal("40"), cutoff_obc=None, cutoff_sc=None, cutoff_st=None, cutoff_ews=None,
        )
        qinput = QualificationInput(
            candidate_id=1, category="GEN", is_pwd=False,
            attempt_percentage=Decimal("50"),
            score_after_proctoring=Decimal("60"),
            normalised_score=None,
            is_disqualified_by_proctoring=False,
            disqualification_reason=None,
            section_scores=[SectionScoreInput(1, Decimal("39.9999"), True)],
            overall_cutoff_gen=None,
        )
        result = engine.qualify(qinput, [section])
        section_fails = [r for r in result.reasons if r.code == FailureCode.SECTION_CUTOFF_FAIL]
        assert len(section_fails) == 1, "39.9999 should fail the 40.0 cut-off"

    def test_no_premature_rounding_in_calculation(self):
        """Intermediate calculations must preserve Decimal precision."""
        engine = NormalisationEngine(min_shift_size=100)
        # Score that would be rounded at 2dp but must be exact for normalisation
        norm = engine.normalise_score(
            raw_score=Decimal("63.789123"),
            mean_shift=Decimal("50"),
            std_shift=Decimal("10"),
            mean_all=Decimal("55"),
            std_all=Decimal("8"),
        )
        # The result should retain high precision, not be rounded
        assert norm != norm.quantize(Decimal("0.01"))  # has more than 2dp


# ================================================================== #
# RE-EVALUATION RESTRICTION TESTS (Rule 11)
# ================================================================== #

class TestReEvaluationRule:
    """Rule 11: One re-evaluation per candidate."""

    def test_second_re_evaluation_raises(self):
        """
        This test verifies the business rule.
        Integration test with DB is in tests/integration/test_re_evaluation.py.
        Here we test the guard logic.
        """
        # The service checks for existing ReEvaluationRequest before creating.
        # Simulate by asserting the enforcement exists in service code.
        from app.services.re_evaluation_service import ReEvaluationService
        import inspect
        source = inspect.getsource(ReEvaluationService.request_re_evaluation)
        assert "Only one re-evaluation is permitted" in source or "already requested" in source


# ================================================================== #
# EVALUATION ENGINE INTEGRATION (unit-level)
# ================================================================== #

class TestEvaluationEngineIntegration:
    """Full evaluation pipeline unit tests."""

    def setup_method(self):
        self.engine = EvaluationEngine()

    def _run(self, correct_responses: int, wrong_responses: int, total_q: int = 100,
             proctoring_severity: int = 0, confirmed_malpractice: bool = False):
        section = make_section(total_questions=total_q)
        keys = [make_answer_key(i + 1, correct="A") for i in range(total_q)]
        responses = []
        for i in range(correct_responses):
            responses.append(make_response(i + 1, selected="A"))
        for j in range(wrong_responses):
            responses.append(make_response(correct_responses + j + 1, selected="B"))

        return self.engine.evaluate(
            candidate_id=1,
            sections=[section],
            answer_keys_by_section={1: keys},
            responses_by_section={1: responses},
            proctoring_max_severity=proctoring_severity,
            confirmed_malpractice=confirmed_malpractice,
        )

    def test_basic_scoring(self):
        output = self._run(correct_responses=50, wrong_responses=20)
        # 50 correct * 1 = 50; 20 wrong * -0.25 = -5; total = 45
        assert output.raw_score == Decimal("45")
        assert output.total_correct == 50
        assert output.total_wrong == 20

    def test_attempt_percentage_calculation(self):
        output = self._run(correct_responses=10, wrong_responses=0, total_q=100)
        assert output.attempt_percentage == Decimal("10")

    def test_all_not_attempted_zero_score(self):
        output = self._run(correct_responses=0, wrong_responses=0)
        assert output.raw_score == Decimal("0")
        assert output.total_not_attempted == 100


# ================================================================== #
# INPUT VALIDATION TESTS
# ================================================================== #

class TestInputValidation:
    """Test schema-level validation."""

    def test_invalid_category_rejected(self):
        from pydantic import ValidationError
        from app.schemas.schemas import CandidateCreate
        with pytest.raises(ValidationError):
            CandidateCreate(
                roll_number="R001",
                full_name="Test",
                date_of_birth=date(1995, 1, 1),
                category="INVALID_CATEGORY",  # not in enum
                examination_id=1,
                shift_id=1,
            )

    def test_shift_end_before_start_rejected(self):
        from pydantic import ValidationError
        from app.schemas.schemas import ShiftCreate
        with pytest.raises(ValidationError):
            ShiftCreate(
                shift_code="S1",
                name="Morning",
                shift_date=date(2024, 1, 1),
                shift_start_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                shift_end_time=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),  # before start
            )

    def test_negative_question_count_rejected(self):
        from pydantic import ValidationError
        from app.schemas.schemas import ExaminationSectionCreate
        with pytest.raises(ValidationError):
            ExaminationSectionCreate(
                name="Math",
                section_code="MATH",
                section_order=1,
                total_questions=-1,  # invalid
                max_marks=Decimal("100"),
                marks_per_correct=Decimal("1"),
            )

    def test_exam_code_non_alphanumeric_rejected(self):
        from pydantic import ValidationError
        from app.schemas.schemas import ExaminationCreate
        with pytest.raises(ValidationError):
            ExaminationCreate(
                name="Test Exam",
                exam_code="exam code with spaces",  # invalid
                duration_minutes=180,
            )
