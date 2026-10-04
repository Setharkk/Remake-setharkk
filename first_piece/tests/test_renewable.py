"""Lifetime risk, bounded lineage, migration and exact renewal resume."""
import copy
import json
import math
import random
import unittest

from first_piece.shared import ALPHA, SharedLearner
from first_piece.renewable import RenewableLearner
from first_piece.renewable_adapter import RenewableAdapter
from first_piece.shared_adapter import SharedAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.tests.test_shared import train, wire_symbol
from first_piece.integration_probe import agent_proposal, observed_receipt


def constant_step(core, i):
    core.receive({"kind": "token", "token": "constant", "task": 0})
    core.receive({"kind": "surface", "surface": "sealed", "task": 0})
    core.learn(i % 2, i % 2)


def canonical(core):
    data = core.checkpoint()
    for search in data["searches"]:
        search["elapsed_seconds"] = 0
    return data


class RenewableTests(unittest.TestCase):
    def test_summable_risk_and_stricter_later_intervals(self):
        core = RenewableLearner(max_attempts=2)
        weights = [core._interval_alpha(a) for a in range(1, 2001, 2)]
        self.assertAlmostEqual(math.fsum(weights), ALPHA * 1000 / 1001)
        self.assertLess(core._interval_alpha(3), core._interval_alpha(1))
        self.assertGreater(core._interval(10, 128, attempt=3)["bound"],
                           core._interval(10, 128, attempt=1)["bound"])
        self.assertEqual(SharedLearner()._interval_alpha(999), ALPHA)

    def test_more_than_sixteen_attempts_bounded_history_and_exact_resume(self):
        core = RenewableLearner(n_actions=2, max_attempts=2, min_records=64, cooldown=128)
        for i in range(10000):
            constant_step(core, i)
        self.assertGreater(core.attempts, 16)
        self.assertGreater(core.renewal["archived_attempts"], 16)
        self.assertLessEqual(len(core.searches), 2)
        self.assertLessEqual(len(core.decisions), 6)
        self.assertEqual(core.admissions, 0)
        self.assertEqual(core.neural_updates, 2 * core.steps)
        restored = RenewableLearner.restore(json.loads(json.dumps(core.checkpoint())))
        for i in range(10000, 10512):
            constant_step(core, i)
            constant_step(restored, i)
        self.assertEqual(canonical(core), canonical(restored))
        self.assertEqual(core.metrics()["lifetime_alpha_upper_bound"], ALPHA)

    def test_frozen_later_block_resume_preserves_future_decisions(self):
        core = RenewableLearner(5, max_tasks=2, max_symbols=8, n_actions=2,
                                max_attempts=2, min_records=128, fit_per_context=64)
        world = ScaleWorld(3, n_contexts=2, n_symbols=8, n_actions=2)
        rng = random.Random(2001)
        for i in range(20000):
            events, _ = world.episode(i % 2)
            for event in events:
                core.receive(event)
            core.learn(rng.randrange(2), rng.randrange(2))
            if core.attempts > 2 and core.trial is not None and core.trial["n"] == 32:
                break
        self.assertGreater(core.attempts, 2)
        self.assertIsNotNone(core.trial)
        restored = RenewableLearner.restore(json.loads(json.dumps(core.checkpoint())))
        for i in range(1500):
            events, target = world.episode(i % 2)
            action = rng.randrange(2)
            for model in (core, restored):
                for event in events:
                    model.receive(event)
                model.learn(action, int(action == target))
        self.assertEqual(canonical(core), canonical(restored))
        self.assertLessEqual(len(core.searches), 2)

    def test_ledger_interval_and_count_corruption_rejected(self):
        core = RenewableLearner(n_actions=2, max_attempts=2, min_records=64, cooldown=128)
        for i in range(1000):
            constant_step(core, i)
        original = core.checkpoint()
        mutators = [
            lambda d: d["renewal"].__setitem__("archived_attempts", 1),
            lambda d: d["renewal"].__setitem__("archived_fit_records", 64),
            lambda d: d["renewal"]["terminal_counts"].__setitem__("accept", 1),
            lambda d: d["renewal"].__setitem__("archived_at", d["steps"] + 1),
            lambda d: d["renewal"].__setitem__("legacy_first_block", "yes"),
            lambda d: d.__setitem__("neural_updates", d["neural_updates"] + 2),
        ]
        for mutate in mutators:
            bad = copy.deepcopy(original)
            mutate(bad)
            with self.assertRaises(ValueError):
                RenewableLearner.restore(bad)
        noise = RenewableLearner(max_tasks=2, max_symbols=8, n_actions=2, max_attempts=2,
                                 fit_per_context=64, min_records=128)
        world, rng = ScaleWorld(2, n_symbols=8, n_contexts=2, n_actions=2), random.Random(17)
        for i in range(1000):
            events, _ = world.episode(i % 2)
            for event in events:
                noise.receive(event)
            noise.learn(rng.randrange(2), rng.randrange(2))
        for d in noise.decisions:
            if "relevance" in d:
                bad = noise.checkpoint()
                bad["decisions"][noise.decisions.index(d)]["relevance"]["bound"] += .01
                with self.assertRaises(ValueError):
                    RenewableLearner.restore(bad)
                break
        else:
            self.fail("Expected a real statistical look")

    def test_explicit_finite_import_preserves_weights_and_historical_budget(self):
        finite = train(SharedLearner(91, max_tasks=2, n_actions=2),
                       ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
        original = finite.checkpoint()
        converted = RenewableLearner.from_finite_checkpoint(original)
        core = RenewableLearner.restore(converted)
        for name in ("active", "baseline", "rng", "steps", "attempts", "admissions",
                     "neural_updates", "searches", "decisions"):
            self.assertEqual(converted[name], original[name])
        self.assertEqual(core._interval_alpha(1), ALPHA)
        self.assertEqual(core._interval_alpha(17), ALPHA / 2)
        self.assertEqual(core.metrics()["lifetime_alpha_upper_bound"], 2 * ALPHA)
        with self.assertRaises(ValueError):
            RenewableLearner.restore(original)

    def test_wire_import_pending_receipt_and_renewal_copy_are_exact(self):
        adapter = SharedAdapter(actions=("left", "right"), learner_options={"max_attempts": 2})
        adapter.submit_observation(wire_symbol(0, "a"))
        prediction = adapter.submit_observation(wire_symbol(1, "sealed", end=True))
        request = adapter.register_action(agent_proposal(prediction, 0), executor_id="executor")
        fresh = RenewableAdapter.from_finite_checkpoint(json.loads(json.dumps(adapter.checkpoint())))
        restored = RenewableAdapter.restore(fresh)
        self.assertEqual(restored.current_prediction(), prediction)
        receipt = observed_receipt(request, 1)
        ack = restored.submit_receipt(receipt)
        self.assertEqual(restored.submit_receipt(receipt), ack)
        self.assertEqual(restored.metrics()["model_revision"], 1)
        self.assertEqual(restored.capabilities()["lifetime_alpha_upper_bound"], .1)
        fork = restored._learner._transaction_copy()
        fork.renewal["terminal_counts"]["unsupported"] += 1
        self.assertEqual(restored._learner.renewal["terminal_counts"]["unsupported"], 0)

    def test_archived_last_admission_controls_live_update_counts(self):
        finite = train(SharedLearner(91, max_tasks=2, n_actions=2, max_attempts=2),
                       ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
        self.assertGreater(finite.admissions, 0)
        core = RenewableLearner.restore(RenewableLearner.from_finite_checkpoint(finite.checkpoint()))
        world, rng = ScaleWorld(31, n_contexts=2, n_actions=2), random.Random(97)
        for i in range(15000):
            events, _ = world.episode(i % 2)
            for event in events:
                core.receive(event)
            core.learn(rng.randrange(2), rng.randrange(2))
            if core.renewal["archived_admissions"]:
                break
        self.assertGreater(core.renewal["archived_admissions"], 0)
        state = core.checkpoint()
        self.assertEqual(RenewableLearner.restore(state).checkpoint(), state)
        state["active"]["counts"][0][0] += 1
        with self.assertRaises(ValueError):
            RenewableLearner.restore(state)


if __name__ == "__main__":
    unittest.main()
