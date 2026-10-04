import math
import tempfile
import unittest
from pathlib import Path

import torch
from torch import nn

from cortex_lab_v0.file_lab import FileLab, collect_cases
from cortex_lab_v1.geometry import (
    DTYPE, centroid, exp_origin, lorentz_dot, parallel_transport,
    squared_distance, tangent_projection,
)
from cortex_lab_v1.learner import IntrinsicEnsemble
from cortex_lab_v1.network import IntrinsicNetwork
from cortex_lab_v1.optimizer import RiemannianAdam

torch.set_num_threads(1)


def boost(rapidity=.3):
    matrix = torch.eye(5, dtype=DTYPE)
    matrix[0, 0] = matrix[1, 1] = math.cosh(rapidity)
    matrix[0, 1] = matrix[1, 0] = math.sinh(rapidity)
    return matrix


def assert_points(test, points):
    test.assertTrue(bool(torch.isfinite(points).all()))
    test.assertTrue(bool((points[..., 0] > 0).all()))
    torch.testing.assert_close(
        lorentz_dot(points, points), -torch.ones_like(points[..., 0]),
        atol=1e-9, rtol=0
    )


class GeometryTests(unittest.TestCase):
    def test_centroid_and_transport_are_geometric(self):
        points = exp_origin(torch.tensor([[.2, -.1, .3, .1], [-.3, .2, .1, .2]], dtype=DTYPE))
        average = centroid(points)
        assert_points(self, average)
        transform = boost()
        torch.testing.assert_close(
            centroid(points @ transform.T), average @ transform.T, atol=1e-11, rtol=1e-11
        )
        vector = tangent_projection(points[0], torch.tensor([0., .1, .2, -.1, .3], dtype=DTYPE))
        moved = parallel_transport(points[0], points[1], vector)
        torch.testing.assert_close(lorentz_dot(points[1], moved), torch.zeros((), dtype=DTYPE), atol=1e-11, rtol=0)
        torch.testing.assert_close(lorentz_dot(vector, vector), lorentz_dot(moved, moved), atol=1e-11, rtol=1e-11)

    def test_distance_derivatives_at_coincident_points(self):
        q = torch.tensor([[0., 0., 0., 0.], [.2, -.1, .3, .1]], dtype=DTYPE, requires_grad=True)
        other = q.detach().clone().requires_grad_(True)
        self.assertTrue(torch.autograd.gradcheck(
            lambda x, y: squared_distance(exp_origin(x), exp_origin(y)),
            (q, other), eps=1e-6, atol=1e-5, rtol=1e-4
        ))


class NetworkTests(unittest.TestCase):
    def test_every_trainable_parameter_is_a_manifold_point(self):
        model = IntrinsicNetwork(seed=7)
        self.assertEqual(sum(p.numel() for p in model.parameters()), 170)
        self.assertEqual(model.intrinsic_degrees_of_freedom, 136)
        self.assertEqual(model.points_count, 34)
        self.assertFalse(any(isinstance(module, nn.Linear) for module in model.modules()))
        for p in model.parameters():
            self.assertEqual(p.shape[-1], 5)
            assert_points(self, p)

    def test_layers_stay_on_manifold_and_outputs_are_isometry_invariant(self):
        model = IntrinsicNetwork(seed=8)
        observations = torch.tensor([[0, 0, 0], [1, 0, 1], [1, 1, 1]], dtype=DTYPE)
        actions = torch.tensor([0, 1, 3])
        for state in model.latent_states(observations, actions):
            assert_points(self, state)
        expected = model(observations, actions).detach()
        transform = boost()
        with torch.no_grad():
            for p in model.parameters():
                p.copy_(p @ transform.T)
        torch.testing.assert_close(model(observations, actions), expected, atol=1e-10, rtol=1e-10)


