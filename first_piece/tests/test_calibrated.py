"""Calibration must improve proper scores without altering competence learning."""
import copy
import json
import random
import unittest

from first_piece.calibrated import CalibratedLearner, CONTRAST_FLOOR
from first_piece.calibrated_adapter import CalibratedAdapter
from first_piece.consolidated import ConsolidatedLearner
from first_piece.consolidated_adapter import ConsolidatedAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.tests.test_shared import train, wire_symbol
from first_piece.integration_probe import agent_proposal, observed_receipt


def canonical(core):
    data = core.checkpoint()
    for s in data["searches"]:
        s["elapsed_seconds"] = 0
    return data


class CalibratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old = train(ConsolidatedLearner(100, max_tasks=8, max_symbols=16),
                    ScaleWorld(400, n_symbols=16, n_contexts=4), 10000)
        cls.original = old.checkpoint()
        cls.initial = CalibratedLearner.from_consolidated_checkpoint(cls.original)
        assert cls.initial["protected"] is not None

    def core(self):
        return CalibratedLearner.restore(self.initial)

    def test_noise_reduces_overconfidence_but_never_changes_the_protected_bank(self):
        core = self.core()
        frozen = core.checkpoint()["protected"]
        world, rng = ScaleWorld(400, n_symbols=16, n_contexts=4), random.Random(891)
        score = 0.0
        for i in range(4000):
            events, _ = world.episode(i % 4)
            for event in events:
                p = core.receive(event)
            action, y = rng.randrange(4), int(rng.random() < .25)
            self.assertEqual(core.learn(action, y), p[action])
            if i >= 2000:
                score += (p[action] - y) ** 2
        self.assertLess(score / 2000, .21)
        self.assertEqual(core.checkpoint()["protected"], frozen)
        for slot in range(4):
            params = core.calibration_parameters(slot)
            self.assertLess(params["retained_contrast"], .2)
            self.assertAlmostEqual(params["background_rate"], .25, delta=.09)
            for _ in range(64):
                events, target = world.episode(slot)
                for event in events:
                    p = core.receive(event)
                self.assertEqual(max(range(4), key=p.__getitem__), target)
                core.finish_evaluation()
        self.assertEqual(CalibratedLearner.restore(core.checkpoint()).checkpoint(),
                         core.checkpoint())

    def test_background_rate_is_learned_instead_of_assuming_one_over_actions(self):
        core, world = self.core(), ScaleWorld(400, n_symbols=16, n_contexts=4)
        rng = random.Random(901)
        for i in range(3200):
            slot = i % 4
            events, _ = world.episode(slot)
            for event in events:
                p = core.receive(event)
            action = rng.randrange(4)
            y = int(rng.random() < (.1 if slot < 2 else .6))
            core.learn(action, y)
        for slot in range(4):
            params = core.calibration_parameters(slot)
            expected = .1 if slot < 2 else .6
            self.assertAlmostEqual(params["background_rate"], expected, delta=.09)
            self.assertLess(params["retained_contrast"], .2)

    def test_calibration_cannot_change_neural_updates_search_or_admission_decisions(self):
        calibrated = self.core()
        raw = ConsolidatedLearner.restore(self.original)
        world, rng = ScaleWorld(400, n_symbols=16, n_contexts=4), random.Random(917)
        for i in range(2500):
            events, target = world.episode(i % 4, changed=True)
            action = rng.randrange(4)
            for model in (calibrated, raw):
                for event in events:
                    model.receive(event)
                model.learn(action, int(action == target))
        a, b = canonical(calibrated), canonical(raw)
        a.pop("calibration")
        a["format"], a["implementation"] = b["format"], b["implementation"]
        self.assertEqual(a, b)
        self.assertEqual(calibrated.metrics()["validation_reference"],
                         "raw_protected_competence")

    def test_new_context_warms_up_without_borrowing_another_contexts_outcomes(self):
        core = self.core()
        world, rng = ScaleWorld(400, n_symbols=16, n_contexts=5), random.Random(919)
        for _ in range(40):
            events, target = world.episode(4)
            for event in events:
                p = core.receive(event)
            action = rng.randrange(4)
            core.learn(action, int(action == target))
        self.assertEqual(core.calibration_parameters(4)["observations"], 40)
        self.assertTrue(core.calibration_parameters(4)["active"])
        self.assertEqual(CalibratedLearner.restore(core.checkpoint()).checkpoint(),
                         core.checkpoint())

    def test_pending_forecast_resume_and_private_fork_are_exact(self):
        core = self.core()
        for event in ScaleWorld(400, n_symbols=16, n_contexts=4).episode(0)[0]:
            p = core.receive(event)
        restored = CalibratedLearner.restore(json.loads(json.dumps(core.checkpoint())))
        self.assertEqual(restored.pending_probabilities(), p)
        for model in (core, restored):
            self.assertEqual(model.learn(1, 0), p[1])
        self.assertEqual(canonical(core), canonical(restored))
        before = core.checkpoint()
        fork = core._transaction_copy()
        fork._calibration[0]["probabilities"][0] = 0.0
        self.assertEqual(core.checkpoint(), before)

    def test_corrupt_cached_predictions_moments_policy_and_import_boundary_rejected(self):
        for field in ("probability", "moment", "window", "slot", "pending"):
            bad = copy.deepcopy(self.initial)
            cache = bad["calibration"]["contexts"]["0"]
            if field == "probability":
                cache["probabilities"][0] = 1 - cache["probabilities"][0]
            elif field == "moment":
                cache["sums"][0] += .01
            elif field == "window":
                bad["calibration"]["window"] += 1
            elif field == "slot":
                bad["calibration"]["contexts"]["07"] = bad["calibration"]["contexts"].pop("0")
            else:
                bad["calibration"]["pending_import_at"] = bad["steps"]
            with self.subTest(field=field), self.assertRaises(ValueError):
                CalibratedLearner.restore(bad)

    def test_mixture_preserves_action_order_and_stays_in_probability_bounds(self):
        core = self.core()
        for slot in range(4):
            params = core.calibration_parameters(slot)
            self.assertGreaterEqual(params["retained_contrast"], CONTRAST_FLOOR)
            events, _ = ScaleWorld(400, n_symbols=16, n_contexts=4).episode(slot)
            for event in events:
                p = core.receive(event)
            raw = ConsolidatedLearner.pending_probabilities(core)
            self.assertEqual(sorted(range(4), key=p.__getitem__),
                             sorted(range(4), key=raw.__getitem__))
            self.assertTrue(all(0 <= value <= 1 for value in p))
            core.finish_evaluation()

    def test_invalid_feedback_does_not_mutate_calibration_or_neural_state(self):
        core = self.core()
        for event in ScaleWorld(400, n_symbols=16, n_contexts=4).episode(0)[0]:
            core.receive(event)
        before = core.checkpoint()
        for action, y in ((True, 0), (4, 0), (0, .5)):
            with self.assertRaises(ValueError):
                core.learn(action, y)
            self.assertEqual(core.checkpoint(), before)

    def test_explicit_import_preserves_an_old_live_forecast_until_its_feedback(self):
        old = ConsolidatedLearner.restore(self.original)
        world = ScaleWorld(400, n_symbols=16, n_contexts=4)
        for event in world.episode(0)[0]:
            p = old.receive(event)
        core = CalibratedLearner.restore(
            CalibratedLearner.from_consolidated_checkpoint(old.checkpoint()))
        self.assertEqual(core.pending_probabilities(), p)
        self.assertEqual(core.learn(0, 1), p[0])
        self.assertIsNone(core.pending_import_at)
        self.assertEqual(CalibratedLearner.restore(core.checkpoint()).checkpoint(),
                         core.checkpoint())

    def test_imported_pending_forecast_can_close_without_a_label(self):
        old = ConsolidatedLearner.restore(self.original)
        for event in ScaleWorld(400, n_symbols=16, n_contexts=4).episode(0)[0]:
            old.receive(event)
        core = CalibratedLearner.restore(
            CalibratedLearner.from_consolidated_checkpoint(old.checkpoint()))
        frozen, steps = core.checkpoint()["protected"], core.steps
        core.finish_evaluation()
        self.assertIsNone(core.pending_import_at)
        self.assertEqual(core.steps, steps)
        self.assertEqual(core.checkpoint()["protected"], frozen)
        self.assertEqual(CalibratedLearner.restore(core.checkpoint()).checkpoint(),
                         core.checkpoint())

    def test_wire_import_pending_request_and_repeated_receipt_keep_one_update(self):
        old = ConsolidatedAdapter(actions=("left", "right"))
        old.submit_observation(wire_symbol(0, "opaque"))
        prediction = old.submit_observation(wire_symbol(1, "sealed", end=True))
        request = old.register_action(agent_proposal(prediction, 0), executor_id="executor")
        data = CalibratedAdapter.from_consolidated_checkpoint(old.checkpoint())
        core = CalibratedAdapter.restore(json.loads(json.dumps(data)))
        self.assertEqual(core.current_prediction(), prediction)
        ack = core.submit_receipt(observed_receipt(request, 1))
        after = core.checkpoint()
        self.assertEqual(core.submit_receipt(observed_receipt(request, 1)), ack)
        self.assertEqual(core.checkpoint(), after)
        self.assertEqual(core.metrics()["model_revision"], 1)
        self.assertEqual(core.capabilities()["probability_calibration"],
                         "rolling-mixture-v1")


if __name__ == "__main__":
    unittest.main()
