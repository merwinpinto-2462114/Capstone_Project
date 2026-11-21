"""
EXAMFLOW – Merit List Engine (PS-072 Rules 9 & 10)
===================================================
Implements deterministic merit-list ordering and category allocation.

Tie-breaking order (Rule 9):
  1. Higher normalised score
  2. Higher relevant sectional score (order from approved rule register – see DL-006)
  3. Fewer incorrect answers
  4. Older date of birth (earlier date = older)
  5. Alphabetical full name (ascending, case-insensitive)
  6. UNRESOLVED – recorded per approved policy, NOT silently broken

Rule 10 – Category cut-offs:
  - Reserved-category candidates scoring ≥ GEN threshold are allocated under GEN
    (freeing reserved slots) per approved allocation rule (DL-007).

Decision Log:
  DL-006: Tie-breaker sectional order: not yet officially specified.
           Placeholder: sections in ascending section_order.
           Must be confirmed from the approved rule register.
  DL-007: GEN threshold allocation for reserved candidates: candidate counted in
           GEN allocation if their normalised score >= overall_cutoff_gen.
           If the approved rule differs, update allocate_category().
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ================================================================== #
# Data classes
# ================================================================== #

@dataclass
class MeritCandidate:
    candidate_id: int
    roll_number: str
    full_name: str
    date_of_birth: date
    category: str               # GEN | OBC | SC | ST | EWS
    is_pwd: bool
    normalised_score: Decimal
    score_after_proctoring: Decimal
    total_wrong: int
    section_scores: Dict[int, Decimal]  # section_id → raw_section_score
    is_qualified: bool
    evaluation_result_id: int


@dataclass
class MeritEntry:
    candidate_id: int
    roll_number: str
    full_name: str
    category: str
    is_pwd: bool
    overall_rank: int
    category_rank: Optional[int]
    final_score: Decimal
    tie_breaker_applied: str   # None | SECTION_SCORE | WRONG_COUNT | DOB | NAME | UNRESOLVED
    is_allocated: bool
    allocation_category: str
    evaluation_result_id: int


# ================================================================== #
# Tie-breaker comparator
# ================================================================== #

def _tiebreak_key(
    candidate: MeritCandidate,
    section_order: List[int],  # section_ids in priority order (DL-006)
) -> tuple:
    """
    Returns a sort key such that lower tuple value = better rank.
    All fields are negated/inverted to allow ascending sort to give descending merit.
    """
    # 1. Higher normalised score → negate for ascending sort
    score_key = -candidate.normalised_score

    # 2. Sectional scores in configured order (DL-006 placeholder)
    section_key = tuple(
        -candidate.section_scores.get(sid, Decimal("0"))
        for sid in section_order
    )

    # 3. Fewer wrong answers
    wrong_key = candidate.total_wrong

    # 4. Older date of birth → earlier date = smaller value
    dob_key = candidate.date_of_birth

    # 5. Alphabetical name ascending (case-insensitive)
    name_key = candidate.full_name.lower()

    return (score_key, *section_key, wrong_key, dob_key, name_key)


def _determine_tiebreaker(c1: MeritCandidate, c2: MeritCandidate, section_order: List[int]) -> str:
    """Identify which tie-breaker separated two adjacent candidates."""
    if c1.normalised_score != c2.normalised_score:
        return "NORMALISED_SCORE"

    for sid in section_order:
        s1 = c1.section_scores.get(sid, Decimal("0"))
        s2 = c2.section_scores.get(sid, Decimal("0"))
        if s1 != s2:
            return "SECTION_SCORE"

    if c1.total_wrong != c2.total_wrong:
        return "WRONG_COUNT"

    if c1.date_of_birth != c2.date_of_birth:
        return "DOB"

    if c1.full_name.lower() != c2.full_name.lower():
        return "NAME"

    return "UNRESOLVED"


# ================================================================== #
# Merit List Engine
# ================================================================== #

class MeritListEngine:
    """
    Builds the final merit list with deterministic ordering.
    """

    def __init__(self, section_order: Optional[List[int]] = None):
        """
        section_order: list of section_ids in tie-breaker priority (DL-006).
        If not supplied, tie-breaker step 2 is skipped (all sections treated equal).
        """
        self.section_order = section_order or []

    def build_merit_list(
        self,
        candidates: List[MeritCandidate],
        overall_cutoff_gen: Optional[Decimal] = None,
    ) -> List[MeritEntry]:
        """
        Returns fully ranked and allocated merit list entries.
        Only qualified candidates are included.
        """
        qualified = [c for c in candidates if c.is_qualified]

        if not qualified:
            return []

        # --- Sort deterministically ---
        sorted_candidates = sorted(
            qualified,
            key=lambda c: _tiebreak_key(c, self.section_order),
        )

        entries: List[MeritEntry] = []
        category_rank_counters: Dict[str, int] = {}

        for overall_rank, (candidate, next_candidate) in enumerate(
            self._adjacent_pairs(sorted_candidates), start=1
        ):
            # Determine which tie-breaker was applied (compare with next candidate)
            if next_candidate is not None:
                tb = _determine_tiebreaker(candidate, next_candidate, self.section_order)
            else:
                tb = "NONE"  # Last candidate — no comparison needed

            # Allocate category (Rule 10 – DL-007)
            alloc_cat = self.allocate_category(candidate, overall_cutoff_gen)
            cat_rank = category_rank_counters.get(alloc_cat, 0) + 1
            category_rank_counters[alloc_cat] = cat_rank

            entries.append(
                MeritEntry(
                    candidate_id=candidate.candidate_id,
                    roll_number=candidate.roll_number,
                    full_name=candidate.full_name,
                    category=candidate.category,
                    is_pwd=candidate.is_pwd,
                    overall_rank=overall_rank,
                    category_rank=cat_rank,
                    final_score=candidate.normalised_score,
                    tie_breaker_applied=tb,
                    is_allocated=True,
                    allocation_category=alloc_cat,
                    evaluation_result_id=candidate.evaluation_result_id,
                )
            )

        return entries

    @staticmethod
    def allocate_category(
        candidate: MeritCandidate,
        overall_cutoff_gen: Optional[Decimal],
    ) -> str:
        """
        Rule 10 (DL-007): A reserved-category candidate scoring >= GEN threshold
        is allocated under GEN. Otherwise allocated under their own category.
        """
        if (
            candidate.category != "GEN"
            and overall_cutoff_gen is not None
            and candidate.normalised_score >= overall_cutoff_gen
        ):
            return "GEN"
        return candidate.category

    @staticmethod
    def _adjacent_pairs(lst: List[MeritCandidate]):
        """Yield (item, next_item_or_None) pairs."""
        for i, item in enumerate(lst):
            yield item, lst[i + 1] if i + 1 < len(lst) else None
