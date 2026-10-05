"""Regression checks for audit defects, selective ownership and exact optimizations."""
import copy
import json
import random
import threading
import unittest
from unittest.mock import patch

from first_piece import adapter as adapter_module
from first_piece.integration_probe import agent_proposal, observed_receipt
from first_piece.learner import DistinctionLearner
from first_piece.plastic_revision import PlasticRevisionLearner
from first_piece.plastic_revision_adapter import PlasticRevisionAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.shared import SharedLearner, SharedSpherePredictor, _feature_masks, pair_coordinates, pair_index
from first_piece.spherical import SpherePredictor, learnable_point, unit
from first_piece.temporal import TemporalLearner
from first_piece.tests.test_shared import train, wire_symbol
from validation.plastic_revision_review import collect_boundary, confirmed_deadline

def attach(core, events):
    adapter = PlasticRevisionAdapter(learner_options={"max_tasks": core.config["max_tasks"],
                                                      "max_symbols": core.config["max_symbols"]})
    adapter._learner = core
    adapter._revision = core.steps
    adapter._slots = {f"ctx:{slot}": slot for slot in sorted(core.tasks)}
    for sequence, event in enumerate(events):
        prediction = adapter.submit_observation(wire_symbol(
            sequence, "sealed" if event["kind"] == "surface" else event["token"],
            context=f"ctx:{event['task']}", end=event["kind"] == "surface"))
    return adapter, prediction

class RevisionFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core, cls.events, cls.action, cls.outcome = collect_boundary()
        cls.boundary = core.checkpoint()

    def core(self):
        return PlasticRevisionLearner.restore(copy.deepcopy(self.boundary))

    def test_unpublished_feedback_copy_does_not_write_parent_validation(self):
        source = self.core()
        for event in self.events:
            source.receive(event)
        before = source.checkpoint()
        for kwargs in ({}, {"context": source.episode["task"]}):
            child = source._transaction_copy(**kwargs)
            child.learn(self.action, self.outcome)
            self.assertEqual(source.checkpoint(), before)
            self.assertEqual(PlasticRevisionLearner.restore(source.checkpoint()).checkpoint(), before)
            self.assertIsNot(child.searches[-1]["validation"], source.searches[-1]["validation"])
            child.searches[-1]["validation"]["refresh_checks"].append({"private": True})
            self.assertEqual(source.checkpoint(), before)

    def test_late_receipt_failure_preserves_restorable_wire_state_and_can_retry(self):
        adapter, prediction = attach(self.core(), self.events)
        request = adapter.register_action(agent_proposal(prediction, self.action), executor_id="executor")
        receipt = observed_receipt(request, self.outcome)
        before = adapter.checkpoint()
        real_counter = adapter_module.wire.counter
        def failure(value, name, minimum=0):
            if name == "model revision":
                raise RuntimeError("late failure")
            return real_counter(value, name, minimum)
        with patch("first_piece.adapter.wire.counter", side_effect=failure):
            with self.assertRaises(RuntimeError):
                adapter.submit_receipt(receipt)
        self.assertEqual(adapter.checkpoint(), before)
        self.assertEqual(PlasticRevisionAdapter.restore(before).checkpoint(), before)
        ack = adapter.submit_receipt(receipt)
        self.assertEqual(ack["model_revision"], before["model_revision"] + 1)
        self.assertEqual(adapter.submit_receipt(receipt), ack)

    def test_transfer_mean_at_anchor_cut_locus_uses_neutral_replayable_point(self):
        core = PlasticRevisionLearner(max_tasks=4, max_symbols=16)
        for route, point in enumerate([unit([-1, 0, .1]), unit([-1, 0, -.1])]):
            learnable_point(point, core.active.anchors)
            core.active.points[route][0] = point
        rows = [(0, 1, 0, coin, 0, 1) for _ in range(8) for coin in (0, 1)]
        candidate, _, report = core._initialize_banks([0], rows)
        self.assertGreater(report["ambiguous_means"], 0)
        self.assertEqual(report["transferred_candidate_points"], 0)
        self.assertEqual(candidate.points[1][0], core._new_model().points[1][0])
        candidate.update(0, 1, 1)
        self.assertEqual(SharedSpherePredictor.restore(candidate.checkpoint()).checkpoint(),
                         candidate.checkpoint())

    def test_existing_deadline_criterion_rejects_confirmation_at_13000(self):
        result = confirmed_deadline()
        self.assertEqual(result["actual_delays"]["plastic_revision"]["confirmation_global_labels"], 13000)
        self.assertTrue(result["criteria_failures"])

    def test_historical_neural_update_and_live_count_corruption_is_rejected(self):
        for cls in (DistinctionLearner, TemporalLearner):
            core = cls()
            core.receive({"kind": "token", "token": 0, "task": 0})
            core.receive({"kind": "surface", "surface": "sealed", "task": 0})
            core.learn(0, 1)
            good = core.checkpoint()
            for field in ("total", "live"):
                bad = copy.deepcopy(good)
                if field == "total":
                    bad["tasks"][0]["neural_updates"] += 100
                else:
                    bad["tasks"][0]["active"]["counts"][0][0] += 1
                with self.subTest(cls=cls.__name__, field=field):
                    with self.assertRaises(ValueError):
                        cls.restore(bad)
            self.assertEqual(cls.restore(good).checkpoint(), good)

    def test_format7_import_preserves_pending_trial_forecast_and_risk(self):
        core = self.core()
        for event in self.events:
            core.receive(event)
        old = core.checkpoint()
        old["format"], old["implementation"] = 7, "first_piece.plastic-revision-s2.v2"
        with self.assertRaises(ValueError):
            PlasticRevisionLearner.restore(old)
        data = PlasticRevisionLearner.from_plastic_revision_checkpoint(old)
        new = PlasticRevisionLearner.restore(data)
        self.assertEqual(new.pending_probabilities(), core.pending_probabilities())
        self.assertEqual(new.trial, core.trial)
        self.assertEqual(new._interval_alpha(), core._interval_alpha())
        self.assertEqual(new.candidate.checkpoint(), core.candidate.checkpoint())
        self.assertEqual(data["format"], 8)

    def test_format7_wire_import_keeps_pending_request_and_duplicate_receipt(self):
        adapter, prediction = attach(self.core(), self.events)
        request = adapter.register_action(agent_proposal(prediction, self.action), executor_id="executor")
        old = adapter.checkpoint()
        old["implementation"] = "first_piece.plastic-revision-s2.v2"
        old["learner"]["format"] = 7
        old["learner"]["implementation"] = old["implementation"]
        migrated = PlasticRevisionAdapter.restore(
            PlasticRevisionAdapter.from_plastic_revision_checkpoint(old))
        self.assertEqual(migrated.current_prediction(), prediction)
        self.assertEqual(migrated.checkpoint()["pending_request"], adapter.checkpoint()["pending_request"])
        receipt = observed_receipt(request, self.outcome)
        acknowledgement = migrated.submit_receipt(receipt)
        after = migrated.checkpoint()
        self.assertEqual(migrated.submit_receipt(receipt), acknowledgement)
        self.assertEqual(migrated.checkpoint(), after)

    def test_selective_observation_copy_changes_no_parent_memory_or_banks(self):
        source = self.core()
        before = source.checkpoint()
        child = source._observation_copy()
        for event in self.events:
            child.receive(event)
        self.assertEqual(source.checkpoint(), before)
        self.assertEqual(PlasticRevisionLearner.restore(child.checkpoint()).pending_probabilities(),
                         child.pending_probabilities())
        self.assertIs(child.active, source.active)
        self.assertIsNot(child.episode, source.episode)
        self.assertIsNot(child.tasks, source.tasks)

    def test_new_context_observation_copy_owns_binding_and_calibration(self):
        core = train(PlasticRevisionLearner(100, max_tasks=8, max_symbols=16),
                     ScaleWorld(400, n_symbols=16, n_contexts=4), 10000)
        before = core.checkpoint()
        child = core._observation_copy()
        child.receive({"kind": "token", "token": core.symbols[0], "task": 4})
        self.assertNotIn(4, core.tasks)
        self.assertNotIn(4, core._calibration)
        self.assertEqual(core.checkpoint(), before)
        self.assertIn(4, child._calibration)

    def test_fit_does_not_hold_wire_lock_and_concurrent_duplicates_learn_once(self):
        adapter = PlasticRevisionAdapter()
        adapter.submit_observation(wire_symbol(0, "alpha"))
        prediction = adapter.submit_observation(wire_symbol(1, "sealed", end=True))
        request = adapter.register_action(agent_proposal(prediction, 0), executor_id="executor")
        receipt = observed_receipt(request, 1)
        entered, release, read_done = threading.Event(), threading.Event(), threading.Event()
        results, errors = [], []
        real_learn = PlasticRevisionLearner.learn
        calls = []
        def paused(core, action, outcome):
            calls.append(1)
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test did not release learner")
            return real_learn(core, action, outcome)
        def writer():
            try:
                results.append(adapter.submit_receipt(receipt))
            except BaseException as error:
                errors.append(error)
        def reader():
            try:
                snapshot = adapter.checkpoint()
                self.assertEqual(snapshot["model_revision"], 0)
                self.assertTrue(adapter.metrics(detailed=False)["pending_request"])
                self.assertEqual(PlasticRevisionAdapter.restore(snapshot).checkpoint(), snapshot)
                read_done.set()
            except BaseException as error:
                errors.append(error)
        with patch.object(PlasticRevisionLearner, "learn", paused):
            first, duplicate, read = threading.Thread(target=writer), threading.Thread(target=writer), threading.Thread(target=reader)
            first.start()
            try:
                self.assertTrue(entered.wait(2))
                duplicate.start()
                read.start()
                self.assertTrue(read_done.wait(2))
            finally:
                release.set()
                first.join(5)
                if duplicate.ident is not None:
                    duplicate.join(5)
                if read.ident is not None:
                    read.join(5)
        self.assertFalse(errors, errors)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(adapter.metrics()["model_revision"], 1)
        self.assertFalse(adapter._receipt_busy)

    def test_dense_transpose_matches_independent_bit_definition_including_partial_blocks(self):
        rng = random.Random(909)
        for symbols in (4, 16, 64, 128):
            pairs = symbols*(symbols-1)//2
            offset = symbols + pairs
            for count in (1, 7, 8, 9, 15, 16, 17, 33):
                rows = [(i % 3, rng.getrandbits(symbols), rng.getrandbits(pairs), 0, 0, 0)
                        for i in range(count)]
                expected = {}
                for i, (slot, mask, before, _, _, _) in enumerate(rows):
                    features = mask | (before << symbols) | (1 << (offset + slot))
                    while features:
                        feature = features.bit_length() - 1
                        expected[feature] = expected.get(feature, 0) | (1 << i)
                        features ^= 1 << feature
                self.assertEqual(_feature_masks(rows, symbols, offset, 3), expected)
        rows = [(0, 1, 0, 0, 0, 0)] * 32
        self.assertEqual(_feature_masks(rows, 64, 2080, 17),
                         {0: (1 << 32)-1, 2080: (1 << 32)-1})

    def test_pair_inverse_matches_every_legal_pair_and_rejects_unbound_order(self):
        for capacity in (4, 16, 64, 128):
            for a in range(capacity):
                for b in range(a+1, capacity):
                    self.assertEqual(pair_coordinates(pair_index(a, b, capacity), capacity), (a, b))
        core = SharedLearner(max_symbols=64)
        core.receive({"kind": "token", "token": "a", "task": 0})
        core.receive({"kind": "token", "token": "b", "task": 0})
        bad = core.checkpoint()
        bad["program"] = [64 + pair_index(0, 2, 64)]
        with self.assertRaises(ValueError):
            SharedLearner.restore(bad)

    def test_probability_cache_is_exact_and_detects_point_anchor_and_temperature_changes(self):
        model = SharedSpherePredictor()
        for i in range(256):
            action, route, outcome = i % 4, (i // 4) % 8, (i // 3) % 2
            expected = SpherePredictor.probability(model, action, route)
            self.assertEqual(model.probability(action, route), expected)
            model.update(action, outcome, route)
            self.assertEqual(model.probability(action, route),
                             SpherePredictor.probability(model, action, route))
        for field, value in (("point", unit([.2, .9, .1])), ("anchor", unit([.8, .2, .1])), ("temperature", .8)):
            if field == "point":
                model.points[0][0] = value
            elif field == "anchor":
                model.anchors[0] = value
            else:
                model.temperature = value
            self.assertEqual(model.probability(0, 0), SpherePredictor.probability(model, 0, 0))

    def test_summary_metrics_omit_only_detailed_history(self):
        core = self.core()
        full, summary = core.metrics(), core.metrics(detailed=False)
        full.pop("decisions")
        full.pop("searches")
        self.assertEqual(summary, full)

if __name__ == "__main__":
    unittest.main()
