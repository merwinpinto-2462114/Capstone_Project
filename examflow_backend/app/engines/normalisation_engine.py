"""
EXAMFLOW – Normalisation Engine (PS-072 Rule 6 & 7)
=====================================================
Implements shift normalisation exactly as specified in PS-072.

Formula used:
    normalised_score_i = (
        (mean_all + (std_all / std_shift) * (raw_score_i - mean_shift))
    )

Where:
    mean_shift  = arithmetic mean of raw scores in the candidate's shift
    std_shift   = population standard deviation of raw scores in the shift
    mean_all    = arithmetic mean across ALL shifts (or pooled group)
    std_all     = population standard deviation across ALL shifts (or pooled group)

NOTE: If the official PS-072 specification supplies a different formula, replace
      this implementation. Do NOT substitute based on assumptions — raise DL-004.

Rule 7 – Denominator guard:
    If std_shift <= 0, raise NormalisationDenominatorError.
    The calling service MUST handle this and log a decision item.

Rule 6 – Small-shift pooling:
    Shifts with fewer than MIN_SHIFT_SIZE candidates (default 100) are pooled.
    Pooled shifts share the combined population's statistics.

Decision Log:
- DL-004: Formula confirmed as the PERCENTILE/Z-SCORE re-scaling variant.
          Official formula from signed PS-072 document must be verified against
          this implementation before production use.
- DL-005: Denominator guard behaviour: raise exception → service logs DL item.
          Do NOT silently assign 0 or the raw score.
"""

import logging
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

PRECISION_NORMALISED = Decimal("0.00001")  # 5 decimal places for display


class NormalisationDenominatorError(Exception):
    """Raised when shift std_dev <= 0 (Rule 7 guard)."""
    pass


# ================================================================== #
# Data classes
# ================================================================== #

@dataclass
class ShiftRawData:
    shift_id: int
    candidate_scores: Dict[int, Decimal]  # candidate_id → raw_score


@dataclass
class ShiftStatisticsComputed:
    shift_id: int
    candidate_count: int
    mean: Decimal
    std_dev: Decimal          # population std dev


@dataclass
class NormalisationInput:
    candidate_id: int
    shift_id: int
    raw_score: Decimal


@dataclass
class NormalisationOutput:
    candidate_id: int
    shift_id: int
    raw_score: Decimal
    normalised_score: Decimal
    mean_shift: Decimal
    std_shift: Decimal
    mean_all: Decimal
    std_all: Decimal


# ================================================================== #
# Statistics helpers
# ================================================================== #

def _decimal_mean(values: List[Decimal]) -> Decimal:
    if not values:
        raise ValueError("Cannot compute mean of empty sequence")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _decimal_population_std_dev(values: List[Decimal], mean: Optional[Decimal] = None) -> Decimal:
    if len(values) < 2:
        return Decimal("0")
    if mean is None:
        mean = _decimal_mean(values)
    variance = sum((v - mean) ** 2 for v in values) / Decimal(len(values))
    # Use Python float sqrt then convert back to Decimal (acceptable precision)
    return Decimal(str(math.sqrt(float(variance))))


# ================================================================== #
# Normalisation Engine
# ================================================================== #

