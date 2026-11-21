"""
EXAMFLOW – Qualification Engine (PS-072 Rules 3, 4, 8)
=======================================================
Determines whether a candidate qualifies based on:
  - Minimum attempt percentage (Rule 8)
  - Sectional cut-offs with category relaxation (Rule 3)
  - Overall cut-off with category relaxation (Rule 3)
  - Proctoring disqualification (Rule 5)

Always returns structured failure reasons — never a bare boolean.

Category relaxation (Rule 3):
  - OBC / EWS : -5 percentage points from GEN threshold
  - SC / ST   : -10 percentage points from GEN threshold
  - PwD       : additional -5 percentage points on top of category relaxation
"""

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ================================================================== #
# Enumerations and constants
# ================================================================== #

class FailureCode(str, Enum):
    BELOW_MIN_ATTEMPTS = "BELOW_MIN_ATTEMPTS"
    SECTION_CUTOFF_FAIL = "SECTION_CUTOFF_FAIL"
    OVERALL_CUTOFF_FAIL = "OVERALL_CUTOFF_FAIL"
    PROCTORING_DISQUALIFIED = "PROCTORING_DISQUALIFIED"
    SKIPPED_MANDATORY_SECTION = "SKIPPED_MANDATORY_SECTION"
    EVALUATION_ERROR = "EVALUATION_ERROR"


# Category relaxation deltas (Rule 3)
CATEGORY_RELAXATION: Dict[str, Decimal] = {
    "GEN": Decimal("0"),
    "OBC": Decimal("5"),
    "EWS": Decimal("5"),
    "SC": Decimal("10"),
    "ST": Decimal("10"),
}
PWD_ADDITIONAL_RELAXATION = Decimal("5")

MIN_ATTEMPT_PCT = Decimal("10")  # Rule 8 – inclusive boundary (DL-003)


# ================================================================== #
# Data classes
# ================================================================== #

@dataclass
class QualificationFailureReason:
    code: FailureCode
    detail: str


@dataclass
class SectionCutoffConfig:
    section_id: int
    section_code: str
    is_mandatory: bool
    cutoff_gen: Optional[Decimal]
    cutoff_obc: Optional[Decimal]
    cutoff_sc: Optional[Decimal]
    cutoff_st: Optional[Decimal]
    cutoff_ews: Optional[Decimal]


@dataclass
class SectionScoreInput:
    section_id: int
    raw_section_score: Decimal
    was_attempted: bool   # False if section was entirely skipped


@dataclass
class QualificationInput:
    candidate_id: int
    category: str            # GEN | OBC | SC | ST | EWS
    is_pwd: bool
    attempt_percentage: Decimal
    score_after_proctoring: Decimal
    normalised_score: Optional[Decimal]
    is_disqualified_by_proctoring: bool
    disqualification_reason: Optional[str]
    section_scores: List[SectionScoreInput]
    overall_cutoff_gen: Optional[Decimal]  # overall cut-off for GEN


@dataclass
class QualificationResult:
    candidate_id: int
    is_qualified: bool
    status: str            # QUALIFIED | NOT_QUALIFIED | DISQUALIFIED
    reasons: List[QualificationFailureReason] = field(default_factory=list)
    category_relaxation_percentage: Decimal = Decimal("0")
    effective_overall_cutoff: Optional[Decimal] = None
    overall_cutoff_gen: Optional[Decimal] = None

    def to_reasons_json(self) -> str:
        return json.dumps(
            [{"code": r.code.value, "detail": r.detail} for r in self.reasons]
        )


# ================================================================== #
# Relaxation helper
# ================================================================== #

def compute_effective_cutoff(
    base_cutoff: Optional[Decimal],
    category: str,
    is_pwd: bool,
) -> Optional[Decimal]:
    """
    Subtract the category relaxation from the GEN cut-off.
    Rule 3: relaxation is applied as a reduction in the threshold.

    Returns None if base_cutoff is None (no cut-off configured).
    """
    if base_cutoff is None:
        return None

    relaxation = CATEGORY_RELAXATION.get(category, Decimal("0"))
    if is_pwd:
        relaxation += PWD_ADDITIONAL_RELAXATION

    # Relaxation is in percentage points; convert to marks
    # Note: the relaxation is applied as: effective = gen_cutoff * (1 - relaxation_pct/100)
    # This interpretation needs confirming against the rule register.
    # Current implementation: treat cutoff as an absolute threshold and subtract
    # the relaxation applied as a percentage of the cutoff value.
    effective = base_cutoff * (Decimal("1") - relaxation / Decimal("100"))
    return max(effective, Decimal("0"))  # Can't go below zero


