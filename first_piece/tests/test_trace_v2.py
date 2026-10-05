"""Behavioral regression tests for calibrated/revisable trace integration."""
import copy
import json
import math
import random
import unittest
from unittest.mock import patch

from first_piece.adaptive_trace_v2 import AdaptiveTraceLearnerV2, calibrated, fresh_readout, add_readout
from first_piece.trace_service import AdaptiveTraceAdapter, AdaptiveTraceService
from first_piece.trace_work import TraceFitWork
from first_piece.cooperative import sealed
from first_piece.integration_probe import agent_proposal, observed_receipt
from first_piece.tests.test_shared import wire_symbol
from first_piece.tests.test_readiness import trace


def feed(core, events):
    p = None
    for event in events:
        p = core.receive(event)
    return p


def feed_wire(service, events, sequence):
    p = None
    for event in events:
        p = service.submit_observation(wire_symbol(sequence, event.get("token", "sealed"),
            context=f"ctx:{event['task']}", end=event["kind"] == "surface"))
        sequence += 1
    return p, sequence


def train(core, n, seed=4, reverse=False, noise=False):
    rng = random.Random(seed)
    for i in range(n):
        target = i%2
        p = feed(core, trace(target, i%4))
        action = rng.randrange(2)
        y = rng.randrange(2) if noise else int(action == (1-target if reverse else target))
        core.learn(action, y)
    return core


def accuracy(core, reverse=False):
    count = 0
    loss = []
    for i in range(256):
        target = i%2
        p = feed(core, trace(target, i%4))
        label = 1-target if reverse else target
        count += max(range(2), key=p.__getitem__) == label
        loss.extend((p[a]-int(a == label))**2 for a in range(2))
        core.finish_evaluation()
    return count/256, math.fsum(loss)/len(loss)


