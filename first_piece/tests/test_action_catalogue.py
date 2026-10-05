"""Catalogue, budget, causal validation, copy isolation and migration regressions."""
import copy
import json
import math
import random
import unittest
from unittest.mock import patch

from first_piece.action_bank import ActionSpherePredictor
from first_piece.action_trace import ActionTraceLearner, gain_width, LAMBDAS
from first_piece.action_service import ActionTraceAdapter, ActionTraceService
from first_piece.action_work import ActionFitWork
from first_piece.adaptive_trace_v2 import AdaptiveTraceLearnerV2
from first_piece.trace_service import AdaptiveTraceService
from first_piece.tests.test_trace_v2 import feed, feed_wire
from first_piece.tests.test_readiness import trace
from first_piece.integration_probe import agent_proposal, observed_receipt
from first_piece.cooperative import sealed


def actions(n):
    return tuple(f"action:{i}" for i in range(n))


class ActionCatalogueTests(unittest.TestCase):
    def test_sphere_bank_works_beyond_sixteen_and_restores(self):
        bank = ActionSpherePredictor(n_actions=128,point_budget=1024)
        for _ in range(128):
            bank.update(127,1,0)
        self.assertGreater(bank.probability(127,0),.9)
        restored = ActionSpherePredictor.restore(json.loads(json.dumps(bank.checkpoint())))
        self.assertEqual(bank.checkpoint(),restored.checkpoint())
        self.assertEqual(bank.probability(127,0),restored.probability(127,0))
        with self.assertRaises(ValueError):
            ActionSpherePredictor(n_actions=128,point_budget=255)


    def test_full_tree_and_live_trial_fit_declared_point_reservation(self):
        core = ActionTraceLearner(n_actions=32)
        pending = [(0,0)]
        next_index = 1
        while pending:
            index,depth = pending.pop(0)
            node = core._node(depth)
            node["protected"] = copy.deepcopy(node["bank"])
            core.nodes[index] = node
            if depth < 3:
                children = [next_index,next_index+1]
                next_index += 2
                node["children"],node["centers"] = children, [[1.,0.,0.],[0.,1.,0.]]
                pending.extend((child,depth+1) for child in children)
        core.trial = {"candidate":core._bank(),"control":core._bank(),
                      "reference":core._bank(),"n":0}
        m = core.metrics()
        self.assertEqual(8,m["leaves"])
        self.assertLessEqual(m["allocated_s2_points"],m["reserved_s2_points"])

    def test_resource_budgets_reject_before_bank_allocation(self):
        for options in ({"n_actions":32,"point_budget":100},
                        {"n_actions":64},{"n_actions":4,"window":256,"min_records":512},
                        {"n_actions":32,"min_records":128}):
            with patch.object(ActionSpherePredictor,"__init__",side_effect=AssertionError("allocated")):
                with self.assertRaises(ValueError):
                    ActionTraceLearner(**options)
        core = ActionTraceLearner(n_actions=128,max_tasks=1,max_leaves=2)
        m = core.metrics()
        self.assertLessEqual(m["reserved_s2_points"],m["point_budget"])
        self.assertLessEqual(m["reserved_record_slots"],m["record_budget"])

    def test_named_catalogue_matches_outputs_and_higher_action_receipt(self):
        service = ActionTraceService(actions=actions(32))
        p,sequence = feed_wire(service,trace(1),0)
        self.assertEqual(32,len(p["forecasts"]))
        self.assertEqual("action:31",p["forecasts"][-1]["action_name"])
        req = service.register_action(agent_proposal(p,31),executor_id="test:executor")
        receipt = observed_receipt(req,1)
        self.assertEqual(1,service.submit_receipt(receipt)["model_revision"])
        p,sequence = feed_wire(service,trace(1),sequence)
        c = service.coverage()
        self.assertEqual(32,len(c["actions"]))
        self.assertEqual(1,c["actions"][-1]["observations"])
        self.assertEqual(0,sum(a["observations"] for a in c["actions"][:-1]))
        cp = service.checkpoint()
        restored = ActionTraceService.restore(json.loads(json.dumps(cp)))
        self.assertEqual(cp,restored.checkpoint())
        with self.assertRaises(ValueError):
            ActionTraceService(actions=actions(4),learner_options={"n_actions":8})

    def test_sparse_past_rows_and_variable_width_radius_are_validated(self):
        core = ActionTraceLearner(n_actions=8)
        for i in range(1024):
            feed(core,trace(i%2))
            a = (i//2)%8
            core.learn(a,int(a == (0 if i%2 == 0 else 7)))
        cp = core.checkpoint()
        self.assertEqual(cp,ActionTraceLearner.restore(json.loads(json.dumps(cp))).checkpoint())
        self.assertEqual(16,len(LAMBDAS))
        self.assertEqual(0,gain_width(.001,.009))  # Both hypothetical scores clipped identically.
        self.assertGreater(gain_width(.99,.5),4)
        if cp["trial"] is not None:
            bad = copy.deepcopy(cp)
            bad["trial"]["width_squares"]["improvement"] = -1
            with self.assertRaises(ValueError):
                ActionTraceLearner.restore(bad)

    def test_service_and_direct_are_exact_across_fit_phases(self):
        for n in (4,8,32):
            core = ActionTraceLearner(9,n_actions=n)
            service = ActionTraceService(seed=9,actions=actions(n))
            rng,sequence,seen = random.Random(9),0,set()
            for i in range(64*n+256):
                events = trace(i%2,(i//2)%4)
                expected = feed(core,events)
                p,sequence = feed_wire(service,events,sequence)
                self.assertEqual(expected,[f["distribution"]["parameters"]["p"] for f in p["forecasts"]])
                a = rng.randrange(n)
                y = int(a%2 == i%2)
                core.learn(a,y)
                req = service.register_action(agent_proposal(p,a),executor_id="test:executor")
                receipt = observed_receipt(req,y)
                before = service._adapter.checkpoint()
                service.begin_receipt(receipt)
                while service._work is not None:
                    w = service._work
                    key = (w.phase,None if w.fit is None else (w.fit.phase,w.fit.epoch,w.fit.bank,w.fit.mean_group))
                    fresh = key not in seen
                    if fresh:
                        self.assertEqual(before,service._adapter.checkpoint())
                        service = ActionTraceService.restore(json.loads(json.dumps(service.checkpoint())))
                        seen.add(key)
                    status = service.advance(1)
                    self.assertLessEqual(status["consumed_units"],1)
                    if service._work is not None and fresh:
                        self.assertEqual(before,service._adapter.checkpoint())
                self.assertEqual(core.checkpoint(),service._adapter._learner.checkpoint())
            self.assertTrue(any(k[0] == "fit" for k in seen),n)
            saved = service.checkpoint()
            service.submit_receipt(receipt)
            self.assertEqual(saved,service.checkpoint())

    def test_receipt_copy_isolation_and_retry_preserve_parent(self):
        service = ActionTraceService(actions=actions(8))
        p,_ = feed_wire(service,trace(0),0)
        req = service.register_action(agent_proposal(p,7),executor_id="test:executor")
        receipt = observed_receipt(req,1)
        before = service._adapter.checkpoint()
        candidate = service._adapter._fork_learner(context=0)
        candidate.learn(7,1)
        self.assertEqual(before,service._adapter.checkpoint())
        service.begin_receipt(receipt)
        original = ActionTraceLearner.learn
        def broken(core,*args,**kw):
            original(core,*args,**kw)
            raise RuntimeError("private failure")
        with patch.object(ActionTraceLearner,"learn",broken):
            with self.assertRaises(RuntimeError):
                service.advance(1)
        self.assertEqual(before,service._adapter.checkpoint())
        self.assertEqual(1,service.submit_receipt(receipt)["model_revision"])

    def test_import_v2_pending_prediction_action_and_trial_keeps_legacy_policy(self):
        old = AdaptiveTraceService(seed=7)
        sequence = 0
        for i in range(160):
            p,sequence = feed_wire(old,trace(i%2),sequence)
            a = (i//2)%2
            req = old.register_action(agent_proposal(p,a),executor_id="test:executor")
            old.submit_receipt(observed_receipt(req,int(a == i%2)))
        self.assertIsNotNone(old._adapter._learner.trial)
        p,sequence = feed_wire(old,trace(0),sequence)
        req = old.register_action(agent_proposal(p,0),executor_id="test:executor")
        new = ActionTraceService.from_v2(json.loads(json.dumps(old.checkpoint())))
        self.assertEqual(p,new.current_prediction())
        self.assertEqual(req,new._adapter._pending)
        self.assertEqual("legacy",new._adapter._learner.trial["validation"])
        receipt = observed_receipt(req,1)
        self.assertEqual(old.submit_receipt(receipt),new.submit_receipt(receipt))
        self.assertEqual(old._adapter._learner.nodes[0]["bank"].points,new._adapter._learner.nodes[0]["bank"].points)
        self.assertEqual(old._adapter._learner.trial["n"],new._adapter._learner.trial["n"])

    def test_import_v2_partial_fit_resumes_same_frozen_candidate(self):
        old = AdaptiveTraceService(seed=7)
        sequence = 0
        for i in range(128):
            p,sequence = feed_wire(old,trace(i%2),sequence)
            a = (i//2)%2
            req = old.register_action(agent_proposal(p,a),executor_id="test:executor")
            receipt = observed_receipt(req,int(a == i%2))
            old.begin_receipt(receipt)
            if i < 127:
                old.submit_receipt(receipt)
        while old._work.fit is None or old._work.fit.phase != "replay":
            old.advance(1)
        old.advance(17)
        new = ActionTraceService.from_v2(json.loads(json.dumps(old.checkpoint())))
        self.assertEqual(old.current_prediction(),new.current_prediction())
        self.assertEqual(old.submit_receipt(receipt),new.submit_receipt(receipt))
        for name in ("candidate","control","reference"):
            self.assertEqual(old._adapter._learner.trial[name].points,new._adapter._learner.trial[name].points)

    def test_128_actions_forecast_and_restore_with_explicit_budget(self):
        service = ActionTraceService(actions=actions(128),
            learner_options={"max_tasks":1,"max_leaves":2})
        p,_ = feed_wire(service,trace(0),0)
        self.assertEqual(128,len(p["forecasts"]))
        clone = ActionTraceService.restore(json.loads(json.dumps(service.checkpoint())))
        self.assertEqual(p,clone.current_prediction())
        self.assertEqual(128,clone.capabilities()["action_count"])
