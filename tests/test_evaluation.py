import json
import math
import tempfile
import unittest
from pathlib import Path

from selfguard import (
    EvaluationRecord,
    assert_disjoint_splits,
    binary_metrics,
    evaluate_fixed_fpr,
    load_evaluation_records,
    minimum_clean_samples_for_zero_false_positives,
    precision_at_prevalence,
    select_threshold_at_fpr,
    wilson_interval,
)
from selfguard.evaluation_cli import main as evaluation_main


def record(example_id, label, score, group_id, **kwargs):
    return EvaluationRecord(example_id, label, score, group_id, **kwargs)


class MetricTests(unittest.TestCase):
    def test_binary_metrics_and_ranking_metrics(self):
        metrics = binary_metrics(
            [0, 0, 1, 1],
            [0.1, 0.8, 0.7, 0.9],
            0.75,
            deployment_attack_prevalence=0.01,
        )
        self.assertEqual((metrics.tn, metrics.fp, metrics.fn, metrics.tp), (1, 1, 1, 1))
        self.assertEqual(metrics.precision.value, 0.5)
        self.assertEqual(metrics.recall.value, 0.5)
        self.assertEqual(metrics.f1, 0.5)
        self.assertAlmostEqual(metrics.roc_auc, 0.75)
        self.assertAlmostEqual(metrics.average_precision, 5 / 6)
        self.assertAlmostEqual(
            metrics.precision_at_deployment_prevalence,
            precision_at_prevalence(0.5, 0.5, 0.01),
        )
        self.assertAlmostEqual(
            metrics.conservative_precision_at_deployment_prevalence,
            precision_at_prevalence(
                metrics.recall.low, metrics.clean_fpr.high, 0.01
            ),
        )

    def test_average_precision_handles_score_ties_as_one_threshold(self):
        metrics = binary_metrics([1, 0], [0.5, 0.5], 0.5)
        self.assertAlmostEqual(metrics.roc_auc, 0.5)
        self.assertAlmostEqual(metrics.average_precision, 0.5)

    def test_wilson_interval_exposes_uncertainty_at_zero_false_positives(self):
        interval = wilson_interval(0, 300)
        self.assertEqual(interval.value, 0.0)
        self.assertGreater(interval.high, 0.0)
        self.assertLess(interval.high, 0.02)

    def test_projected_precision_rejects_invalid_rates(self):
        with self.assertRaises(ValueError):
            precision_at_prevalence(0.8, 0.1, 1.1)

    def test_minimum_clean_sample_requirement_matches_wilson_gate(self):
        self.assertEqual(minimum_clean_samples_for_zero_false_positives(0.05), 73)
        self.assertEqual(minimum_clean_samples_for_zero_false_positives(0.01), 381)
        self.assertLessEqual(wilson_interval(0, 381).high, 0.01)
        self.assertGreater(wilson_interval(0, 380).high, 0.01)


class ThresholdTests(unittest.TestCase):
    def test_selects_highest_recall_under_clean_fpr_cap(self):
        selection = select_threshold_at_fpr(
            [0, 0, 0, 0, 1, 1],
            [0.1, 0.2, 0.3, 0.9, 0.35, 0.8],
            max_clean_fpr=0.25,
            fpr_constraint="point",
        )
        self.assertEqual(selection.threshold, 0.35)
        self.assertEqual(selection.validation.clean_fpr.value, 0.25)
        self.assertEqual(selection.validation.recall.value, 1.0)

    def test_zero_fpr_threshold_accounts_for_tied_clean_scores(self):
        selection = select_threshold_at_fpr(
            [0, 0, 1, 1],
            [0.5, 0.5, 0.5, 0.9],
            max_clean_fpr=0.0,
            fpr_constraint="point",
        )
        self.assertEqual(selection.threshold, 0.9)
        self.assertEqual(selection.validation.clean_fpr.value, 0.0)
        self.assertEqual(selection.validation.recall.value, 0.5)

    def test_defaults_to_fpr_confidence_upper_bound(self):
        selection = select_threshold_at_fpr(
            [0] * 100 + [1, 1],
            [0.1] * 100 + [0.8, 0.9],
            max_clean_fpr=0.05,
        )
        self.assertEqual(selection.fpr_constraint, "upper")
        self.assertLessEqual(selection.validation.clean_fpr.high, 0.05)

    def test_upper_bound_gate_reports_insufficient_clean_sample_size(self):
        with self.assertRaisesRegex(RuntimeError, "at least 381"):
            select_threshold_at_fpr(
                [0] * 10 + [1],
                [0.1] * 10 + [0.9],
                max_clean_fpr=0.01,
                fpr_constraint="upper",
            )


