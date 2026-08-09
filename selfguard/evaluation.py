"""Leakage-resistant evaluation utilities for SELFGuard detectors.

Thresholds are selected on validation data and then frozen before test data is
evaluated.  The module intentionally has no scikit-learn dependency so that
deployment teams can audit the metric calculations used in release gates.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class RateInterval:
    """A binomial rate and its Wilson score confidence interval."""

    value: float
    low: float
    high: float
    numerator: int
    denominator: int


@dataclass(frozen=True)
class EvaluationRecord:
    """One labeled detector score.

    ``group_id`` identifies the source task, attack template, document, or
    conversation that must not cross dataset splits.  ``content_hash`` provides
    an additional exact-duplicate check when it is available.
    """

    example_id: str
    label: int
    score: float
    group_id: str
    stratum: str = "default"
    is_hard_negative: bool = False
    content_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.example_id.strip():
            raise ValueError("example_id must be non-empty")
        if self.label not in (0, 1):
            raise ValueError("label must be 0 (clean) or 1 (injected)")
        if not math.isfinite(self.score):
            raise ValueError("score must be finite")
        if not self.group_id.strip():
            raise ValueError("group_id must be non-empty")
        if not self.stratum.strip():
            raise ValueError("stratum must be non-empty")
        if self.is_hard_negative and self.label != 0:
            raise ValueError("hard negatives must have label=0")


@dataclass(frozen=True)
class BinaryMetrics:
    """Thresholded and ranking metrics for a labeled score set."""

    threshold: float
    precision: RateInterval
    recall: RateInterval
    f1: float
    clean_fpr: RateInterval
    specificity: float
    prevalence: float
    predicted_positive_rate: float
    roc_auc: float
    average_precision: float
    tn: int
    fp: int
    fn: int
    tp: int
    precision_at_deployment_prevalence: Optional[float] = None
    conservative_precision_at_deployment_prevalence: Optional[float] = None


@dataclass(frozen=True)
class ThresholdSelection:
    """A validation-selected operating point."""

    threshold: float
    target_clean_fpr: float
    fpr_constraint: str
    validation: BinaryMetrics


@dataclass(frozen=True)
class FixedFPRReport:
    """Validation selection plus untouched-test evaluation."""

    selection: ThresholdSelection
    test: BinaryMetrics
    hard_negatives: Optional[BinaryMetrics]
    strata: Dict[str, BinaryMetrics]
    deployment_attack_prevalence: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return _json_safe(asdict(self))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _validate_confidence(confidence: float) -> float:
    confidence = float(confidence)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return confidence


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> RateInterval:
    """Return a two-sided Wilson interval for a binomial proportion."""

    confidence = _validate_confidence(confidence)
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("Require 0 <= successes <= total")
    if total == 0:
        return RateInterval(math.nan, math.nan, math.nan, successes, total)

    value = successes / total
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (value + z2 / (2.0 * total)) / denominator
    half_width = (
        z
        * math.sqrt(value * (1.0 - value) / total + z2 / (4.0 * total * total))
        / denominator
    )
    return RateInterval(
        value=value,
        low=max(0.0, center - half_width),
        high=min(1.0, center + half_width),
        numerator=successes,
        denominator=total,
    )


def minimum_clean_samples_for_zero_false_positives(
    max_clean_fpr: float,
    confidence: float = 0.95,
) -> int:
    """Return the clean sample size needed to certify an FPR after 0 errors.

    The release evaluator uses the two-sided Wilson interval.  This helper makes
    the corresponding evidence requirement explicit before an expensive model
    run starts.  It does not imply that observing zero false positives is
    likely; it only computes the minimum denominator for which the interval's
    upper bound can meet the requested cap.
    """

    max_clean_fpr = float(max_clean_fpr)
    if not 0.0 < max_clean_fpr < 1.0:
        raise ValueError("max_clean_fpr must be between 0 and 1, exclusive")
    confidence = _validate_confidence(confidence)
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    z2 = z * z
    # For zero successes, the Wilson upper limit simplifies to z^2 / (n + z^2).
    required = math.ceil(z2 * (1.0 - max_clean_fpr) / max_clean_fpr)
    while wilson_interval(0, required, confidence).high > max_clean_fpr:
        required += 1
    return required


def precision_at_prevalence(tpr: float, fpr: float, prevalence: float) -> float:
    """Project precision under a deployment attack prevalence using Bayes' rule."""

    for name, value in (("tpr", tpr), ("fpr", fpr), ("prevalence", prevalence)):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
    numerator = tpr * prevalence
    denominator = numerator + fpr * (1.0 - prevalence)
    return numerator / denominator if denominator else math.nan


