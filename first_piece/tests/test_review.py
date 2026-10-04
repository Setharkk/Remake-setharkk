import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from first_piece import audit
from first_piece.criterion import evaluate_distinction
from first_piece.world import HistoryWorld


class NumericEvidenceTests(unittest.TestCase):
    def test_wrong_endpoint_predictions_have_finite_clipped_scores(self):
        outcomes = [i % 2 for i in range(100)]
        result = evaluate_distinction(
            [.5] * 100, [1 - y for y in outcomes], outcomes, outcomes, epsilon=1e-20
        )
        self.assertTrue(math.isfinite(result["mean_log_score_gain"]))
        self.assertAlmostEqual(result["mean_log_score_gain"], math.log(1e-20 / .5))

    def test_extreme_finite_settings_do_not_overflow_the_bound(self):
        outcomes = [i % 2 for i in range(100)]
        for settings in ({"alpha": 1e-310}, {"epsilon": 1e-310},
                         {"comparison_limit": 10**400}):
            with self.subTest(settings=settings):
                result = evaluate_distinction([.5] * 100, [.5] * 100, outcomes, outcomes, **settings)
                self.assertTrue(math.isfinite(result["uncertainty_bound"]))
                self.assertEqual(result["decision"], "pending_evidence")

    def test_unrepresentable_cost_is_rejected(self):
        outcomes = [i % 2 for i in range(100)]
        for settings in ({"penalty": 1e308, "extra_units": 2},
                         {"extra_units": 10**400}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                evaluate_distinction([.5] * 100, [.5] * 100, outcomes, outcomes, **settings)

    def test_two_tail_union_bound_respects_the_total_risk_budget(self):
        n, comparisons, alpha, epsilon = 1000, 1000, .05, .01
        outcomes = [i % 2 for i in range(n)]
        result = evaluate_distinction([.5] * n, [.5] * n, outcomes, outcomes)
        width = math.log(1 / epsilon)
        # Hoeffding bounds each tail of a variable in [-width, width].
        each_tail = math.exp(-n * result["uncertainty_bound"]**2 / (2 * width**2))
        self.assertLessEqual(2 * comparisons * each_tail, alpha * (1 + 1e-12))


class AuditDurabilityTests(unittest.TestCase):
    def test_completed_progress_matches_metrics_and_world_state(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result = audit.audit_condition(0, "acquisition", False, [100, 200], directory)
            progress = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
            state = json.loads((directory / "world_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["status"], "completed")
            self.assertEqual(progress["checkpoint_interactions"], 200)
            self.assertEqual(progress["checkpoints"], result["checkpoints"])
            self.assertEqual(progress["world_checkpoint"], state)
            self.assertEqual(HistoryWorld.restore(state).completed, 200)

    def test_interruption_keeps_the_last_evaluated_horizon(self):
        class InterruptedWorld(HistoryWorld):
            def act(self, action):
                if self.completed == 125:
                    raise RuntimeError("Injected interruption after interaction 125")
                return super().act(action)

        for noise in (False, True):
            with self.subTest(noise=noise), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                with patch.object(audit, "HistoryWorld", InterruptedWorld):
                    with self.assertRaisesRegex(RuntimeError, "Injected interruption"):
                        audit.audit_condition(0, "acquisition", noise, [100, 200], directory)
                progress = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
                self.assertEqual(progress["status"], "interrupted")
                self.assertEqual(progress["error_type"], "RuntimeError")
                self.assertEqual(progress["checkpoint_interactions"], 100)
                self.assertEqual([c["interactions"] for c in progress["checkpoints"]], [100])
                self.assertEqual(HistoryWorld.restore(progress["world_checkpoint"]).completed, 100)
                self.assertEqual(len((directory / "observations.jsonl").read_text().splitlines()), 125)
                self.assertFalse((directory / "world_checkpoint.json").exists())


if __name__ == "__main__":
    unittest.main()
