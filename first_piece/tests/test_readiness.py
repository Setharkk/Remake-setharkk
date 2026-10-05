"""Resume, isolation, observed coverage and experimental-state invariants."""
import copy
import json
import random
import unittest
from unittest.mock import patch

from first_piece.cooperative import CooperativeService, ReceiptWork, SearchWork, canonical, rows_of, sealed
from first_piece.plastic_revision import PlasticRevisionLearner
from first_piece.adaptive_trace import AdaptiveTraceLearner, encoded_state
from first_piece.scale_world import ScaleWorld
from first_piece.tests.test_shared import train, wire_symbol
from first_piece.integration_probe import agent_proposal, observed_receipt
from validation.plastic_revision_review import collect_boundary
from setharkk import contracts as wire


def feed(service,events,start=0):
    p = None
    for sequence,event in enumerate(events,start):
        p = service.submit_observation(wire_symbol(sequence,
            event.get("token","sealed"), context=f"ctx:{event['task']}",
            end=event["kind"] == "surface"))
    return p


def attach(core):
    service = CooperativeService()
    service._adapter._learner = core
    service._adapter._revision = core.steps
    service._adapter._slots = {f"ctx:{slot}":slot for slot in sorted(core.tasks)}
    return service


def trace(target,context=0,prefix=None):
    a,b = "opaque.alpha","opaque.beta"
    tokens = (prefix or [a,b,"opaque.noise"]) + ([a,a,b] if target == 0 else [a,b,b])
    return [{"kind":"token","token":token,"task":context} for token in tokens]+[
        {"kind":"surface","surface":"sealed","task":context}]


