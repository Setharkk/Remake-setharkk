"""Regression checks for numerical errors and the experiment protocol."""
import contextlib
import csv
import errno
import io
import json
import math
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from cortex_lab_v0.core import (
    DTYPE, Ensemble, curved_step, exp_origin, log_origin,
    lorentz_dot, mixture_log_likelihood,
)
from cortex_lab_v0.file_lab import ACTION_NAMES, FileLab, collect_cases
from cortex_lab_v0.run import make_warmup, run_condition, split_cases

torch.set_num_threads(1)


class NumericalRegressionTests(unittest.TestCase):
    def test_origin_is_exact(self):
        q = torch.zeros((2, 4), dtype=DTYPE)
        expected = torch.zeros((2, 5), dtype=DTYPE)
        expected[:, 0] = 1
        torch.testing.assert_close(exp_origin(q), expected, atol=0, rtol=0)
        torch.testing.assert_close(log_origin(expected), q, atol=0, rtol=0)

    def test_zero_steps_do_not_accumulate_drift(self):
        original = exp_origin(torch.tensor([[.2, -.3, .1, .4]], dtype=DTYPE))
        point = original.clone()
        for _ in range(2048):
            point = curved_step(point, torch.zeros((1, 4), dtype=DTYPE))
        torch.testing.assert_close(point, original, atol=0, rtol=0)

    def test_small_vector_derivatives(self):
        q = torch.tensor([
            [1e-12, -1e-12, 0., 0.],
            [1e-4, -2e-4, 0., 3e-4],
            [1e-3, 0., 0., 0.],
        ], dtype=DTYPE, requires_grad=True)
        w = torch.tensor([
            [0., 0., 1e-12, 0.],
            [2e-4, 0., -1e-4, 0.],
            [-1e-3, 0., 0., 0.],
        ], dtype=DTYPE, requires_grad=True)
        self.assertTrue(torch.autograd.gradcheck(
            lambda x, y: log_origin(curved_step(exp_origin(x), y)),
            (q, w), eps=1e-7, atol=1e-7, rtol=1e-5
        ))

    def test_geometry_over_the_model_range(self):
        rng = torch.Generator().manual_seed(19)
        q = (torch.rand((100, 4), generator=rng, dtype=DTYPE) * 2 - 1) * .8
        w = (torch.rand((100, 4), generator=rng, dtype=DTYPE) * 2 - 1) * .4
        for point in (exp_origin(q), curved_step(exp_origin(q), w)):
            torch.testing.assert_close(
                lorentz_dot(point, point), -torch.ones(100, dtype=DTYPE),
                atol=1e-12, rtol=0
            )
        torch.testing.assert_close(log_origin(exp_origin(q)), q, atol=1e-12, rtol=0)

    def test_extreme_wrong_predictions_are_not_capped(self):
        logits = torch.full((1, 2, 4), -1000., dtype=DTYPE)
        targets = torch.ones((2, 4), dtype=DTYPE)
        torch.testing.assert_close(
            -mixture_log_likelihood(logits, targets),
            torch.full((2,), 4000., dtype=DTYPE), atol=1e-10, rtol=0
        )

    def test_likelihood_mixes_joint_distributions(self):
        logits = torch.tensor([
            [[math.log(9)] * 4],
            [[-math.log(9)] * 4],
        ], dtype=DTYPE)
        targets = torch.ones((1, 4), dtype=DTYPE)
        expected = math.log((.9 ** 4 + .1 ** 4) / 2)
        self.assertAlmostEqual(
            float(mixture_log_likelihood(logits, targets)[0]), expected, places=12
        )

    def test_evaluation_uses_stable_joint_likelihood(self):
        learner = Ensemble("hyperbolic", seed=0, members=2)
        with torch.no_grad():
            for model, bias in zip(learner.models, (-100., -1000.)):
                model.decoder.weight.zero_()
                model.decoder.bias.fill_(bias)
        cases = [{"state": [0, 0, 0], "action": 0, "result": [1, 1, 1, 1]}]
        metrics = learner.evaluate(cases)
        self.assertAlmostEqual(metrics["nll"], 400 + math.log(2), places=10)
        self.assertAlmostEqual(metrics["brier"], 1, places=12)


