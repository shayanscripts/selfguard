"""Command-line interface for fixed-FPR detector evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .evaluation import (
    assert_disjoint_splits,
    evaluate_fixed_fpr,
    load_evaluation_records,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select a detector threshold on validation scores, freeze it, and "
            "evaluate test scores with leakage and hard-negative checks."
        )
    )
    parser.add_argument("--validation", required=True, help="Validation CSV or JSONL")
    parser.add_argument("--test", required=True, help="Untouched test CSV or JSONL")
    parser.add_argument(
        "--train",
        help="Optional train CSV or JSONL used only for cross-split leakage checks",
    )
    parser.add_argument(
        "--max-clean-fpr",
        required=True,
        type=float,
        help="Maximum clean FPR allowed on validation data",
    )
    parser.add_argument(
        "--fpr-constraint",
        choices=("point", "upper"),
        default="upper",
        help=(
            "Constrain the empirical point estimate or its confidence-interval "
            "upper bound; defaults to the production-safe 'upper' gate"
        ),
    )
    parser.add_argument(
        "--deployment-attack-prevalence",
        type=float,
        help="Optional expected attack prevalence used to project precision",
    )
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--output", help="Optional path for the JSON report")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    validation = load_evaluation_records(args.validation)
    test = load_evaluation_records(args.test)
    splits = {"validation": validation, "test": test}
    if args.train:
        splits["train"] = load_evaluation_records(args.train)
    assert_disjoint_splits(splits)

    report = evaluate_fixed_fpr(
        validation,
        test,
        max_clean_fpr=args.max_clean_fpr,
        confidence=args.confidence,
        deployment_attack_prevalence=args.deployment_attack_prevalence,
        check_disjoint=False,
        fpr_constraint=args.fpr_constraint,
    )
    rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
