"""Second-review regressions for snapshot isolation and run interruptions."""
import contextlib
import csv
import errno
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from cortex_lab_v0.core import Ensemble
from cortex_lab_v0.file_lab import FileLab, collect_cases
from cortex_lab_v0.run import run_condition, split_cases

torch.set_num_threads(1)


class SnapshotTests(unittest.TestCase):
    def test_checkpoint_stays_at_the_captured_training_step(self):
        learner = Ensemble("hyperbolic", seed=1, members=1)
        checkpoint = learner.checkpoint()
        expected = {
            name: value.clone() for name, value in checkpoint[0].items()
        }
        learner.observe([0, 0, 0], 0, [1, 0, 0, 1])
        learner.learn(updates=3, batch_size=4)
        current = learner.models[0].state_dict()
        self.assertTrue(any(
            not torch.equal(current[name], value)
            for name, value in expected.items()
        ))
        for name, value in expected.items():
            torch.testing.assert_close(checkpoint[0][name], value, atol=0, rtol=0)

    def test_editing_checkpoint_does_not_modify_the_running_model(self):
        learner = Ensemble("euclidean", seed=2, members=1)
        candidates = [{"state": [0, 0, 0], "action": 0}]
        expected = learner.predict(candidates).clone()
        checkpoint = learner.checkpoint()
        checkpoint[0]["decoder.bias"].add_(5)
        torch.testing.assert_close(
            learner.predict(candidates), expected, atol=0, rtol=0
        )


class InitializationTests(unittest.TestCase):
    def test_cpu_initialization_preserves_global_rngs(self):
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(731)
            expected_cpu_state = torch.random.get_rng_state().clone()
            # CUDA can be seeded lazily even in a CPU-only process.
            # Observe that boundary without requiring a GPU on the runner.
            with patch.object(torch.cuda, "manual_seed_all") as cuda_seed:
                curved = Ensemble("hyperbolic", seed=11, members=2)
                flat = Ensemble("euclidean", seed=11, members=2)
            torch.testing.assert_close(
                torch.random.get_rng_state(), expected_cpu_state, atol=0, rtol=0
            )
            cuda_seed.assert_not_called()
            for curved_model, flat_model in zip(curved.models, flat.models):
                for name, value in curved_model.state_dict().items():
                    torch.testing.assert_close(
                        flat_model.state_dict()[name], value, atol=0, rtol=0
                    )


class InterruptedRunTests(unittest.TestCase):
    def test_evaluated_metrics_survive_a_later_filesystem_error(self):
        args = SimpleNamespace(
            steps=6, device="cpu", updates=1, batch_size=4, evaluate_every=2
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = collect_cases(FileLab(root / "fixtures"))
            train, test = split_cases(cases, seed=0)
            actual_execute = FileLab.execute

            def execute_with_fault(lab, state, action):
                if lab.count == 4:
                    raise OSError(errno.EIO, "injected failure after four experiments")
                return actual_execute(lab, state, action)

            with patch.object(FileLab, "execute", new=execute_with_fault):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(OSError) as raised:
                        run_condition(
                            root, "hyperbolic", "random", 0, train, test, args
                        )
            self.assertEqual(raised.exception.errno, errno.EIO)
            directory = root / "seed_0" / "hyperbolic_random"
            records = [
                json.loads(line)
                for line in (directory / "experiences.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual([r["step"] for r in records], [1, 2, 3, 4])
            with (directory / "metrics.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                metrics = list(csv.DictReader(stream))
            self.assertEqual([int(row["step"]) for row in metrics], [0, 2, 4])
            self.assertEqual(
                [int(row["optimizer_updates"]) for row in metrics], [0, 6, 12]
            )


if __name__ == "__main__":
    unittest.main()