class LeakageAndReportTests(unittest.TestCase):
    def test_rejects_groups_crossing_splits(self):
        validation = [record("v1", 0, 0.1, "shared")]
        test = [record("t1", 1, 0.9, "shared")]
        with self.assertRaisesRegex(ValueError, "Dataset leakage"):
            assert_disjoint_splits({"validation": validation, "test": test})

    def test_rejects_content_hashes_crossing_splits(self):
        validation = [record("v1", 0, 0.1, "v", content_hash="same")]
        test = [record("t1", 1, 0.9, "t", content_hash="same")]
        with self.assertRaisesRegex(ValueError, "content_hash"):
            assert_disjoint_splits({"validation": validation, "test": test})

    def test_fixed_fpr_report_includes_hard_negative_and_stratum_metrics(self):
        validation = [
            record("v0", 0, 0.1, "vg0"),
            record("v1", 0, 0.2, "vg1"),
            record("v2", 1, 0.8, "vg2"),
            record("v3", 1, 0.9, "vg3"),
        ]
        test = [
            record(
                "t0",
                0,
                0.85,
                "tg0",
                stratum="quoted_security_text",
                is_hard_negative=True,
            ),
            record("t1", 0, 0.1, "tg1", stratum="ordinary_clean"),
            record("t2", 1, 0.95, "tg2", stratum="direct_injection"),
            record("t3", 1, 0.7, "tg3", stratum="indirect_injection"),
        ]
        report = evaluate_fixed_fpr(
            validation,
            test,
            max_clean_fpr=0.0,
            fpr_constraint="point",
            deployment_attack_prevalence=0.01,
        )
        self.assertIsNotNone(report.hard_negatives)
        self.assertEqual(report.hard_negatives.clean_fpr.value, 1.0)
        self.assertEqual(set(report.strata), {
            "direct_injection",
            "indirect_injection",
            "ordinary_clean",
            "quoted_security_text",
        })
        serialized = report.to_dict()
        self.assertIsNone(serialized["hard_negatives"]["recall"]["value"])
        json.dumps(serialized, allow_nan=False)

    def test_loader_supports_jsonl_and_validates_hard_negatives(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scores.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "example_id": "one",
                        "label": 0,
                        "score": 0.2,
                        "group_id": "group-one",
                        "is_hard_negative": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            records = load_evaluation_records(path)
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].is_hard_negative)

            path.write_text(
                '{"example_id":"bad","label":1,"score":0.9,'
                '"group_id":"g","is_hard_negative":true}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hard negatives"):
                load_evaluation_records(path)

    def test_cli_writes_strict_json_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validation_path = root / "validation.jsonl"
            test_path = root / "test.jsonl"
            output_path = root / "report.json"

            def write_records(path, rows):
                path.write_text(
                    "".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8",
                )

            write_records(
                validation_path,
                [
                    {"example_id": "v0", "label": 0, "score": 0.1, "group_id": "vg0"},
                    {"example_id": "v1", "label": 0, "score": 0.2, "group_id": "vg1"},
                    {"example_id": "v2", "label": 1, "score": 0.8, "group_id": "vg2"},
                ],
            )
            write_records(
                test_path,
                [
                    {"example_id": "t0", "label": 0, "score": 0.1, "group_id": "tg0"},
                    {"example_id": "t1", "label": 1, "score": 0.9, "group_id": "tg1"},
                ],
            )
            evaluation_main(
                [
                    "--validation",
                    str(validation_path),
                    "--test",
                    str(test_path),
                    "--max-clean-fpr",
                    "0",
                    "--fpr-constraint",
                    "point",
                    "--output",
                    str(output_path),
                ]
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["test"]["tp"], 1)
            self.assertEqual(report["test"]["fp"], 0)


if __name__ == "__main__":
    unittest.main()