class ProtocolRegressionTests(unittest.TestCase):
    def test_unexpected_os_failures_do_not_become_training_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            lab = FileLab(Path(temporary) / "files")
            for error in (PermissionError("denied"), OSError(errno.EIO, "I/O error")):
                with self.subTest(error=type(error).__name__):
                    with patch.object(Path, "rename", side_effect=error):
                        with self.assertRaises(type(error)):
                            lab.execute([1, 0, 0], 1)

    def test_shared_warmup_covers_distinct_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            cases = collect_cases(FileLab(Path(temporary) / "fixtures"))
            for seed in range(10):
                train, _ = split_cases(cases, seed)
                indices = make_warmup(train, seed)
                self.assertEqual(indices, make_warmup(train, seed))
                self.assertEqual(len(set(indices)), 8)
                self.assertEqual(
                    [train[index]["action"] for index in indices], [0, 1, 2, 3] * 2
                )

    def test_four_conditions_keep_budgets_and_heldout_pairs_separate(self):
        args = SimpleNamespace(
            steps=10, device="cpu", updates=1, batch_size=4, evaluate_every=4
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = collect_cases(FileLab(root / "fixtures"))
            train, test = split_cases(cases, seed=0)
            train_pairs = {(tuple(c["state"]), c["action"]) for c in train}
            test_pairs = {(tuple(c["state"]), c["action"]) for c in test}
            shared_warmup = None
            for geometry in ("hyperbolic", "euclidean"):
                for exploration in ("active", "random"):
                    with self.subTest(geometry=geometry, exploration=exploration):
                        # Force the active gate so this test exercises that branch.
                        # Native _randbelow still uses getrandbits for selections.
                        with patch.object(random.Random, "random", return_value=.5):
                            with contextlib.redirect_stdout(io.StringIO()):
                                summary = run_condition(
                                    root, geometry, exploration, 0, train, test, args
                                )
                        directory = Path(summary["directory"])
                        records = [
                            json.loads(line)
                            for line in (directory / "experiences.jsonl").read_text(
                                encoding="utf-8"
                            ).splitlines()
                        ]
                        replay = json.loads(
                            (directory / "replay.json").read_text(encoding="utf-8")
                        )
                        self.assertEqual(len(records), args.steps)
                        self.assertEqual(len(replay), args.steps)
                        self.assertEqual(summary["training_experiments"], args.steps)
                        self.assertEqual(
                            summary["final"]["optimizer_updates"], args.steps * 3
                        )
                        self.assertTrue((directory / "weights.pt").is_file())
                        warmup = [(r["state"], r["action"]) for r in records[:8]]
                        if shared_warmup is None:
                            shared_warmup = warmup
                        self.assertEqual(warmup, shared_warmup)
                        self.assertEqual(len({(tuple(s), a) for s, a in warmup}), 8)
                        for record, experience in zip(records, replay):
                            pair = (
                                tuple(record["state"]), ACTION_NAMES.index(record["action"])
                            )
                            self.assertIn(pair, train_pairs)
                            self.assertNotIn(pair, test_pairs)
                            self.assertEqual(record["result"], experience["result"])
                            self.assertIn("learning_target", record)
                            self.assertNotIn("goal", record)
                            self.assertTrue(all(
                                0 <= p <= 1 for p in record["predicted_before"]
                            ))
                            self.assertGreaterEqual(record["expected_information_gain"], 0)
                            self.assertLessEqual(
                                record["expected_information_gain"], math.log(3) + 1e-10
                            )
                        expected_selection = (
                            "information_gain" if exploration == "active" else "random"
                        )
                        self.assertTrue(all(
                            r["selection"] == expected_selection for r in records[8:]
                        ))
                        with (directory / "metrics.csv").open(
                            encoding="utf-8", newline=""
                        ) as stream:
                            rows = list(csv.DictReader(stream))
                        self.assertEqual([int(r["step"]) for r in rows], [0, 4, 8, 10])
                        for row in rows:
                            self.assertTrue(all(math.isfinite(float(v)) for v in row.values()))


if __name__ == "__main__":
    unittest.main()
