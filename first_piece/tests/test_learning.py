import copy
import json
import math
import random
import unittest

from first_piece.learner import DistinctionLearner
from first_piece.learning_run import episode, evaluate
from first_piece.spherical import SpherePredictor, norm
from first_piece.streaming import StreamingWorld


def train(seed=0, rule=0, mode="structured", n=6000, **config):
    learner = DistinctionLearner(seed + 100003, **config)
    world = StreamingWorld(seed, rule, mode=mode)
    actions = random.Random(seed + 200003)
    for _ in range(n):
        episode(world, [learner], actions.randrange(2))
    return learner


class SphereTests(unittest.TestCase):
    def test_update_improves_score_and_preserves_sphere_and_tangence(self):
        model = SpherePredictor()
        previous = model.probability(0, 0)
        diagnostic = model.update(0, 1, 0)
        self.assertGreater(model.probability(0, 0), previous)
        self.assertLess(diagnostic["tangent_residual"], 1e-12)
        self.assertLess(diagnostic["sphere_residual"], 1e-12)
        for step in range(1000):
            model.update(step % 2, (step // 2) % 2, (step // 3) % 2)
        for row in model.points:
            for p in row:
                self.assertAlmostEqual(norm(p), 1, places=12)

    def test_readout_and_update_are_equivariant_under_rotation(self):
        angle = .71
        def rotate(v):
            x, y, z = v
            return [math.cos(angle) * x - math.sin(angle) * y,
                    math.sin(angle) * x + math.cos(angle) * y, z]
        original = SpherePredictor()
        transformed = SpherePredictor.restore(original.checkpoint())
        transformed.points = [[rotate(p) for p in row] for row in transformed.points]
        transformed.anchors = [rotate(p) for p in transformed.anchors]
        for step in range(32):
            action, outcome, route = step % 2, (step // 2) % 2, (step // 3) % 2
            self.assertAlmostEqual(original.probability(action, route),
                                   transformed.probability(action, route), places=11)
            original.update(action, outcome, route)
            transformed.update(action, outcome, route)
            for row, other in zip(original.points, transformed.points):
                for p, q in zip(row, other):
                    for x, y in zip(rotate(p), q):
                        self.assertAlmostEqual(x, y, places=11)

    def test_corrupt_sphere_checkpoint_is_rejected(self):
        snapshot = SpherePredictor().checkpoint()
        snapshot["points"][0][0] = [2.0, 0.0, 0.0]
        with self.assertRaises(ValueError):
            SpherePredictor.restore(snapshot)


class StreamingTests(unittest.TestCase):
    def test_stream_never_exposes_history_or_rule(self):
        world = StreamingWorld(3, rule=1, phase="transfer")
        tokens = []
        while True:
            event = world.next_event()
            self.assertNotIn("history", event)
            self.assertNotIn("rule", event)
            self.assertEqual(set(event), {"kind", "task", "token"} if event["kind"] == "token"
                             else {"kind", "task", "surface"})
            if event["kind"] == "surface":
                break
            tokens.append(event["token"])
        self.assertGreaterEqual(len(tokens), 13)
        with self.assertRaises(RuntimeError):
            world.next_event()
        world.act(0)

    def test_json_stream_checkpoint_continues_exactly(self):
        for mode in ("structured", "noise", "action_only"):
            world = StreamingWorld(4, phase="transfer", mode=mode)
            for _ in range(7):
                world.next_event()
            restored = StreamingWorld.restore(json.loads(json.dumps(world.checkpoint())))
            while True:
                event = world.next_event()
                self.assertEqual(event, restored.next_event())
                if event["kind"] == "surface":
                    break
            self.assertEqual(world.act(1), restored.act(1))
            self.assertEqual(world.checkpoint(), restored.checkpoint())


class LearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = train(seed=2, rule=1)
        cls.ablated = train(seed=2, rule=1, allow_distinctions=False)

    def test_learns_unknown_rule_and_transfers_with_matched_ablation(self):
        scores = evaluate(self.full, self.ablated, seed=929, rule=1,
                          phase="transfer", mode="structured", n=256)["models"]
        self.assertIsNotNone(self.full.tasks[0]["token"])
        self.assertGreaterEqual(scores["full"]["policy_success"], .95)
        self.assertLess(scores["full"]["brier"], scores["without_distinction"]["brier"] - .1)
        self.assertLessEqual(scores["without_distinction"]["policy_success"], .65)
        self.assertEqual(self.full.metrics()["neural_updates"],
                         self.ablated.metrics()["neural_updates"])
        for decision in self.full.tasks[0]["decisions"]:
            self.assertEqual(decision["candidate_fit_updates"], 256)
            self.assertEqual(decision["control_fit_updates"], 256)

    def test_memory_intervention_changes_performance_without_changing_parameters(self):
        before = self.full.checkpoint()
        scores = evaluate(self.full, self.ablated, seed=930, rule=1,
                          phase="transfer", mode="structured", n=256)["models"]
        self.assertGreater(scores["full"]["policy_success"],
                           scores["without_memory"]["policy_success"] + .25)
        self.assertEqual(before, self.full.checkpoint())

    def test_control_only_action_relation_does_not_create_a_distinction(self):
        learner = train(seed=1, mode="action_only", n=5000)
        self.assertIsNone(learner.tasks[0]["token"])
        self.assertNotIn("accept", [d["decision"] for d in learner.tasks[0]["decisions"]])
        self.assertGreater(learner.tasks[0]["active"].probability(0, 0), .95)

    def test_noise_does_not_create_a_distinction_in_this_fixture(self):
        learner = train(seed=1, mode="noise", n=5000)
        self.assertIsNone(learner.tasks[0]["token"])
        self.assertNotIn("accept", [d["decision"] for d in learner.tasks[0]["decisions"]])

    def test_frozen_models_do_not_change_on_validation_labels(self):
        learner = train(seed=3, n=300)
        state = learner.tasks[0]
        self.assertEqual(state["status"], "validating")
        before = {k: state[k].checkpoint() for k in ("candidate", "control")}
        world = StreamingWorld(102)
        for _ in range(16):
            episode(world, [learner], 0)
        self.assertEqual(before, {k: state[k].checkpoint() for k in ("candidate", "control")})

    def test_task_retention_keeps_existing_network_unchanged(self):
        learner = DistinctionLearner.restore(self.full.checkpoint())
        before = learner.tasks[0]["active"].checkpoint()
        other = StreamingWorld(481, rule=0, task=1)
        for i in range(1000):
            episode(other, [learner], i % 2)
        self.assertEqual(before, learner.tasks[0]["active"].checkpoint())

    def test_full_json_resume_includes_validation_and_pending_memory(self):
        original = train(seed=4, n=400)
        world = StreamingWorld(222, rule=1, mode="noise", phase="transfer")
        for _ in range(5):
            original.receive(world.next_event())
        restored = DistinctionLearner.restore(json.loads(json.dumps(original.checkpoint())))
        recovered = StreamingWorld.restore(json.loads(json.dumps(world.checkpoint())))
        for i in range(32):
            while True:
                event = world.next_event()
                self.assertEqual(event, recovered.next_event())
                self.assertEqual(original.receive(event), restored.receive(event))
                if event["kind"] == "surface":
                    break
            action = i % 2
            outcome = world.act(action)
            self.assertEqual(outcome, recovered.act(action))
            original.learn(action, outcome)
            restored.learn(action, outcome)
        self.assertEqual(original.checkpoint(), restored.checkpoint())

    def test_invalid_feedback_and_event_leave_state_unchanged(self):
        learner = DistinctionLearner()
        before = learner.checkpoint()
        for event in ({"kind": "token", "task": 0, "token": True},
                      {"kind": "token", "task": -1, "token": 0},
                      {"kind": "token", "task": 0, "token": 0, "history": [0]}):
            with self.assertRaises(ValueError):
                learner.receive(event)
            self.assertEqual(before, learner.checkpoint())
        learner.receive({"kind": "token", "task": 0, "token": 0})
        learner.receive({"kind": "surface", "task": 0, "surface": "sealed"})
        before = learner.checkpoint()
        for action, outcome in ((-1, 0), (0, True), (1, 2)):
            with self.assertRaises(ValueError):
                learner.learn(action, outcome)
            self.assertEqual(before, learner.checkpoint())

    def test_corrupt_learner_checkpoint_is_rejected_without_mutating_original(self):
        before = self.full.checkpoint()
        snapshot = copy.deepcopy(before)
        snapshot["tasks"][0]["active"]["points"][0][0] = [0, 0, 0]
        with self.assertRaises(ValueError):
            DistinctionLearner.restore(snapshot)
        self.assertEqual(before, self.full.checkpoint())


if __name__ == "__main__":
    unittest.main()
