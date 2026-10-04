"""Protected serving, conditional widths, extended horizons and exact resume."""
import copy
import json
import math
import random
import unittest

from first_piece.consolidated import ConsolidatedLearner, EXTENDED_HORIZONS, UNIVERSAL_WIDTH
from first_piece.consolidated_adapter import ConsolidatedAdapter
from first_piece.renewable import RenewableLearner
from first_piece.renewable_adapter import RenewableAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.shared import log_probability
from first_piece.tests.test_shared import train, wire_symbol
from first_piece.integration_probe import agent_proposal, observed_receipt


def canonical(core):
    data = core.checkpoint()
    for s in data["searches"]:
        s["elapsed_seconds"] = 0
    return data


class ConsolidatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = train(ConsolidatedLearner(100, max_tasks=8, max_symbols=16),
                            ScaleWorld(400, n_symbols=16, n_contexts=4), 10000).checkpoint()
        assert cls.initial["protected"] is not None

    def core(self):
        return ConsolidatedLearner.restore(self.initial)

    def test_noise_changes_working_banks_without_changing_served_competence(self):
        core, world = self.core(), ScaleWorld(400, n_symbols=16, n_contexts=4)
        frozen = core.checkpoint()["protected"]
        initial_active = core.active.checkpoint()
        rng = random.Random(97)
        for i in range(4000):
            events, _ = world.episode(i % 4)
            for event in events:
                p = core.receive(event)
            action, y = rng.randrange(4), int(rng.random() < .25)
            observed = core.learn(action, y)
            self.assertEqual(p[action], observed)
            self.assertEqual(core.tasks[i % 4]["losses"][-1], (p[action] - y) ** 2)
        self.assertEqual(core.checkpoint()["protected"], frozen)
        self.assertNotEqual(core.active.checkpoint(), initial_active)
        world.rng = random.Random(74001)
        for slot in range(4):
            for _ in range(128):
                events, target = world.episode(slot)
                for event in events:
                    p = core.receive(event)
                self.assertEqual(max(range(4), key=p.__getitem__), target)
                core.finish_evaluation()
        self.assertEqual(ConsolidatedLearner.restore(core.checkpoint()).checkpoint(), core.checkpoint())

    def test_conditional_width_covers_every_possible_forecast_pair(self):
        core, world = self.core(), ScaleWorld(400, n_symbols=16, n_contexts=4)
        rng = random.Random(108)
        for i in range(3000):
            events, target = world.episode(i % 4, changed=True)
            for event in events:
                core.receive(event)
            action = rng.randrange(4)
            core.learn(action, int(action == target))
            if core.trial is not None and len(core.trial["program"]) == 3:
                break
        self.assertIsNotNone(core.trial)
        self.assertEqual(len(core.trial["program"]), 3)
        width = core._validation(core.attempts)["widths"]["preservation"]
        self.assertLess(width, UNIVERSAL_WIDTH)
        for old_route, proposed_route in core._joint_routes(core.program, core.trial["program"], 0):
            for a in range(4):
                old = core._protected["bank"].probability(a, old_route)
                new = core.candidate.probability(a, proposed_route)
                gains = [log_probability(new, y) - log_probability(old, y) for y in (0, 1)]
                self.assertLessEqual(abs(gains[1] - gains[0]), width + 1e-12)
        # Incompatible programmes must include mismatched routes in the bound.
        self.assertIn((0, 1), core._joint_routes([0], [1], 0))
        # A context equality is never allowed to be true for another context.
        pairs = core._joint_routes([core.context_offset], [core.context_offset], 0)
        self.assertEqual(pairs, {(0, 0)})

    def test_pending_trial_and_protected_bank_resume_exact_future_admission(self):
        core, world = self.core(), ScaleWorld(400, n_symbols=16, n_contexts=4)
        rng = random.Random(108)
        for i in range(3000):
            events, target = world.episode(i % 4, changed=True)
            for event in events:
                core.receive(event)
            action = rng.randrange(4)
            core.learn(action, int(action == target))
            if core.trial is not None and len(core.trial["program"]) == 3 and core.trial["n"] == 32:
                break
        self.assertIsNotNone(core.trial)
        restored = ConsolidatedLearner.restore(json.loads(json.dumps(core.checkpoint())))
        before = core.admissions
        for i in range(20000):
            events, target = world.episode(i % 4, changed=True)
            action = rng.randrange(4)
            for model in (core, restored):
                for event in events:
                    model.receive(event)
                model.learn(action, int(action == target))
            if core.admissions > before:
                break
        self.assertGreater(core.admissions, before)
        self.assertEqual(canonical(core), canonical(restored))
        self.assertEqual(core._protected["at"], core.steps)

    def test_extended_horizon_is_used_for_weak_real_signal(self):
        core = ConsolidatedLearner(8, max_tasks=1, max_symbols=16, n_actions=4,
                                   fit_per_context=1024, min_records=1024, max_attempts=2)
        world, rng = ScaleWorld(401, n_symbols=16, n_contexts=1), random.Random(742)
        for _ in range(30000):
            events, target = world.episode(0)
            for event in events:
                core.receive(event)
            action = rng.randrange(4)
            y = int(action == target) if rng.random() < .65 else int(rng.random() < .25)
            core.learn(action, y)
            if core.admissions:
                break
        self.assertTrue(any(d.get("relevance", {}).get("n", 0) > 4096 for d in core.decisions))
        self.assertGreater(core.admissions, 0)
        self.assertEqual(ConsolidatedLearner.restore(core.checkpoint()).checkpoint(), core.checkpoint())

    def test_corrupt_protected_counts_width_and_horizons_rejected(self):
        core = self.core()
        bad = core.checkpoint()
        bad["protected"]["bank"]["counts"][0][0] += 1
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)
        bad = core.checkpoint()
        bad["searches"][0]["validation"]["horizons"][-1] = 99999
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)
        bad = core.checkpoint()
        bad["searches"][0]["validation"]["widths"]["relevance"] = .1
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)
        bad = core.checkpoint()
        bad["decisions"][0]["relevance"]["range_width"] = .1
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)
        bad = core.checkpoint()
        bad["policy_start_attempt"] = core.attempts + 2
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)

    def test_live_frozen_width_cannot_be_rewritten_on_resume(self):
        core, world = self.core(), ScaleWorld(400, n_symbols=16, n_contexts=4)
        rng = random.Random(108)
        for i in range(3000):
            events, target = world.episode(i % 4, changed=True)
            for event in events:
                core.receive(event)
            a = rng.randrange(4)
            core.learn(a, int(a == target))
            if core.trial is not None and len(core.trial["program"]) == 3 and core.trial["n"] == 32:
                break
        bad = core.checkpoint()
        bad["searches"][-1]["validation"]["widths"]["preservation"] /= 2
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)
        original = core.checkpoint()
        fork = core._transaction_copy()
        fork._protected["bank"].points[0][0][0] += .1
        self.assertEqual(core.checkpoint(), original)

    def test_renewable_import_preserves_pending_trial_and_risk(self):
        old = train(RenewableLearner(5, max_tasks=4), ScaleWorld(1, n_contexts=4), 600)
        self.assertIsNotNone(old.trial)
        data = ConsolidatedLearner.from_renewable_checkpoint(old.checkpoint())
        recovered = ConsolidatedLearner.restore(data)
        for key in ("active", "baseline", "candidate", "control", "trial", "rng",
                    "steps", "attempts", "admissions", "neural_updates", "decisions", "searches", "renewal"):
            self.assertEqual(data[key], old.checkpoint()[key])
        self.assertEqual(recovered._horizons(1), (128, 1024, 4096))
        self.assertEqual(recovered._horizons(2), EXTENDED_HORIZONS)
        self.assertEqual(recovered.metrics()["lifetime_alpha_upper_bound"], .05)

    def test_import_freezes_current_weights_with_valid_provenance(self):
        old = train(RenewableLearner(100, max_tasks=8, max_symbols=16),
                    ScaleWorld(400, n_symbols=16, n_contexts=4), 10000)
        data = ConsolidatedLearner.from_renewable_checkpoint(old.checkpoint())
        self.assertEqual(data["protected"]["bank"], old.active.checkpoint())
        self.assertEqual(data["protected"]["source"], "import")
        self.assertEqual(ConsolidatedLearner.restore(data).checkpoint(), data)
        bad = copy.deepcopy(data)
        bad["protected"]["at"] -= 1
        with self.assertRaises(ValueError):
            ConsolidatedLearner.restore(bad)

    def test_wire_request_import_and_duplicate_receipt_learn_once(self):
        old = RenewableAdapter(actions=("left", "right"))
        old.submit_observation(wire_symbol(0, "opaque"))
        prediction = old.submit_observation(wire_symbol(1, "sealed", end=True))
        request = old.register_action(agent_proposal(prediction, 0), executor_id="executor")
        data = ConsolidatedAdapter.from_renewable_checkpoint(old.checkpoint())
        restored = ConsolidatedAdapter.restore(json.loads(json.dumps(data)))
        self.assertEqual(restored.current_prediction(), prediction)
        ack = restored.submit_receipt(observed_receipt(request, 1))
        self.assertEqual(restored.submit_receipt(observed_receipt(request, 1)), ack)
        self.assertEqual(restored.metrics()["model_revision"], 1)
        self.assertEqual(restored.capabilities()["max_protected_banks"], 1)


if __name__ == "__main__":
    unittest.main()
