"""Behavior across sensory, agent, executor and checkpoint boundaries."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import threading
import unittest

from first_piece.adapter import FirstPieceAdapter
from first_piece.integration_probe import agent_proposal, observed_receipt, wire_event, exercise
from first_piece.streaming import StreamingWorld


def surface(adapter, world, context="context:one"):
    while True:
        event = world.next_event()
        sequence = adapter.metrics()["last_sequence"] + 1
        prediction = adapter.submit_observation(wire_event(event, sequence, context))
        if prediction is not None:
            return prediction


def complete(adapter, world, context="context:one", action=0):
    prediction = surface(adapter, world, context)
    request = adapter.register_action(agent_proposal(prediction, action), executor_id="lab.executor")
    receipt = observed_receipt(request, world.act(action))
    return request, receipt, adapter.submit_receipt(receipt)


class AdapterTests(unittest.TestCase):
    def assert_rejected_without_mutation(self, adapter, operation):
        before = adapter.checkpoint()
        with self.assertRaises((ValueError, RuntimeError)):
            operation()
        self.assertEqual(before, adapter.checkpoint())

    def test_same_data_and_updates_as_original_learning_core(self):
        # Crosses acquisition and a frozen validation horizon.
        result = exercise(seed=3, episodes=416)
        self.assertEqual(result["model_revision"], 416)
        self.assertTrue(result["direct_neural_state_and_rng_identical"])
        self.assertTrue(result["pending_action_json_resume_without_reexecution"])
        self.assertEqual(result["shared_context_count"], 1)
        self.assertEqual(sum(result["proposals_by_agent"].values()), 416)

    def test_opaque_contexts_have_stable_bounded_bindings(self):
        adapter, world = FirstPieceAdapter(), StreamingWorld()
        complete(adapter, world, "project:alpha")
        complete(adapter, world, "project:beta")
        complete(adapter, world, "project:alpha")
        self.assertEqual(adapter.metrics()["context_slots"], {"project:alpha": 0, "project:beta": 1})
        event = world.next_event()
        message = wire_event(event, adapter.metrics()["last_sequence"] + 1, "project:gamma")
        self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_observation(message))

    def test_sequence_and_capability_errors_are_transactional(self):
        adapter = FirstPieceAdapter()
        base = wire_event({"kind": "token", "token": 0}, 0)
        for changes in ({"sequence": 1}, {"stream_id": "other", "sequence": 2},
                        {"kind": "filesystem.changed"}, {"payload": {"value": 10}},
                        {"payload": {"value": True}}):
            bad = copy.deepcopy(base)
            bad.update(changes)
            self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_observation(bad))
        self.assertIsNone(adapter.submit_observation(base))
        self.assertIsNone(adapter.submit_observation(base))
        self.assertEqual(adapter.metrics()["last_sequence"], 0)
        wrong_stream = wire_event({"kind": "token", "token": 1}, 1)
        wrong_stream["stream_id"] = "other"
        self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_observation(wrong_stream))
        conflicting = copy.deepcopy(base)
        conflicting["payload"]["value"] = 1
        self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_observation(conflicting))
        changed_context = wire_event({"kind": "token", "token": 1}, 1, "different-context")
        self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_observation(changed_context))

    def test_stale_agent_and_forged_executor_do_not_write_state(self):
        adapter, world = FirstPieceAdapter(), StreamingWorld()
        prediction = surface(adapter, world)
        for changes in ({"model_revision": 1}, {"prediction_id": "old"},
                        {"candidate_id": "choice.unknown"}):
            proposal = agent_proposal(prediction)
            proposal.update(changes)
            self.assert_rejected_without_mutation(adapter, lambda: adapter.register_action(proposal, executor_id="lab.executor"))
        request = adapter.register_action(agent_proposal(prediction), executor_id="lab.executor")
        receipt = observed_receipt(request, 1)
        for changes in ({"source_id": "unrelated"}, {"request_id": "old"}):
            bad = copy.deepcopy(receipt)
            bad.update(changes)
            self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_receipt(bad))
        for change in ({"unit": "seconds"}, {"value": True}, {"value": 2}):
            bad = copy.deepcopy(receipt)
            bad["outcome"].update(change)
            self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_receipt(bad))

    def test_predictions_requests_and_config_cannot_mutate_live_state(self):
        adapter, world = FirstPieceAdapter(), StreamingWorld()
        prediction = surface(adapter, world)
        original = adapter.current_prediction()
        prediction["forecasts"][0]["action_name"] = "filesystem.write"
        prediction["forecasts"][0]["distribution"]["parameters"]["p"] = 0
        self.assertEqual(adapter.current_prediction(), original)
        proposal = agent_proposal(original)
        request = adapter.register_action(proposal, executor_id="lab.executor")
        request["arguments"]["surprise"] = "modified"
        request["action_name"] = "filesystem.write"
        self.assertEqual(adapter.register_action(proposal, executor_id="lab.executor")["arguments"], {})
        self.assertEqual(adapter.register_action(proposal, executor_id="lab.executor")["action_name"], adapter.actions[0])
        for name, value in (("model_id", "replacement"), ("actions", ["a", "b"]), ("receipt_window", 2)):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(adapter, name, value)

    def test_two_agents_share_one_model_and_one_inflight_action(self):
        adapter, world = FirstPieceAdapter(), StreamingWorld()
        prediction = surface(adapter, world)
        barrier = threading.Barrier(2)
        def propose(agent):
            barrier.wait(timeout=5)
            try:
                return adapter.register_action(agent_proposal(prediction, agent_id=agent),
                                               executor_id="lab.executor")
            except RuntimeError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(propose, ["agent:a", "agent:b"]))
        accepted = [r for r in results if r is not None]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(adapter.metrics()["model_revision"], 0)
        adapter.submit_receipt(observed_receipt(accepted[0], world.act(0)))
        self.assertEqual(adapter.metrics()["model_revision"], 1)

    def test_duplicate_receipt_learns_once_conflict_and_expired_replay_rejected(self):
        adapter, world = FirstPieceAdapter(receipt_window=1), StreamingWorld()
        request, receipt, ack = complete(adapter, world)
        before = adapter.checkpoint()
        redelivery = copy.deepcopy(receipt)
        redelivery["receipt_id"] += ":again"
        self.assertEqual(adapter.submit_receipt(redelivery), ack)
        self.assertEqual(adapter.checkpoint(), before)
        conflict = copy.deepcopy(receipt)
        conflict["outcome"]["value"] ^= 1
        self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_receipt(conflict))
        complete(adapter, world)
        self.assertEqual(adapter.metrics()["retained_receipts"], 1)
        self.assert_rejected_without_mutation(adapter, lambda: adapter.submit_receipt(receipt))
        self.assertEqual(adapter.metrics()["model_revision"], 2)

    def test_failed_and_cancelled_actions_close_episode_without_training(self):
        for status in ("failed", "cancelled"):
            with self.subTest(status=status):
                adapter, world = FirstPieceAdapter(), StreamingWorld()
                prediction = surface(adapter, world)
                request = adapter.register_action(agent_proposal(prediction), executor_id="lab.executor")
                before = adapter.checkpoint()["learner"]
                ack = adapter.submit_receipt({"schema_version": 1, "receipt_id": "receipt:failure",
                                             "request_id": request["request_id"], "source_id": "lab.executor",
                                             "status": status, "outcome": None})
                after = adapter.checkpoint()["learner"]
                self.assertFalse(ack["learned"])
                self.assertEqual(ack["model_revision"], 0)
                self.assertEqual(before["tasks"], after["tasks"])
                world.abort_episode()
                self.assertEqual(world.checkpoint()["world"]["completed"], 0)
                self.assertIsNone(adapter.current_prediction())
                complete(adapter, world)
                self.assertEqual(adapter.metrics()["model_revision"], 1)

    def test_token_and_pending_action_json_resume_and_duplicate_replay(self):
        adapter, world = FirstPieceAdapter(seed=9), StreamingWorld(seed=17)
        first = world.next_event()
        adapter.submit_observation(wire_event(first, 0, "context:one"))
        checkpoint = json.loads(json.dumps(adapter.checkpoint()))
        restored = FirstPieceAdapter.restore(checkpoint)
        self.assertEqual(restored.checkpoint(), adapter.checkpoint())
        prediction = surface(restored, world)
        request = restored.register_action(agent_proposal(prediction), executor_id="lab.executor")
        pending = json.loads(json.dumps(restored.checkpoint()))
        resumed = FirstPieceAdapter.restore(pending)
        self.assertEqual(resumed.register_action(agent_proposal(prediction), executor_id="lab.executor"), request)
        receipt = observed_receipt(request, world.act(0))
        self.assertEqual(resumed.submit_receipt(receipt), restored.submit_receipt(receipt))
        self.assertEqual(resumed.checkpoint(), restored.checkpoint())
        completed = FirstPieceAdapter.restore(json.loads(json.dumps(resumed.checkpoint())))
        self.assertEqual(completed.submit_receipt(receipt), resumed.submit_receipt(receipt))
        self.assertEqual(completed.checkpoint(), resumed.checkpoint())

    def test_incompatible_or_inconsistent_checkpoints_rejected(self):
        adapter, world = FirstPieceAdapter(), StreamingWorld()
        prediction = surface(adapter, world)
        adapter.register_action(agent_proposal(prediction), executor_id="lab.executor")
        checkpoint = adapter.checkpoint()
        cases = []
        for field, value in (("format", True), ("contract_version", 2),
                             ("implementation", "different-network"),
                             ("model_revision", 1), ("context_slots", {"context:one": 1})):
            bad = copy.deepcopy(checkpoint)
            bad[field] = value
            cases.append(bad)
        bad = copy.deepcopy(checkpoint)
        bad["pending_request"]["request_id"] = "forged"
        cases.append(bad)
        bad = copy.deepcopy(checkpoint)
        bad["prediction"]["forecasts"][0]["distribution"]["parameters"]["p"] = .123
        cases.append(bad)
        for bad in cases:
            with self.subTest(case=len(str(bad))), self.assertRaises(ValueError):
                FirstPieceAdapter.restore(bad)
        self.assertEqual(checkpoint, adapter.checkpoint())

    def test_initial_checkpoint_and_post_receipt_old_prediction_ack(self):
        adapter = FirstPieceAdapter()
        restored = FirstPieceAdapter.restore(json.loads(json.dumps(adapter.checkpoint())))
        self.assertEqual(restored.checkpoint(), adapter.checkpoint())
        world = StreamingWorld()
        prediction = surface(adapter, world)
        old_event = adapter.checkpoint()["last_observation"]
        request = adapter.register_action(agent_proposal(prediction), executor_id="lab.executor")
        adapter.submit_receipt(observed_receipt(request, world.act(0)))
        self.assertEqual(adapter.submit_observation(old_event), prediction)
        self.assertIsNone(adapter.current_prediction())
        self.assert_rejected_without_mutation(adapter, lambda: adapter.register_action(agent_proposal(prediction), executor_id="lab.executor"))


if __name__ == "__main__":
    unittest.main()
