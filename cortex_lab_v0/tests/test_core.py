import tempfile
import unittest
from pathlib import Path

import torch

from cortex_lab_v0.core import (
    DTYPE, Ensemble, TransitionModel, curved_step, exp_origin,
    information_gain, log_origin, lorentz_dot, transport_from_origin,
)
from cortex_lab_v0.file_lab import FileLab, collect_cases
from cortex_lab_v0.run import split_cases

torch.set_num_threads(1)


class GeometryTests(unittest.TestCase):
    def test_inverse_norm_and_transport(self):
        q = torch.tensor([[0., 0., 0., 0.], [.2, -.3, .1, .4]], dtype=DTYPE)
        w = torch.tensor([[0., 0., 0., 0.], [-.1, .2, .3, -.2]], dtype=DTYPE)
        z = exp_origin(q)
        v = transport_from_origin(z, w)
        following = curved_step(z, w)
        torch.testing.assert_close(log_origin(z), q, atol=1e-8, rtol=1e-8)
        for point in (z, following):
            torch.testing.assert_close(
                lorentz_dot(point, point), -torch.ones(2, dtype=DTYPE),
                atol=1e-8, rtol=1e-8
            )
            self.assertTrue(bool((point[:, 0] > 0).all()))
        torch.testing.assert_close(
            lorentz_dot(z, v), torch.zeros(2, dtype=DTYPE),
            atol=1e-8, rtol=1e-8
        )
        torch.testing.assert_close(
            lorentz_dot(v, v), w.square().sum(-1), atol=1e-8, rtol=1e-8
        )
        torch.testing.assert_close(
            curved_step(z, torch.zeros_like(w)), z, atol=1e-8, rtol=1e-8
        )

    def test_derivatives_including_origin(self):
        q = torch.tensor(
            [[0., 0., 0., 0.], [.2, -.1, .3, .1]],
            dtype=DTYPE, requires_grad=True
        )
        w = torch.tensor(
            [[0., 0., 0., 0.], [.1, .2, -.1, .05]],
            dtype=DTYPE, requires_grad=True
        )
        self.assertTrue(torch.autograd.gradcheck(
            lambda x, y: log_origin(curved_step(exp_origin(x), y)),
            (q, w), eps=1e-6, atol=1e-5, rtol=1e-4
        ))

    def test_parameter_budget_matches(self):
        counts = [
            sum(p.numel() for p in TransitionModel(g).parameters())
            for g in ("hyperbolic", "euclidean")
        ]
        self.assertEqual(counts, [72, 72])


class InformationTests(unittest.TestCase):
    def test_agreement_is_not_information(self):
        noisy_but_agreed = torch.full((3, 2, 4), 0.5, dtype=DTYPE)
        torch.testing.assert_close(
            information_gain(noisy_but_agreed), torch.zeros(2, dtype=DTYPE),
            atol=1e-10, rtol=1e-10
        )
        disagreement = noisy_but_agreed.clone()
        disagreement[0] = 0.1
        disagreement[2] = 0.9
        self.assertTrue(bool((information_gain(disagreement) > 0.1).all()))


class LearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.cases = collect_cases(FileLab(Path(cls.temporary.name) / "files"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_real_file_operations(self):
        for case in self.cases:
            source, destination, alias = case["state"]
            action = case["action"]
            expected = list(case["state"])
            if action == 0:
                success = 1 - source
                if success:
                    expected[0] = 1
            elif action == 1:
                success = int(source and not destination)
                if success:
                    expected[0], expected[1] = 0, 1
            elif action == 2:
                success = int(source and not alias)
                if success:
                    expected[0], expected[2] = 0, 1
            else:
                success = source
            self.assertEqual(case["result"], expected + [success])

    def test_split_is_disjoint_and_balanced(self):
        train, test = split_cases(self.cases, seed=7)
        train_pairs = {(tuple(c["state"]), c["action"]) for c in train}
        test_pairs = {(tuple(c["state"]), c["action"]) for c in test}
        self.assertEqual((len(train), len(test)), (24, 8))
        self.assertFalse(train_pairs & test_pairs)
        self.assertTrue(all("result" not in entry for entry in train))
        for action in range(4):
            self.assertEqual(
                sorted(c["result"][-1] for c in test if c["action"] == action),
                [0, 1]
            )

    def test_updates_improve_predictions_and_survive_save(self):
        # This checks the learning mechanism on its training data.
        # Generalization is measured separately by run.py on held-out pairs.
        for geometry in ("hyperbolic", "euclidean"):
            with self.subTest(geometry=geometry):
                learner = Ensemble(geometry, seed=7, members=1)
                before = learner.evaluate(self.cases)
                for case in self.cases:
                    learner.observe(case["state"], case["action"], case["result"])
                learner.learn(updates=100, batch_size=32)
                after = learner.evaluate(self.cases)
                self.assertLess(after["nll"], before["nll"] * 0.7)
                self.assertLess(after["brier"], before["brier"] - 0.02)
                self.assertGreater(after["weights_changed_l2"], 1e-5)
                self.assertGreater(after["gradient_norm"], 0)
                expected = learner.predict(self.cases)
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "weights.pt"
                    torch.save(learner.checkpoint(), path)
                    checkpoint = torch.load(path, weights_only=True)
                    restored = Ensemble(geometry, seed=999, members=1)
                    restored.models[0].load_state_dict(checkpoint[0])
                    torch.testing.assert_close(restored.predict(self.cases), expected)


if __name__ == "__main__":
    unittest.main()