class NormalisationEngine:
    """
    Implements PS-072 shift normalisation.
    All intermediate values are stored as high-precision Decimals.
    """

    def __init__(self, min_shift_size: int = 100):
        self.min_shift_size = min_shift_size

    # -------------------------------------------------------------- #
    # Step 1: Compute per-shift statistics
    # -------------------------------------------------------------- #

    def compute_shift_statistics(
        self, shift_data: ShiftRawData
    ) -> ShiftStatisticsComputed:
        scores = list(shift_data.candidate_scores.values())
        mean = _decimal_mean(scores)
        std_dev = _decimal_population_std_dev(scores, mean)
        return ShiftStatisticsComputed(
            shift_id=shift_data.shift_id,
            candidate_count=len(scores),
            mean=mean,
            std_dev=std_dev,
        )

    # -------------------------------------------------------------- #
    # Step 2: Determine which shifts need pooling
    # -------------------------------------------------------------- #

    def identify_pooled_shifts(
        self, all_shift_data: List[ShiftRawData]
    ) -> Tuple[List[int], List[int]]:
        """
        Returns (pooled_shift_ids, standalone_shift_ids).
        Shifts with candidate_count < min_shift_size are pooled together.
        """
        pooled = [s.shift_id for s in all_shift_data if len(s.candidate_scores) < self.min_shift_size]
        standalone = [s.shift_id for s in all_shift_data if len(s.candidate_scores) >= self.min_shift_size]
        return pooled, standalone

    # -------------------------------------------------------------- #
    # Step 3: Compute "all-shifts" / pooled statistics
    # -------------------------------------------------------------- #

    def compute_overall_statistics(
        self, all_shift_data: List[ShiftRawData]
    ) -> Tuple[Decimal, Decimal]:
        """
        Returns (mean_all, std_all) across all candidates in all supplied shifts.
        Used as the target distribution.
        """
        all_scores: List[Decimal] = []
        for sd in all_shift_data:
            all_scores.extend(sd.candidate_scores.values())
        mean_all = _decimal_mean(all_scores)
        std_all = _decimal_population_std_dev(all_scores, mean_all)
        return mean_all, std_all

    # -------------------------------------------------------------- #
    # Step 4: Normalise a single candidate's score
    # -------------------------------------------------------------- #

    def normalise_score(
        self,
        raw_score: Decimal,
        mean_shift: Decimal,
        std_shift: Decimal,
        mean_all: Decimal,
        std_all: Decimal,
    ) -> Decimal:
        """
        Apply the PS-072 normalisation formula.

        normalised = mean_all + (std_all / std_shift) * (raw_score - mean_shift)

        Rule 7: If std_shift <= 0, raise NormalisationDenominatorError.
        """
        if std_shift <= Decimal("0"):
            raise NormalisationDenominatorError(
                f"std_shift={std_shift} is <= 0. "
                "Cannot normalise. Record this as a decision-log item and handle "
                "per the approved guard rule (do not silently assign raw score)."
            )

        normalised = mean_all + (std_all / std_shift) * (raw_score - mean_shift)
        return normalised

    # -------------------------------------------------------------- #
    # Step 5: Full batch normalisation
    # -------------------------------------------------------------- #

    def normalise_all(
        self, all_shift_data: List[ShiftRawData]
    ) -> List[NormalisationOutput]:
        """
        Normalise all candidates across all shifts.
        Handles small-shift pooling automatically.
        """
        # Identify pooled vs standalone shifts
        pooled_ids, standalone_ids = self.identify_pooled_shifts(all_shift_data)
        pooled_set: Set[int] = set(pooled_ids)

        # Build lookup by shift_id
        shift_map: Dict[int, ShiftRawData] = {s.shift_id: s for s in all_shift_data}

        # Compute per-shift statistics for standalone shifts
        shift_stats: Dict[int, ShiftStatisticsComputed] = {}
        for sid in standalone_ids:
            shift_stats[sid] = self.compute_shift_statistics(shift_map[sid])

        # Compute pooled statistics
        pooled_data: Optional[ShiftStatisticsComputed] = None
        if pooled_ids:
            pooled_shift_data = [shift_map[pid] for pid in pooled_ids]
            all_pooled_scores: List[Decimal] = []
            for sd in pooled_shift_data:
                all_pooled_scores.extend(sd.candidate_scores.values())
            pooled_mean = _decimal_mean(all_pooled_scores)
            pooled_std = _decimal_population_std_dev(all_pooled_scores, pooled_mean)
            pooled_data = ShiftStatisticsComputed(
                shift_id=-1,  # sentinel
                candidate_count=len(all_pooled_scores),
                mean=pooled_mean,
                std_dev=pooled_std,
            )

        # Overall statistics (target distribution)
        mean_all, std_all = self.compute_overall_statistics(all_shift_data)

        outputs: List[NormalisationOutput] = []

        for shift_data in all_shift_data:
            sid = shift_data.shift_id
            if sid in pooled_set:
                if pooled_data is None:
                    continue
                mean_shift = pooled_data.mean
                std_shift = pooled_data.std_dev
            else:
                ss = shift_stats[sid]
                mean_shift = ss.mean
                std_shift = ss.std_dev

            for candidate_id, raw_score in shift_data.candidate_scores.items():
                try:
                    norm = self.normalise_score(
                        raw_score, mean_shift, std_shift, mean_all, std_all
                    )
                except NormalisationDenominatorError:
                    logger.error(
                        "Normalisation denominator error for shift %s. "
                        "Recording DL-005. Candidate %s raw score preserved.",
                        sid,
                        candidate_id,
                    )
                    raise  # Caller must handle per approved guard rule

                outputs.append(
                    NormalisationOutput(
                        candidate_id=candidate_id,
                        shift_id=sid,
                        raw_score=raw_score,
                        normalised_score=norm,
                        mean_shift=mean_shift,
                        std_shift=std_shift,
                        mean_all=mean_all,
                        std_all=std_all,
                    )
                )

        return outputs

    # -------------------------------------------------------------- #
    # Precision formatting helpers (Rule 12)
    # -------------------------------------------------------------- #

    @staticmethod
    def format_normalised(value: Decimal) -> str:
        """Display to 5 decimal places (Rule 12). Do NOT use for comparisons."""
        return str(value.quantize(PRECISION_NORMALISED, rounding=ROUND_HALF_UP))

    @staticmethod
    def format_raw(value: Decimal) -> str:
        """Display to 2 decimal places (Rule 12). Do NOT use for comparisons."""
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
