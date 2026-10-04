import json
import math
import random
import unittest

from first_piece.world import HistoryWorld
from first_piece.criterion import evaluate_distinction


class WorldTests(unittest.TestCase):
    def test_same_observation_opposite_actions(self):
        a, b = HistoryWorld(8), HistoryWorld(8)
        view = a.observe()
        self.assertEqual(view, b.observe())
        self.assertEqual(a.act(0) + b.act(1), 1)
        self.assertEqual(view["observation"], {"task": 0, "surface": "sealed"})

    def test_rule_changes_outcomes_without_leaking_into_view(self):
        a, b = HistoryWorld(11, rule=0), HistoryWorld(11, rule=1)
        for action in (0, 1) * 10:
            self.assertEqual(a.observe(), b.observe())
            self.assertEqual(a.act(action) + b.act(action), 1)

    def test_transfer_has_new_history_lengths_and_one_cue(self):
        for phase in ("acquisition", "transfer"):
            world = HistoryWorld(3, phase=phase)
            for _ in range(20):
                view = world.observe()
                history = view["history"]
                self.assertEqual(sum(token in (0, 1) for token in history), 1)
                self.assertTrue(2 <= len(history) <= 7 if phase == "acquisition" else 13 <= len(history) <= 33)
                world.act(0)

    def test_returned_history_is_not_hidden_state(self):
        world = HistoryWorld(0)
        view = world.observe()
        cue = next(token for token in view["history"] if token in (0, 1))
        view["history"].clear()
        self.assertEqual(world.act(cue), 1)

    def test_invalid_action_does_not_mutate_state(self):
        world = HistoryWorld(7)
        world.observe()
        before = world.checkpoint()
        for action in (-1, 2, .9, True, None):
            with self.assertRaises(ValueError):
                world.act(action)
            self.assertEqual(world.checkpoint(), before)

    def test_interaction_order_and_configuration_are_validated(self):
        world = HistoryWorld()
        with self.assertRaises(RuntimeError):
            world.act(0)
        world.observe()
        with self.assertRaises(RuntimeError):
            world.observe()
        for setting in ({"seed": -1}, {"rule": 2}, {"phase": "other"}, {"noise": 1}):
            with self.assertRaises(ValueError):
                HistoryWorld(**setting)

    def test_json_checkpoint_restores_pending_interaction_and_future(self):
        for noise in (False, True):
            original = HistoryWorld(29, phase="transfer", noise=noise)
            original.observe()
            restored = HistoryWorld.restore(json.loads(json.dumps(original.checkpoint())))
            self.assertEqual(original.act(1), restored.act(1))
            for action in (0, 1) * 10:
                self.assertEqual(original.observe(), restored.observe())
                self.assertEqual(original.act(action), restored.act(action))
            self.assertEqual(original.checkpoint(), restored.checkpoint())

    def test_noise_has_matched_inputs_and_uninformative_outcomes(self):
        structured, noise = HistoryWorld(17), HistoryWorld(17, noise=True)
        actions = random.Random(123)
        matches = 0
        for _ in range(10000):
            self.assertEqual(structured.observe(), noise.observe())
            action = actions.randrange(2)
            matches += structured.act(action) == noise.act(action)
        self.assertLess(abs(matches / 10000 - .5), .03)

    def test_corrupt_checkpoint_is_rejected(self):
        world = HistoryWorld(8)
        world.observe()
        before = world.checkpoint()
        bad = json.loads(json.dumps(before))
        bad["inputs_rng"] = []
        with self.assertRaises(ValueError):
            HistoryWorld.restore(bad)
        self.assertEqual(world.checkpoint(), before)

    def test_global_random_generator_is_preserved(self):
        before = random.getstate()
        world = HistoryWorld(9)
        world.observe()
        world.act(0)
        self.assertEqual(random.getstate(), before)


class EvidenceTests(unittest.TestCase):
    @staticmethod
    def good(n):
        outcomes = [i % 2 for i in range(n)]
        return ([.5] * n, [.99 if y else .01 for y in outcomes], outcomes, outcomes)

    def test_short_evidence_can_be_pending_and_long_evidence_accepted(self):
        early = evaluate_distinction(*self.good(100))
        later = evaluate_distinction(*self.good(10000))
        self.assertEqual(early["decision"], "pending_evidence")
        self.assertEqual(later["decision"], "accept")
        self.assertAlmostEqual(later["mean_log_score_gain"], math.log(.99 / .5))

    def test_confidently_harmful_proposal_is_rejected(self):
        old, new, y, group = self.good(10000)
        bad = evaluate_distinction(old, [1 - p for p in new], y, group)
        self.assertEqual(bad["decision"], "reject")

    def test_capacity_and_branch_support_are_enforced(self):
        self.assertEqual(
            evaluate_distinction(*self.good(10000), max_units=1)["decision"],
            "blocked_by_budget",
        )
        old, new, y, group = self.good(10000)
        self.assertEqual(
            evaluate_distinction(old, new, y, [0] * len(y))["decision"],
            "pending_support",
        )

    def test_invalid_evidence_is_rejected(self):
        for args in (([], [], [], []), ([.5], [.9], [2], [0]),
                     ([.5], [float("nan")], [1], [0]),
                     ([.5], [1.1], [1], [0]), ([.5], [.9], [1], [])):
            with self.assertRaises(ValueError):
                evaluate_distinction(*args)
        with self.assertRaises(ValueError):
            evaluate_distinction(*self.good(100), alpha=0)


if __name__ == "__main__":
    unittest.main()