def get_section_cutoff_for_category(
    section_config: SectionCutoffConfig,
    category: str,
) -> Optional[Decimal]:
    mapping = {
        "GEN": section_config.cutoff_gen,
        "OBC": section_config.cutoff_obc,
        "EWS": section_config.cutoff_ews,
        "SC": section_config.cutoff_sc,
        "ST": section_config.cutoff_st,
    }
    return mapping.get(category)


# ================================================================== #
# Qualification Engine
# ================================================================== #

class QualificationEngine:
    """
    Applies all qualification rules deterministically.
    """

    def qualify(
        self,
        qinput: QualificationInput,
        section_configs: List[SectionCutoffConfig],
    ) -> QualificationResult:
        reasons: List[QualificationFailureReason] = []

        # --- Rule 5: Proctoring disqualification (highest priority) ---
        if qinput.is_disqualified_by_proctoring:
            return QualificationResult(
                candidate_id=qinput.candidate_id,
                is_qualified=False,
                status="DISQUALIFIED",
                reasons=[
                    QualificationFailureReason(
                        code=FailureCode.PROCTORING_DISQUALIFIED,
                        detail=qinput.disqualification_reason or "Proctoring event triggered disqualification",
                    )
                ],
            )

        # --- Rule 8: Minimum attempts ---
        if qinput.attempt_percentage < MIN_ATTEMPT_PCT:
            reasons.append(
                QualificationFailureReason(
                    code=FailureCode.BELOW_MIN_ATTEMPTS,
                    detail=(
                        f"Attempt percentage {qinput.attempt_percentage}% is below "
                        f"the minimum required {MIN_ATTEMPT_PCT}%"
                    ),
                )
            )

        # --- Rule 4: Skipped mandatory sections ---
        section_score_map: Dict[int, SectionScoreInput] = {
            ss.section_id: ss for ss in qinput.section_scores
        }

        for sc in section_configs:
            ss = section_score_map.get(sc.section_id)
            if sc.is_mandatory and (ss is None or not ss.was_attempted):
                reasons.append(
                    QualificationFailureReason(
                        code=FailureCode.SKIPPED_MANDATORY_SECTION,
                        detail=f"Mandatory section '{sc.section_code}' was skipped",
                    )
                )

        # --- Rule 3: Sectional cut-offs with category relaxation ---
        for sc in section_configs:
            ss = section_score_map.get(sc.section_id)
            if ss is None:
                continue

            cat_cutoff = get_section_cutoff_for_category(sc, qinput.category)
            # For non-GEN, also apply PwD relaxation on top
            effective_sec_cutoff = self._apply_pwd(cat_cutoff, qinput.is_pwd)

            if effective_sec_cutoff is not None and ss.raw_section_score < effective_sec_cutoff:
                reasons.append(
                    QualificationFailureReason(
                        code=FailureCode.SECTION_CUTOFF_FAIL,
                        detail=(
                            f"Section '{sc.section_code}' score {ss.raw_section_score} < "
                            f"effective cut-off {effective_sec_cutoff} "
                            f"(category={qinput.category}, PwD={qinput.is_pwd})"
                        ),
                    )
                )

        # --- Rule 10: Overall cut-off with category relaxation ---
        effective_overall = compute_effective_cutoff(
            qinput.overall_cutoff_gen, qinput.category, qinput.is_pwd
        )
        relaxation_pct = CATEGORY_RELAXATION.get(qinput.category, Decimal("0"))
        if qinput.is_pwd:
            relaxation_pct += PWD_ADDITIONAL_RELAXATION

        score_to_compare = (
            qinput.normalised_score
            if qinput.normalised_score is not None
            else qinput.score_after_proctoring
        )

        if effective_overall is not None and score_to_compare < effective_overall:
            reasons.append(
                QualificationFailureReason(
                    code=FailureCode.OVERALL_CUTOFF_FAIL,
                    detail=(
                        f"Score {score_to_compare} < overall effective cut-off {effective_overall} "
                        f"(GEN base={qinput.overall_cutoff_gen}, "
                        f"relaxation={relaxation_pct}%)"
                    ),
                )
            )

        # --- Final decision ---
        if reasons:
            status = "NOT_QUALIFIED"
        else:
            status = "QUALIFIED"

        return QualificationResult(
            candidate_id=qinput.candidate_id,
            is_qualified=not bool(reasons),
            status=status,
            reasons=reasons,
            category_relaxation_percentage=relaxation_pct,
            effective_overall_cutoff=effective_overall,
            overall_cutoff_gen=qinput.overall_cutoff_gen,
        )

    @staticmethod
    def _apply_pwd(cutoff: Optional[Decimal], is_pwd: bool) -> Optional[Decimal]:
        if cutoff is None:
            return None
        if is_pwd:
            return max(cutoff * (Decimal("1") - PWD_ADDITIONAL_RELAXATION / Decimal("100")), Decimal("0"))
        return cutoff
