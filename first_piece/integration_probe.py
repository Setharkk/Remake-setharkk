"""Synthetic integration evidence; no applications or files are acted upon."""
import argparse
import copy
import json
from pathlib import Path
import random

from setharkk import contracts as wire
from .adapter import FirstPieceAdapter
from .learner import DistinctionLearner
from .streaming import StreamingWorld


def wire_event(event, sequence, context_id="experiment:shared"):
    kind = event["kind"]
    return {
        "schema_version": wire.VERSION, "event_id": f"sensor:{sequence}",
        "stream_id": "sensor:main", "sequence": sequence,
        "context_id": context_id, "source_id": "lab.sensor",
        "kind": f"lab.{kind}",
        "payload": {"value": event["token"] if kind == "token" else event["surface"]},
    }


def agent_proposal(prediction, action=0, agent_id="agent:explorer"):
    return {
        "schema_version": wire.VERSION, "agent_id": agent_id,
        "goal_id": "goal:learn-shared-context",
        "prediction_id": prediction["prediction_id"],
        "model_revision": prediction["model_revision"],
        "candidate_id": f"choice.{action}",
    }


def observed_receipt(request, outcome, receipt_id=None):
    return {
        "schema_version": wire.VERSION,
        "receipt_id": receipt_id or "receipt:" + request["request_id"],
        "request_id": request["request_id"], "source_id": request["executor_id"],
        "status": "observed",
        "outcome": {"measure": "lab.success", "unit": "binary", "value": outcome},
    }


def exercise(seed=0, episodes=1344):
    adapter = FirstPieceAdapter(seed=seed)
    direct = DistinctionLearner(seed)
    world = StreamingWorld(seed + 100)
    actions = random.Random(seed + 200)
    sequence = 0
    executions = 0
    proposals_by_agent = {"agent:explorer": 0, "agent:verifier": 0}
    resumed_pending = False
    predictions_equal = True
    for episode in range(episodes):
        while True:
            event = world.next_event()
            reference = direct.receive(event)
            result = adapter.submit_observation(wire_event(event, sequence))
            sequence += 1
            if reference is not None:
                actual = [f["distribution"]["parameters"]["p"] for f in result["forecasts"]]
                predictions_equal = predictions_equal and actual == reference
                assert actual == reference
                break
            assert result is None
        action = actions.randrange(2)
        agent = list(proposals_by_agent)[episode % 2]
        proposal = agent_proposal(result, action, agent)
        request = adapter.register_action(proposal, executor_id="lab.executor")
        assert adapter.register_action(proposal, executor_id="lab.executor") == request
        proposals_by_agent[agent] += 1
        outcome = world.act(action)
        executions += 1
        receipt = observed_receipt(request, outcome)
        if episode == 384:
            # Simulated executor has already acted. Its receipt is retained
            # outside the learner; resuming the learner must not act again.
            snapshot = json.loads(json.dumps(adapter.checkpoint()))
            assert snapshot["pending_request"] == request
            assert snapshot["learner"]["tasks"][0]["status"] == "validating"
            adapter = FirstPieceAdapter.restore(snapshot)
            world = StreamingWorld.restore(json.loads(json.dumps(world.checkpoint())))
            assert adapter.register_action(proposal, executor_id="lab.executor") == request
            resumed_pending = True
        direct.learn(action, outcome)
        acknowledgement = adapter.submit_receipt(receipt)
        duplicate = copy.deepcopy(receipt)
        duplicate["receipt_id"] += ":redelivery"
        assert adapter.submit_receipt(duplicate) == acknowledgement
        assert adapter.checkpoint()["learner"] == direct.checkpoint()
    metrics = adapter.metrics()
    return {
        "seed": seed, "training_interactions": episodes,
        "sensor_events": sequence, "executor_calls": executions,
        "proposals_by_agent": proposals_by_agent,
        "model_revision": metrics["model_revision"],
        "shared_context_count": len(metrics["context_slots"]),
        "direct_predictions_identical": predictions_equal,
        "direct_neural_state_and_rng_identical": True,
        "duplicate_receipts_no_extra_learning": True,
        "pending_action_json_resume_without_reexecution": resumed_pending,
        "learner_status": metrics["learner"],
        "capabilities": adapter.capabilities(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = {"protocol": 1, "scope": "synthetic single-stream adapter",
              "integration": exercise(),
              "physical_exactly_once_execution_proven": False,
              "temporal_order_learning_implemented": False}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FIRST_PIECE_INTEGRATION_JSON=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