class OptimizerTests(unittest.TestCase):
    def test_descent_momentum_and_points_stay_geometric(self):
        point = nn.Parameter(exp_origin(torch.tensor([[.7, -.2, .1, 0.]], dtype=DTYPE)))
        target = exp_origin(torch.tensor([[-.2, .1, .2, 0.]], dtype=DTYPE))
        optimizer = RiemannianAdam([point])
        before = float(squared_distance(point, target).detach().sum())
        for _ in range(15):
            optimizer.zero_grad()
            squared_distance(point, target).sum().backward()
            optimizer.step()
            assert_points(self, point)
            moment, _ = optimizer.state[0]
            torch.testing.assert_close(
                lorentz_dot(point, moment), torch.zeros(1, dtype=DTYPE), atol=1e-9, rtol=0
            )
        self.assertLess(float(squared_distance(point, target).detach().sum()), before)

    def test_optimizer_respects_isometries_inside_radius_constraint(self):
        transform = boost(.2)
        initial = exp_origin(torch.tensor([[.3, -.2, .1, 0.]], dtype=DTYPE))
        target = exp_origin(torch.tensor([[-.1, .2, .1, .1]], dtype=DTYPE))
        left, right = nn.Parameter(initial.clone()), nn.Parameter(initial @ transform.T)
        a, b = RiemannianAdam([left], lr=.01), RiemannianAdam([right], lr=.01)
        for _ in range(3):
            a.zero_grad()
            b.zero_grad()
            squared_distance(left, target).sum().backward()
            squared_distance(right, target @ transform.T).sum().backward()
            a.step()
            b.step()
            torch.testing.assert_close(right, left @ transform.T, atol=1e-10, rtol=1e-10)

    def test_nonfinite_gradient_does_not_partially_update_points(self):
        a = nn.Parameter(exp_origin(torch.zeros((1, 4), dtype=DTYPE)))
        b = nn.Parameter(exp_origin(torch.ones((1, 4), dtype=DTYPE) * .1))
        before = [a.detach().clone(), b.detach().clone()]
        optimizer = RiemannianAdam([a, b])
        a.grad = torch.ones_like(a)
        b.grad = torch.full_like(b, float("nan"))
        with self.assertRaises(FloatingPointError):
            optimizer.step()
        for p, original in zip((a, b), before):
            torch.testing.assert_close(p, original, atol=0, rtol=0)
        self.assertEqual(optimizer.steps, 0)


class LearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.cases = collect_cases(FileLab(Path(cls.temporary.name) / "fixtures"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_learns_observed_transitions_without_leaving_manifold(self):
        learner = IntrinsicEnsemble(seed=7, members=1)
        before = learner.evaluate(self.cases)
        for case in self.cases:
            learner.observe(case["state"], case["action"], case["result"])
        learner.learn(updates=600, batch_size=32)
        after = learner.evaluate(self.cases)
        self.assertLess(after["brier"], before["brier"] - .02)
        self.assertLess(after["brier"], .20)
        self.assertGreater(after["geodesic_parameter_displacement"], 1e-4)
        self.assertLess(after["max_manifold_constraint_error"], 1e-9)
        for model, optimizer in zip(learner.models, learner.optimizers):
            for p, (moment, _) in zip(model.parameters(), optimizer.state):
                assert_points(self, p)
                torch.testing.assert_close(
                    lorentz_dot(p, moment), torch.zeros_like(p[..., 0]), atol=1e-9, rtol=0
                )
        print(
            "INTRINSIC_TRAINING_TEST_JSON=" + str({
                "before_brier": before["brier"], "after_brier": after["brier"],
                "constraint_error": after["max_manifold_constraint_error"],
            }), flush=True
        )

    def test_checkpoint_is_independent_and_restores_predictions(self):
        learner = IntrinsicEnsemble(seed=3, members=1)
        expected = learner.predict(self.cases)
        saved = learner.checkpoint()
        learner.observe([0, 0, 0], 0, [1, 0, 0, 1])
        learner.learn(updates=2)
        restored = IntrinsicEnsemble(seed=999, members=1)
        restored.load_weights(saved)
        torch.testing.assert_close(restored.predict(self.cases), expected, atol=0, rtol=0)

    def test_invalid_checkpoint_is_rejected_before_mutation(self):
        learner = IntrinsicEnsemble(seed=3, members=1)
        expected = learner.predict(self.cases)
        saved = learner.checkpoint()
        saved["models"][0]["output_points"][..., 0] = 0
        with self.assertRaises(ValueError):
            learner.load_weights(saved)
        torch.testing.assert_close(learner.predict(self.cases), expected, atol=0, rtol=0)


if __name__ == "__main__":
    unittest.main()