def _ranking_metrics(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    positive_count = int(labels.sum())
    negative_count = int(labels.size - positive_count)
    if positive_count == 0 or negative_count == 0:
        roc_auc = math.nan
    else:
        order = np.argsort(scores, kind="mergesort")
        sorted_scores = scores[order]
        ranks = np.empty(labels.size, dtype=float)
        start = 0
        while start < labels.size:
            end = start + 1
            while end < labels.size and sorted_scores[end] == sorted_scores[start]:
                end += 1
            ranks[order[start:end]] = (start + 1 + end) / 2.0
            start = end
        positive_rank_sum = float(ranks[labels == 1].sum())
        roc_auc = (
            positive_rank_sum - positive_count * (positive_count + 1) / 2.0
        ) / (positive_count * negative_count)

    if positive_count == 0:
        average_precision = math.nan
    else:
        descending = np.argsort(-scores, kind="mergesort")
        sorted_labels = labels[descending]
        sorted_scores = scores[descending]
        cumulative_tp = np.cumsum(sorted_labels == 1)
        score_group_ends = np.r_[
            np.flatnonzero(sorted_scores[1:] != sorted_scores[:-1]), labels.size - 1
        ]
        previous_tp = 0
        area = 0.0
        for end in score_group_ends:
            tp_at_threshold = int(cumulative_tp[end])
            positives_added = tp_at_threshold - previous_tp
            precision_at_threshold = tp_at_threshold / (int(end) + 1)
            area += precision_at_threshold * positives_added / positive_count
            previous_tp = tp_at_threshold
        average_precision = float(area)
    return float(roc_auc), float(average_precision)


def binary_metrics(
    labels: Sequence[int],
    scores: Sequence[float],
    threshold: float,
    *,
    confidence: float = 0.95,
    deployment_attack_prevalence: Optional[float] = None,
) -> BinaryMetrics:
    """Calculate detector metrics at a frozen threshold."""

    _validate_confidence(confidence)
    if deployment_attack_prevalence is not None:
        deployment_attack_prevalence = float(deployment_attack_prevalence)
        if not 0.0 <= deployment_attack_prevalence <= 1.0:
            raise ValueError("deployment_attack_prevalence must be between 0 and 1")
    y_true = np.asarray(labels, dtype=int)
    y_score = np.asarray(scores, dtype=float)
    if y_true.ndim != 1 or y_score.ndim != 1 or y_true.size != y_score.size:
        raise ValueError("labels and scores must be same-length one-dimensional arrays")
    if y_true.size == 0:
        raise ValueError("labels and scores must not be empty")
    if not np.all(np.isin(y_true, (0, 1))):
        raise ValueError("labels must contain only 0 and 1")
    if not np.all(np.isfinite(y_score)):
        raise ValueError("scores must be finite")
    if math.isnan(float(threshold)):
        raise ValueError("threshold must not be NaN")

    predicted = y_score >= threshold
    positive = y_true == 1
    negative = ~positive
    tp = int(np.sum(predicted & positive))
    fp = int(np.sum(predicted & negative))
    fn = int(np.sum(~predicted & positive))
    tn = int(np.sum(~predicted & negative))

    precision = wilson_interval(tp, tp + fp, confidence)
    recall = wilson_interval(tp, tp + fn, confidence)
    clean_fpr = wilson_interval(fp, fp + tn, confidence)
    f1_denominator = 2 * tp + fp + fn
    f1 = 2 * tp / f1_denominator if f1_denominator else 0.0
    roc_auc, average_precision = _ranking_metrics(y_true, y_score)

    projected_precision = None
    conservative_projected_precision = None
    if (
        deployment_attack_prevalence is not None
        and math.isfinite(recall.value)
        and math.isfinite(clean_fpr.value)
    ):
        projected_precision = precision_at_prevalence(
            recall.value, clean_fpr.value, float(deployment_attack_prevalence)
        )
        conservative_projected_precision = precision_at_prevalence(
            recall.low, clean_fpr.high, float(deployment_attack_prevalence)
        )

    return BinaryMetrics(
        threshold=float(threshold),
        precision=precision,
        recall=recall,
        f1=float(f1),
        clean_fpr=clean_fpr,
        specificity=1.0 - clean_fpr.value if math.isfinite(clean_fpr.value) else math.nan,
        prevalence=float(np.mean(positive)),
        predicted_positive_rate=float(np.mean(predicted)),
        roc_auc=roc_auc,
        average_precision=average_precision,
        tn=tn,
        fp=fp,
        fn=fn,
        tp=tp,
        precision_at_deployment_prevalence=projected_precision,
        conservative_precision_at_deployment_prevalence=(
            conservative_projected_precision
        ),
    )


def select_threshold_at_fpr(
    labels: Sequence[int],
    scores: Sequence[float],
    max_clean_fpr: float,
    *,
    confidence: float = 0.95,
    fpr_constraint: str = "upper",
) -> ThresholdSelection:
    """Choose the highest-recall validation threshold under a clean-FPR cap.

    Do not call this function on test data.  Ties are resolved by F1, precision,
    and then the stricter threshold, matching the research notebook's intent.
    """

    if not 0.0 <= max_clean_fpr <= 1.0:
        raise ValueError("max_clean_fpr must be between 0 and 1")
    if fpr_constraint not in {"point", "upper"}:
        raise ValueError("fpr_constraint must be 'point' or 'upper'")
    if fpr_constraint == "upper" and max_clean_fpr == 0.0:
        raise ValueError(
            "A confidence-bound FPR target of zero is unattainable with a "
            "finite sample; use a positive target"
        )
    y_true = np.asarray(labels, dtype=int)
    y_score = np.asarray(scores, dtype=float)
    if y_true.size == 0 or y_true.size != y_score.size:
        raise ValueError("labels and scores must be non-empty and the same length")
    if not np.any(y_true == 0) or not np.any(y_true == 1):
        raise ValueError("threshold selection requires both clean and injected examples")
    if not np.all(np.isfinite(y_score)):
        raise ValueError("scores must be finite")

    thresholds = np.unique(np.r_[y_score, np.nextafter(y_score.max(), np.inf)])
    candidates = [
        binary_metrics(y_true, y_score, threshold, confidence=confidence)
        for threshold in thresholds
    ]
    eligible = [
        row
        for row in candidates
        if (
            row.clean_fpr.high
            if fpr_constraint == "upper"
            else row.clean_fpr.value
        )
        <= max_clean_fpr
    ]
    if not eligible:
        if fpr_constraint == "upper":
            clean_count = int(np.sum(y_true == 0))
            required = minimum_clean_samples_for_zero_false_positives(
                max_clean_fpr, confidence
            )
            raise RuntimeError(
                "No validation threshold satisfies the confidence-bound "
                f"clean-FPR constraint: {clean_count} clean examples supplied; "
                f"at least {required} are required even with zero false positives"
            )
        raise RuntimeError(
            "No validation threshold satisfies the clean-FPR constraint; "
            "collect more clean validation examples or relax the target"
        )
    selected = max(
        eligible,
        key=lambda row: (
            row.recall.value,
            row.f1,
            row.precision.value if math.isfinite(row.precision.value) else -1.0,
            row.threshold,
        ),
    )
    return ThresholdSelection(
        threshold=selected.threshold,
        target_clean_fpr=float(max_clean_fpr),
        fpr_constraint=fpr_constraint,
        validation=selected,
    )


def assert_disjoint_splits(
    splits: Mapping[str, Sequence[EvaluationRecord]],
) -> None:
    """Fail when IDs, groups, or available content hashes cross split boundaries."""

    names = list(splits)
    for index, left_name in enumerate(names):
        left = splits[left_name]
        left_ids = {record.example_id for record in left}
        left_groups = {record.group_id for record in left}
        left_hashes = {record.content_hash for record in left if record.content_hash}
        if len(left_ids) != len(left):
            raise ValueError(f"Duplicate example_id within {left_name}")
        for right_name in names[index + 1 :]:
            right = splits[right_name]
            overlaps = {
                "example_id": left_ids & {record.example_id for record in right},
                "group_id": left_groups & {record.group_id for record in right},
                "content_hash": left_hashes
                & {record.content_hash for record in right if record.content_hash},
            }
            violations = {
                field: sorted(values)[:5] for field, values in overlaps.items() if values
            }
            if violations:
                raise ValueError(
                    f"Dataset leakage between {left_name} and {right_name}: {violations}"
                )


def evaluate_fixed_fpr(
    validation: Sequence[EvaluationRecord],
    test: Sequence[EvaluationRecord],
    *,
    max_clean_fpr: float,
    confidence: float = 0.95,
    deployment_attack_prevalence: Optional[float] = None,
    check_disjoint: bool = True,
    fpr_constraint: str = "upper",
) -> FixedFPRReport:
    """Select on validation records and evaluate once on test records."""

    if not validation or not test:
        raise ValueError("validation and test records must not be empty")
    if check_disjoint:
        assert_disjoint_splits({"validation": validation, "test": test})

    selection = select_threshold_at_fpr(
        [record.label for record in validation],
        [record.score for record in validation],
        max_clean_fpr,
        confidence=confidence,
        fpr_constraint=fpr_constraint,
    )
    threshold = selection.threshold

    def metrics(records: Sequence[EvaluationRecord]) -> BinaryMetrics:
        return binary_metrics(
            [record.label for record in records],
            [record.score for record in records],
            threshold,
            confidence=confidence,
            deployment_attack_prevalence=deployment_attack_prevalence,
        )

    hard_negative_records = [record for record in test if record.is_hard_negative]
    strata: Dict[str, BinaryMetrics] = {}
    for stratum in sorted({record.stratum for record in test}):
        stratum_records = [record for record in test if record.stratum == stratum]
        strata[stratum] = metrics(stratum_records)

    return FixedFPRReport(
        selection=selection,
        test=metrics(test),
        hard_negatives=metrics(hard_negative_records) if hard_negative_records else None,
        strata=strata,
        deployment_attack_prevalence=deployment_attack_prevalence,
    )


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"", "0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _record_from_mapping(row: Mapping[str, Any], source: str, line: int) -> EvaluationRecord:
    try:
        return EvaluationRecord(
            example_id=str(row["example_id"]),
            label=int(row["label"]),
            score=float(row["score"]),
            group_id=str(row["group_id"]),
            stratum=str(row.get("stratum") or "default"),
            is_hard_negative=_parse_bool(row.get("is_hard_negative", False)),
            content_hash=str(row["content_hash"]) if row.get("content_hash") else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid record in {source} at row {line}: {exc}") from exc


def load_evaluation_records(path: str | Path) -> List[EvaluationRecord]:
    """Load evaluation scores from CSV or JSON Lines."""

    source = Path(path)
    if source.suffix.casefold() not in {".csv", ".jsonl"}:
        raise ValueError("Evaluation files must use .csv or .jsonl")
    records: List[EvaluationRecord] = []
    with source.open("r", encoding="utf-8", newline="") as handle:
        if source.suffix.casefold() == ".csv":
            for line, row in enumerate(csv.DictReader(handle), start=2):
                records.append(_record_from_mapping(row, str(source), line))
        else:
            for line, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in {source} at row {line}: {exc.msg}"
                    ) from exc
                if not isinstance(row, dict):
                    raise ValueError(f"Expected an object in {source} at row {line}")
                records.append(_record_from_mapping(row, str(source), line))
    if not records:
        raise ValueError(f"No evaluation records found in {source}")
    return records


def records_to_dicts(records: Iterable[EvaluationRecord]) -> List[Dict[str, Any]]:
    """Return JSON-serializable record dictionaries."""

    return [asdict(record) for record in records]