class ReadinessTests(unittest.TestCase):
    def test_incremental_search_keeps_exact_program_and_examined_count(self):
        for features in (1,2,3):
            core = train(PlasticRevisionLearner(7,max_tasks=4,max_symbols=16,max_features=features),
                         ScaleWorld(92,n_symbols=16,n_contexts=4),517)
            for scope in (None,2):
                reference = copy.deepcopy(core)
                expected = reference._search(rows_of(core),scope=scope)
                job = SearchWork(core,rows_of(core),scope,core.attempts)
                phases = set()
                while job.phase != "done":
                    phases.add(job.phase)
                    job.advance()
                    if len(phases) and job.examined % 53 == 0:
                        job = SearchWork.restore(core,rows_of(core),scope,core.attempts,
                                                 json.loads(json.dumps(job.checkpoint())))
                result = job.report()
                self.assertEqual(result["program"],expected)
                for field in ("fit_records","eligible_features","pooled_features","hypotheses_examined"):
                    self.assertEqual(result[field],reference.searches[-1][field])
                self.assertIn("masks",phases)

    def test_empty_pool_can_resume_pair_and_triple_administration(self):
        core = train(PlasticRevisionLearner(0,max_tasks=1,max_symbols=4),
                     ScaleWorld(0,n_symbols=4,n_contexts=1),64)
        # Empty input is a valid search operation even though feedback requires support.
        reference = copy.deepcopy(core)
        expected = reference._search([])
        work = SearchWork(core,[],None,core.attempts)
        while work.phase != "done":
            work = SearchWork.restore(core,[],None,core.attempts,
                                      json.loads(json.dumps(work.checkpoint())))
            work.advance()
        self.assertIsNone(expected)
        self.assertIsNone(work.report()["program"])

    def test_real_initial_trial_all_phases_resume_without_served_mutation(self):
        core = train(PlasticRevisionLearner(5,max_tasks=4,max_symbols=16),
                     ScaleWorld(400,n_symbols=16,n_contexts=4),511)
        events,target = ScaleWorld(712,n_symbols=16,n_contexts=4).episode(3)
        # Reuse known vocabulary, not another world's opaque symbols.
        events,target = ScaleWorld(400,n_symbols=16,n_contexts=4).episode(3)
        reference = copy.deepcopy(core)
        for event in events:
            reference.receive(event)
        service = attach(core)
        p = feed(service,events)
        req = service.register_action(agent_proposal(p,0),executor_id="test:executor")
        receipt = observed_receipt(req,int(target == 0))
        before = service._adapter.checkpoint()
        service = CooperativeService.from_adapter_checkpoint(json.loads(json.dumps(before)))
        self.assertEqual(before,service.checkpoint()["adapter"])
        reference.learn(0,int(target == 0))
        service.begin_receipt(receipt)
        self.assertEqual(service.begin_receipt(copy.deepcopy(receipt))["state"],"working")
        phases = set()
        checkpoints = set()
        while service.work_status()["state"] == "working":
            phase = service._work.phase
            phases.add(phase)
            key = (phase,service._work.search.phase if phase == "search" else
                   (service._work.fit["bank"],service._work.fit["epoch"]) if phase in ("replay","shuffle","finalize") else None)
            if key not in checkpoints:
                checkpoints.add(key)
                service = CooperativeService.restore(json.loads(json.dumps(service.checkpoint())))
            result = service.advance(1)
            self.assertLessEqual(result["consumed_units"],1)
            if result["state"] == "working":
                self.assertEqual(before,service._adapter.checkpoint())
                self.assertEqual(p,service.current_prediction())
        self.assertTrue({"search","initialize","shuffle","replay","finalize"} <= phases)
        self.assertEqual(canonical(reference),canonical(service._adapter._learner))
        state = service.checkpoint()
        duplicate = copy.deepcopy(receipt)
        duplicate["receipt_id"] += ":again"
        self.assertEqual(service.begin_receipt(duplicate)["ack"],result["ack"])
        self.assertEqual(state,service.checkpoint())

    def test_prospective_boundary_and_late_commit_failure_are_isolated(self):
        core,events,action,outcome = collect_boundary()
        reference = copy.deepcopy(core)
        service = attach(core)
        p = feed(service,events)
        req = service.register_action(agent_proposal(p,action),executor_id="test:executor")
        for event in events:
            reference.receive(event)
        reference.learn(action,outcome)
        before = service._adapter.checkpoint()
        service.begin_receipt(observed_receipt(req,outcome))
        real = wire.counter
        def fail(value,name,minimum=0):
            if name == "model revision":
                raise RuntimeError("late commit")
            return real(value,name,minimum)
        with patch("first_piece.cooperative.wire.counter",side_effect=fail):
            with self.assertRaises(RuntimeError):
                while service.work_status()["state"] == "working":
                    service.advance(128)
        self.assertEqual(before,service._adapter.checkpoint())
        service = CooperativeService.restore(json.loads(json.dumps(service.checkpoint())))
        result = service.advance(1)
        self.assertEqual(result["state"],"completed")
        self.assertEqual(canonical(reference),canonical(service._adapter._learner))

    def test_partial_replay_rejects_resealed_cursor_and_permutation_corruption(self):
        core = train(PlasticRevisionLearner(5,max_tasks=4,max_symbols=16),
                     ScaleWorld(400,n_symbols=16,n_contexts=4),511)
        events,target = ScaleWorld(400,n_symbols=16,n_contexts=4).episode(3)
        for event in events:
            core.receive(event)
        receipt = {"schema_version":1,"receipt_id":"r","request_id":"q","source_id":"e",
                   "status":"observed","outcome":{"measure":"lab.success","unit":"binary",
                                                "value":int(target == 0)}}
        work = ReceiptWork(core,0,receipt)
        while work.phase != "replay" or work.fit["gradients"] < 11:
            work.advance()
        snapshot = work.checkpoint()
        for change in (lambda s:s["fit"].__setitem__("gradients",s["fit"]["gradients"]+2),
                       lambda s:s["fit"]["order"].__setitem__(0,s["fit"]["order"][1]),
                       lambda s:s["fit"]["candidate"]["points"][0].pop()):
            data = copy.deepcopy(snapshot["data"])
            change(data)
            with self.assertRaises(ValueError):
                ReceiptWork.restore(sealed(data))

    def test_coverage_is_actual_labels_not_replay_and_flags_missing_actions(self):
        service = CooperativeService(minimum_observations=2,
            actions=["a","b"],learner_options={"max_tasks":1,"max_symbols":4,
                "min_records":64,"fit_per_context":64,"max_features":1})
        seq = 0
        for index in range(160):
            events = [{"kind":"token","token":"same","task":0},
                      {"kind":"surface","surface":"sealed","task":0}]
            p = feed(service,events,seq)
            seq += len(events)
            coverage = service.coverage(p["prediction_id"])
            self.assertEqual(coverage["actions"][1]["observations"],0)
            self.assertEqual(coverage["actions"][1]["coverage_status"],"unobserved")
            req = service.register_action(agent_proposal(p,0),executor_id="test:executor")
            receipt = observed_receipt(req,index%2)
            ack = service.submit_receipt(receipt)
            self.assertEqual(service.submit_receipt(receipt),ack)
        p = feed(service,events,seq)
        c = service.coverage()
        self.assertGreater(c["actions"][0]["observations"],2)
        self.assertLessEqual(c["actions"][0]["observations"],64)
        self.assertEqual(c["actions"][0]["coverage_status"],"observed")
        self.assertIsNone(c["epistemic_interval"])
        with self.assertRaises(ValueError):
            service.coverage("stale")

    def test_cancelled_receipt_does_not_learn_and_corrupt_work_rejected(self):
        service = CooperativeService()
        p = feed(service,trace(0))
        req = service.register_action(agent_proposal(p),executor_id="test:executor")
        receipt = {"schema_version":1,"receipt_id":"cancel:one","request_id":req["request_id"],
                   "source_id":"test:executor","status":"cancelled","outcome":None}
        service.begin_receipt(receipt)
        data = service.checkpoint()
        broken = copy.deepcopy(data)
        broken["work"]["checksum"] = "0"*64
        with self.assertRaises(ValueError):
            CooperativeService.restore(broken)
        self.assertFalse(service.advance(1)["ack"]["learned"])
        self.assertEqual(service._adapter._learner.steps,0)

    def test_recurrent_geometry_retains_multiplicity_without_oracle_fields(self):
        left,right = encoded_state(trace(0)),encoded_state(trace(1))
        self.assertNotEqual(left,right)
        core = PlasticRevisionLearner(n_actions=2)
        for events in (trace(0),trace(1)):
            for event in events:
                core.receive(event)
            if events == trace(0):
                pair = (core.episode["mask"],core.episode["before"])
            else:
                self.assertEqual(pair,(core.episode["mask"],core.episode["before"]))
            core.finish_evaluation()

    def test_adaptive_pending_trial_json_resume_and_lifetime_accounting(self):
        core = AdaptiveTraceLearner(2)
        actions = random.Random(802)
        resumed = False
        for index in range(3000):
            target = index%2
            for event in trace(target):
                core.receive(event)
            action = actions.randrange(2)
            if core.trial is not None and core.trial["n"] >= 19 and not resumed:
                checkpoint = json.loads(json.dumps(core.checkpoint()))
                clone = AdaptiveTraceLearner.restore(checkpoint)
                self.assertEqual(core.checkpoint(),clone.checkpoint())
                self.assertEqual(core.learn(action,int(action == target)),
                                 clone.learn(action,int(action == target)))
                self.assertEqual(core.checkpoint(),clone.checkpoint())
                core,resumed = clone,True
            else:
                core.learn(action,int(action == target))
        self.assertTrue(resumed)
        self.assertGreater(core.attempts,0)
        self.assertLessEqual(core.metrics()["allocated_s2_points"],160)
        self.assertLessEqual(core.metrics()["retained_records"],2048)
        snapshot = json.loads(json.dumps(core.checkpoint()))
        snapshot["neural_updates"] += 1
        with self.assertRaises(ValueError):
            AdaptiveTraceLearner.restore(snapshot)


if __name__ == "__main__":
    unittest.main()
