"""Resource scaling and observed-coverage frontier regressions."""
import copy
import json
import unittest
from unittest.mock import patch

from first_piece.action_bank import ActionSpherePredictor
from first_piece.action_trace import ActionTraceLearner
from first_piece.action_service import ActionTraceService
from first_piece.scalable_service import ScalableActionService
from first_piece.coverage import CoverageLedger
from first_piece.action_work import ActionFitWork
from first_piece.tests.test_trace_v2 import feed, feed_wire
from first_piece.tests.test_action_catalogue import actions
from first_piece.tests.test_readiness import trace
from first_piece.integration_probe import agent_proposal, observed_receipt


def one_symbol(token, context=0):
    return [{"kind": "token", "token": token, "task": context},
            {"kind": "surface", "surface": "sealed", "task": context}]


def perform(service, sequence, action=0, outcome=1, events=None):
    p, sequence = feed_wire(service, trace(0) if events is None else events, sequence)
    request = service.register_action(agent_proposal(p, action), executor_id="test:executor")
    receipt = observed_receipt(request, outcome)
    service.submit_receipt(receipt)
    return sequence, receipt


class ResourceScaleTests(unittest.TestCase):
    def test_actual_ingestion_crosses_old_context_and_symbol_caps(self):
        core = ActionTraceLearner(adaptive=False, max_tasks=32, max_symbols=256,
            max_leaves=32, max_depth=12, record_budget=1000000)
        for i in range(256):
            feed(core, one_symbol(f"opaque:{i}", i%32))
            core.learn(i%2, i%2)
        self.assertEqual(256, len(core.symbols))
        self.assertEqual(32, len(core.contexts))
        restored = ActionTraceLearner.restore(json.loads(json.dumps(core.checkpoint())))
        self.assertEqual(core.checkpoint(), restored.checkpoint())
        before = restored.checkpoint()
        with self.assertRaises(ValueError):
            restored.receive({"kind": "token", "token": "one-too-many", "task": 0})
        self.assertEqual(before, restored.checkpoint())
        with self.assertRaises(ValueError):
            restored.receive({"kind": "token", "token": "opaque:0", "task": 32})
        self.assertEqual(before, restored.checkpoint())

    def test_resource_limits_reject_large_structures_before_neural_allocation(self):
        for opts in ({"max_symbols": 1000000}, {"max_tasks": 1000000},
                     {"max_leaves": 1000000}, {"max_depth": True}):
            with patch.object(ActionSpherePredictor, "__init__", side_effect=AssertionError("allocated")):
                with self.assertRaises(ValueError):
                    ActionTraceLearner(**opts)
        with patch.object(ActionSpherePredictor, "__init__", side_effect=AssertionError("allocated")):
            with self.assertRaises(ValueError):
                ScalableActionService(actions=actions(32), coverage_window=128)
        with self.assertRaises(ValueError):
            ScalableActionService(minimum_observations=33, coverage_window=32)

    def test_deep_restore_uses_iterative_topology_validation(self):
        # Synthetic topology fixture, not evidence of 1,100 learned distinctions.
        core = ActionTraceLearner(adaptive=False, max_tasks=1, max_leaves=1101,
            max_depth=1100, record_budget=1000000)
        core.nodes = {}
        for depth in range(1100):
            index = 2*depth
            branch = core._node(depth)
            branch["children"], branch["centers"] = [index+2, index+1], [[1.,0.,0.], [0.,1.,0.]]
            core.nodes[index] = branch
            core.nodes[index+1] = core._node(depth+1)
        core.nodes[2200] = core._node(1100)
        core.admissions = core.attempts = 1100
        core.fit_records_total = 1100*core.config["min_records"]
        core.neural_updates = 2*core.config["replay_passes"]*core.fit_records_total
        cp = core.checkpoint()
        self.assertEqual(cp, ActionTraceLearner.restore(json.loads(json.dumps(cp))).checkpoint())
        bad = copy.deepcopy(cp)
        bad["nodes"]["2198"]["children"][0] = 0
        with self.assertRaises(ValueError):
            ActionTraceLearner.restore(bad)

    def test_all_32_actions_can_reach_coverage_without_enlarging_calibration(self):
        service = ScalableActionService(actions=actions(32), learner_options={"adaptive": False})
        seq = 0
        for i in range(1024):
            seq, receipt = perform(service, seq, i%32, int(i%32 == 31))
        p, seq = feed_wire(service, trace(0), seq)
        coverage = service.coverage(p["prediction_id"])
        self.assertTrue(all(a["observations"] == 32 and a["coverage_status"] == "observed"
                            for a in coverage["actions"]))
        self.assertEqual(32, coverage["actions"][-1]["positive_outcomes"])
        self.assertEqual(256, len(service._adapter._learner.history[0]))
        self.assertIsNone(coverage["epistemic_interval"])
        cp = service.checkpoint()
        service.submit_receipt(receipt)
        self.assertEqual(cp, service.checkpoint())
        restored = ScalableActionService.restore(json.loads(json.dumps(cp)))
        self.assertEqual(cp, restored.checkpoint())
        self.assertEqual(coverage, restored.coverage())

    def test_coverage_window_ages_and_contexts_do_not_mix(self):
        service = ScalableActionService(minimum_observations=2, coverage_window=2,
            coverage_max_age=4, learner_options={"adaptive": False})
        seq, _ = perform(service, 0, 0, 1)
        seq, _ = perform(service, seq, 0, 0)
        for _ in range(4):
            seq, _ = perform(service, seq, 1, 1, one_symbol("different", 1))
        p, seq = feed_wire(service, trace(0), seq)
        c = service.coverage()
        self.assertEqual(0, c["actions"][0]["observations"])
        self.assertEqual(0, c["actions"][1]["observations"])
        self.assertEqual(service.checkpoint(), ScalableActionService.restore(
            json.loads(json.dumps(service.checkpoint()))).checkpoint())

    def test_invalid_coverage_snapshot_cannot_create_duplicate_evidence(self):
        service = ScalableActionService(learner_options={"adaptive": False})
        perform(service, 0)
        cp = service.checkpoint()
        key = next(iter(cp["coverage"]["buckets"]))
        for transform in ("duplicate", "future", "outcome", "window", "context"):
            bad = copy.deepcopy(cp)
            rows = bad["coverage"]["buckets"][key]
            if transform == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            elif transform == "future":
                rows[0][0] += 1
            elif transform == "outcome":
                rows[0][2] = True
            elif transform == "window":
                bad["coverage"]["window"] = 0
            else:
                bad["coverage"]["buckets"]["0:7:0"] = bad["coverage"]["buckets"].pop(key)
            with self.assertRaises(ValueError):
                ScalableActionService.restore(bad)

    def test_split_reindexes_real_labels_without_counting_replay(self):
        old = ActionTraceLearner(adaptive=False)
        ledger = CoverageLedger(old)
        for token in ("cedar", "quartz"):
            feed(old, one_symbol(token))
            candidate = copy.deepcopy(old)
            candidate.learn(0, 1)
            ledger = ledger.after_receipt(old, candidate, 0, 1)
            old = candidate
        new = copy.deepcopy(old)
        new.nodes[0]["children"] = [1, 2]
        states = [row[1] for rows in ledger.buckets.values() for row in rows]
        new.nodes[0]["centers"] = states
        for i in (1, 2):
            new.nodes[i] = new._node(1)
        new.admissions += 1
        feed(old, one_symbol("cedar"))
        new.state, new.context = list(old.state), old.context
        new.steps += 1
        updated = ledger.after_receipt(old, new, 0, 0)
        self.assertFalse(any(key[0] == 0 for key in updated.buckets))
        self.assertEqual(3, sum(map(len, updated.buckets.values())))
        self.assertEqual(2, sum(map(len, ledger.buckets.values())))
        self.assertEqual(2, len({key[0] for key in updated.buckets}))

    def test_private_failure_and_cancelled_receipt_do_not_add_coverage(self):
        service = ScalableActionService()
        p, seq = feed_wire(service, trace(0), 0)
        req = service.register_action(agent_proposal(p, 0), executor_id="test:executor")
        receipt = observed_receipt(req, 1)
        before = service.checkpoint()
        service.begin_receipt(receipt)
        original = ActionTraceLearner.learn
        def broken(core, *args, **kw):
            original(core, *args, **kw)
            raise RuntimeError("private failure")
        with patch.object(ActionTraceLearner, "learn", broken):
            with self.assertRaises(RuntimeError):
                service.advance(1)
        self.assertEqual(before["coverage"], service.checkpoint()["coverage"])
        self.assertEqual(before["adapter"], service.checkpoint()["adapter"])
        service.submit_receipt(receipt)
        self.assertEqual(1, sum(map(len, service._coverage.buckets.values())))
        p, seq = feed_wire(service, trace(1), seq)
        req = service.register_action(agent_proposal(p, 1), executor_id="test:executor")
        failed = {"schema_version": 1, "receipt_id": "cancelled:1",
                  "request_id": req["request_id"], "source_id": req["executor_id"],
                  "status": "cancelled", "outcome": None}
        service.submit_receipt(failed)
        self.assertEqual(1, sum(map(len, service._coverage.buckets.values())))

    def test_v3_pending_fit_import_preserves_prediction_and_does_not_invent_labels(self):
        old = ActionTraceService(seed=7)
        seq = 0
        for i in range(128):
            p, seq = feed_wire(old, trace(i%2), seq)
            action = (i//2)%2
            req = old.register_action(agent_proposal(p, action), executor_id="test:executor")
            receipt = observed_receipt(req, int(action == i%2))
            old.begin_receipt(receipt)
            if i < 127:
                old.submit_receipt(receipt)
        while old._work.fit is None or old._work.fit.phase != "replay":
            old.advance(1)
        old.advance(17)
        new = ScalableActionService.from_v3(json.loads(json.dumps(old.checkpoint())))
        self.assertEqual(old.current_prediction(), new.current_prediction())
        self.assertEqual(0, sum(map(len, new._coverage.buckets.values())))
        self.assertEqual(127, new._coverage.started_at)
        new = ScalableActionService.restore(json.loads(json.dumps(new.checkpoint())))
        self.assertEqual(old.submit_receipt(receipt), new.submit_receipt(receipt))
        self.assertEqual(old._adapter._learner.checkpoint(), new._adapter._learner.checkpoint())
        self.assertEqual(1, sum(map(len, new._coverage.buckets.values())))

    def test_coverage_and_model_publish_together_after_partition_and_replay(self):
        service = ScalableActionService(seed=7)
        seq, seen = 0, set()
        for i in range(144):
            p, seq = feed_wire(service, trace(i%2), seq)
            action = (i//2)%2
            req = service.register_action(agent_proposal(p, action), executor_id="test:executor")
            receipt = observed_receipt(req, int(action == i%2))
            before = service.checkpoint()
            service.begin_receipt(receipt)
            while service._work is not None:
                fit = service._work.fit
                phase = None if fit is None else fit.phase
                if phase not in seen:
                    service = ScalableActionService.restore(json.loads(json.dumps(service.checkpoint())))
                    seen.add(phase)
                service.advance(128)
                if service._work is not None:
                    cp = service.checkpoint()
                    self.assertEqual(before["adapter"], cp["adapter"])
                    self.assertEqual(before["coverage"], cp["coverage"])
            self.assertEqual(i+1, service._adapter._learner.steps)
        self.assertIn("replay", seen)
        self.assertLessEqual(sum(map(len, service._coverage.buckets.values())),
                            service._coverage.reserved_slots)


if __name__ == "__main__":
    unittest.main()