class TraceV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acquired = train(AdaptiveTraceLearnerV2(3), 8192)

    def test_calibration_reduces_noise_confidence_and_preserves_rank(self):
        cal = fresh_readout()
        for i in range(256):
            add_readout(cal, .99 if i%2 else .01, int(i%4 < 2))
        self.assertLess(abs(calibrated(cal, .99)-.5), .01)
        self.assertGreater(calibrated(cal, .99), calibrated(cal, .01))
        self.assertEqual(256, len(cal["rows"]))

    def test_impossible_fit_and_unsupported_capacities_rejected(self):
        for options in ({"window":128, "min_records":256}, {"max_tasks":9},
                        {"max_symbols":65}, {"calibration_window":31}):
            with self.assertRaises(ValueError):
                AdaptiveTraceLearnerV2(**options)

    def test_noise_does_not_replace_weights_and_competence_survives(self):
        core = copy.deepcopy(self.acquired)
        self.assertGreaterEqual(accuracy(copy.deepcopy(core))[0], .95)
        before = {k: n["protected"].checkpoint() for k, n in core.nodes.items() if n["protected"] is not None}
        count = core.admissions+core.revisions
        train(core, 8192, seed=93, noise=True)
        self.assertEqual(count, core.admissions+core.revisions)
        self.assertEqual(before, {k: n["protected"].checkpoint() for k, n in core.nodes.items() if n["protected"] is not None})
        self.assertGreaterEqual(accuracy(copy.deepcopy(core))[0], .95)
        for target in range(2):
            p = feed(core, trace(target, target))
            self.assertLess(max(abs(v-.5) for v in p), .12)
            core.finish_evaluation()
        self.assertEqual(core.checkpoint(), AdaptiveTraceLearnerV2.restore(
            json.loads(json.dumps(core.checkpoint()))).checkpoint())

    def test_real_rule_reversal_revises_protected_weights(self):
        core = copy.deepcopy(self.acquired)
        splits = core.admissions
        train(core, 32768, seed=15, reverse=True)
        score, loss = accuracy(copy.deepcopy(core), reverse=True)
        self.assertGreaterEqual(core.revisions, 1)
        self.assertGreaterEqual(score, .95)
        self.assertLess(loss, .02)
        self.assertEqual(splits, core.admissions)

    def test_cooperative_forecasts_state_and_all_fit_phases_resume_exactly(self):
        core = AdaptiveTraceLearnerV2(11)
        service = AdaptiveTraceService(seed=11)
        sequence = 0
        rng = random.Random(16)
        seen = set()
        for i in range(512):
            events = trace(i%2, i%4)
            expected = feed(core, events)
            p, sequence = feed_wire(service, events, sequence)
            self.assertEqual(expected, [f["distribution"]["parameters"]["p"] for f in p["forecasts"]])
            action, y = rng.randrange(2), i%2
            outcome = int(action == y)
            core.learn(action, outcome)
            request = service.register_action(agent_proposal(p, action), executor_id="test:executor")
            receipt = observed_receipt(request, outcome)
            before = service._adapter.checkpoint()
            service.begin_receipt(receipt)
            while service._work is not None:
                w = service._work
                key = (w.phase, None if w.fit is None else (w.fit.phase, w.fit.mean_group,
                                                            w.fit.epoch, w.fit.bank))
                if key not in seen:
                    service = AdaptiveTraceService.restore(json.loads(json.dumps(service.checkpoint())))
                    seen.add(key)
                status = service.advance(1)
                self.assertLessEqual(status["consumed_units"], 1)
                if service._work is not None:
                    self.assertEqual(before, service._adapter.checkpoint())
                    self.assertEqual(p, service.current_prediction())
            self.assertEqual(core.checkpoint(), service._adapter._learner.checkpoint())
        phases = {key[1][0] for key in seen if key[1] is not None}
        self.assertTrue({"farthest_a", "farthest_b", "group", "mean", "support",
                         "shuffle", "replay", "publish"} <= phases, phases)
        saved = service.checkpoint()
        self.assertEqual(service.submit_receipt(receipt)["model_revision"], 512)
        self.assertEqual(saved, service.checkpoint())

    def test_revision_replay_resumes_and_partial_corruption_rejected(self):
        core = copy.deepcopy(self.acquired)
        leaf = next(k for k, n in core.nodes.items() if n["children"] is None)
        if core.trial is not None:
            core.trial = None
        direct = TraceFitWork(copy.deepcopy(core), leaf, "revision")
        paused = TraceFitWork(copy.deepcopy(core), leaf, "revision")
        while direct.phase != "done":
            direct.advance()
        seen = set()
        while paused.phase != "done":
            key = (paused.phase, paused.epoch, paused.bank)
            if key not in seen:
                checkpoint = json.loads(json.dumps(paused.checkpoint()))
                clone = copy.deepcopy(checkpoint)
                clone["data"]["gradients"] += 1
                with self.assertRaises(ValueError):
                    TraceFitWork.restore(clone)
                paused = TraceFitWork.restore(checkpoint)
                seen.add(key)
            paused.advance()
        self.assertEqual(direct.core.checkpoint(), paused.core.checkpoint())
        self.assertEqual(2*len(direct.rows)*core.config["replay_passes"], direct.gradients)

    def test_checkpoint_rejects_exposure_calibration_and_last_token_corruption(self):
        core = copy.deepcopy(self.acquired)
        feed(core, trace(0, 0))
        cp = core.checkpoint()
        paths = ("neural_updates", "last_token", "history", "cals")
        for path in paths:
            bad = copy.deepcopy(cp)
            if path == "neural_updates":
                bad[path] += 1
            elif path == "last_token":
                bad[path] = "absent"
            elif path == "history":
                bad[path]["0"].pop()
            else:
                key = next(iter(bad[path]))
                bad[path][key]["sums"][0] += 1
            with self.assertRaises(ValueError):
                AdaptiveTraceLearnerV2.restore(bad)

    def test_service_coverage_is_real_and_failure_retries_same_receipt(self):
        service = AdaptiveTraceService(seed=11, minimum_observations=2)
        p, sequence = feed_wire(service, trace(0), 0)
        coverage = service.coverage()
        self.assertEqual([0, 0], [a["observations"] for a in coverage["actions"]])
        req = service.register_action(agent_proposal(p, 0), executor_id="test:executor")
        receipt = observed_receipt(req, 1)
        before = service._adapter.checkpoint()
        service.begin_receipt(receipt)
        with patch.object(AdaptiveTraceLearnerV2, "learn", side_effect=RuntimeError("unit failed")):
            with self.assertRaises(RuntimeError):
                service.advance(1)
        self.assertEqual(before, service._adapter.checkpoint())
        self.assertEqual("feedback", service._work.phase)
        self.assertEqual(1, service.submit_receipt(receipt)["model_revision"])
        p, sequence = feed_wire(service, trace(0), sequence)
        coverage = service.coverage()
        self.assertEqual([1, 0], [a["observations"] for a in coverage["actions"]])
        saved = service.checkpoint()
        restored = AdaptiveTraceService.from_adapter_checkpoint(
            json.loads(json.dumps(saved["adapter"])), minimum_observations=2)
        self.assertEqual(saved["adapter"], restored.checkpoint()["adapter"])
        self.assertEqual(p, restored.current_prediction())

    def test_observation_fork_isolates_context_rng_and_vocabulary(self):
        adapter = AdaptiveTraceAdapter(seed=2)
        candidate = adapter._fork_learner(observation=True)
        candidate.receive({"kind":"token", "token":"new", "task":0})
        self.assertEqual({}, adapter._learner.symbols)
        self.assertEqual({}, adapter._learner.contexts)
        self.assertEqual("idle", adapter._learner.phase)
        self.assertNotEqual(candidate.rng.getstate(), adapter._learner.rng.getstate())

    def test_resealed_invalid_support_and_partial_mean_are_rejected(self):
        core = train(AdaptiveTraceLearnerV2(8), 128)
        self.assertIsNotNone(core.trial)
        cp = core.checkpoint()
        cp["trial"]["support"] = [[-1, 1], [0, 0]]
        with self.assertRaises(ValueError):
            AdaptiveTraceLearnerV2.restore(cp)
        core.trial = None
        job = TraceFitWork(core, 0, "split")
        while job.phase != "mean":
            job.advance()
        data = job.checkpoint()["data"]
        data["q"] = [0.0, 0.0, 0.0]
        with self.assertRaises(ValueError):
            TraceFitWork.restore(sealed(data))

    def test_old_wire_and_wrong_backend_checkpoints_are_rejected(self):
        from first_piece.cooperative import CooperativeService
        service = AdaptiveTraceService()
        with self.assertRaises(ValueError):
            service.submit_observation({"schema_version":1, "event_id":"one",
                "stream_id":"one", "sequence":0, "context_id":"one", "source_id":"test:sensor",
                "kind":"lab.token", "payload":{"value":0}})
        with self.assertRaises(ValueError):
            AdaptiveTraceService.restore(CooperativeService().checkpoint())
        with self.assertRaises(ValueError):
            CooperativeService.restore(service.checkpoint())
        self.assertFalse(service.capabilities()["autonomous_execution"])
