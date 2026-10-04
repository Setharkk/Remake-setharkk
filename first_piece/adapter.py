"""Cortex-owned bridge: generic wire records outside, lab details inside.

This owns one serialized learning stream and never executes external actions.
Agents receive copies of predictions and submit proposals to the coordinator.
"""
import copy
import hashlib
import json
import threading

from setharkk import contracts as wire
from .learner import DistinctionLearner


IMPLEMENTATION = "first_piece.presence-s2.v1"


def _key(kind, data):
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return kind + ":" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _semantic_receipt(receipt):
    return {k: v for k, v in receipt.items() if k != "receipt_id"}


def _local_event(event):
    if event["kind"] == "lab.token":
        if set(event["payload"]) != {"value"} or type(event["payload"]["value"]) is not int or not 0 <= event["payload"]["value"] <= 9:
            raise ValueError("Unsupported lab token")
        return {"kind": "token", "token": event["payload"]["value"]}
    if event["kind"] == "lab.surface":
        if event["payload"] != {"value": "sealed"}:
            raise ValueError("Unsupported lab surface")
        return {"kind": "surface", "surface": "sealed"}
    raise ValueError("Observation kind outside this model's capabilities")


class FirstPieceAdapter:
    LEARNER_CLASS = DistinctionLearner
    IMPLEMENTATION = IMPLEMENTATION
    MIN_ACTIONS = MAX_ACTIONS = 2

    def __init__(self, *, model_id="setharkk.first-piece", seed=0,
                 actions=("lab.action.0", "lab.action.1"), receipt_window=64,
                 learner_options=None):
        wire.identifier(model_id, "model id")
        if not isinstance(actions, (tuple, list)) or not self.MIN_ACTIONS <= len(actions) <= self.MAX_ACTIONS:
            raise ValueError("Action count outside adapter capabilities")
        actions = [wire.identifier(a, "action name") for a in actions]
        if len(set(actions)) != len(actions):
            raise ValueError("Action names must be distinct")
        wire.counter(receipt_window, "receipt window", minimum=1)
        if receipt_window > 1024:
            raise ValueError("Receipt window exceeds adapter budget")
        options = {} if learner_options is None else copy.deepcopy(learner_options)
        if type(options) is not dict or "seed" in options:
            raise ValueError("Invalid learner options")
        self._learner = self.LEARNER_CLASS(seed, **options)
        self._model_id = model_id
        self._actions = tuple(actions)
        self._receipt_window = receipt_window
        self._revision = 0
        self._stream_id = None
        self._last_sequence = -1
        self._last_observation = None
        self._last_result = None
        self._slots = {}
        self._prediction = None
        self._pending = None
        self._receipts = {}
        self._lock = threading.RLock()

    @property
    def model_id(self):
        return self._model_id

    @property
    def actions(self):
        return self._actions

    @property
    def receipt_window(self):
        return self._receipt_window

    def capabilities(self):
        with self._lock:
            return {
                "contract_version": wire.VERSION, "implementation": self.IMPLEMENTATION,
                "model_id": self.model_id, "max_inflight_actions": 1, "streams": 1,
                "max_contexts": self._learner.config["max_tasks"],
                "observation_kinds": ["lab.token", "lab.surface"],
                "token_range": [0, 9], "actions": list(self.actions),
                "action_arguments": "empty object", "prediction_trigger": "lab.surface",
                "measure": "lab.success", "unit": "binary",
                "distributions": ["bernoulli"], "epistemic_confidence": "not estimated",
                "neural_geometry": "product of S2", "receipt_window": self.receipt_window,
            }

    def _fork_learner(self):
        return copy.deepcopy(self._learner)

    def _translate_observation(self, event):
        return _local_event(event)

    def submit_observation(self, message):
        event = wire.observation(message)
        with self._lock:
            if event == self._last_observation:
                # Repeat of the latest event returns its old acknowledgement.
                # It does not create a new model view or another event.
                return copy.deepcopy(self._last_result)
            if self._stream_id is not None and event["stream_id"] != self._stream_id:
                raise ValueError("This adapter owns one stream")
            if event["sequence"] != self._last_sequence + 1:
                raise ValueError("Observation gap, conflict or old replay")
            local = self._translate_observation(event)
            context = event["context_id"]
            slot = self._slots.get(context)
            if slot is None:
                if len(self._slots) >= self._learner.config["max_tasks"]:
                    raise ValueError("Context budget exhausted")
                slot = len(self._slots)
            candidate = self._fork_learner()
            local["task"] = slot
            probabilities = candidate.receive(local)
            result = None
            if probabilities is not None:
                identity = {k: event[k] for k in ("event_id", "stream_id", "sequence", "context_id")}
                result = wire.prediction({
                    "schema_version": wire.VERSION,
                    "prediction_id": _key("prediction", {**identity, "model": self.model_id, "revision": self._revision}),
                    "model_id": self.model_id, "model_revision": self._revision,
                    **identity,
                    "forecasts": [{
                        "candidate_id": f"choice.{i}", "action_name": name, "arguments": {},
                        "measure": "lab.success", "unit": "binary",
                        "distribution": {"kind": "bernoulli", "parameters": {"p": probabilities[i]}},
                    } for i, name in enumerate(self.actions)],
                })
            # Publish a new complete state only after model and record validation.
            self._learner = candidate
            self._slots[context] = slot
            self._stream_id = event["stream_id"]
            self._last_sequence = event["sequence"]
            self._last_observation = event
            self._last_result = result
            self._prediction = result
            return copy.deepcopy(result)

    def current_prediction(self):
        with self._lock:
            return copy.deepcopy(self._prediction)

    def register_action(self, proposal, *, executor_id):
        """Coordinator binds one scored proposal to a designated executor."""
        proposal = wire.proposal(proposal)
        wire.identifier(executor_id, "executor id")
        with self._lock:
            prediction = self._prediction
            if prediction is None:
                raise RuntimeError("No pending prediction")
            if proposal["prediction_id"] != prediction["prediction_id"] or proposal["model_revision"] != self._revision:
                raise ValueError("Stale or unrelated proposal")
            forecast = next((f for f in prediction["forecasts"]
                             if f["candidate_id"] == proposal["candidate_id"]), None)
            if forecast is None:
                raise ValueError("Unknown action candidate")
            data = {
                "schema_version": wire.VERSION, "model_id": self.model_id,
                "model_revision": self._revision, "prediction_id": prediction["prediction_id"],
                "stream_id": prediction["stream_id"], "sequence": prediction["sequence"],
                "context_id": prediction["context_id"], "agent_id": proposal["agent_id"],
                "goal_id": proposal["goal_id"], "executor_id": executor_id,
                "candidate_id": forecast["candidate_id"], "action_name": forecast["action_name"],
                "arguments": copy.deepcopy(forecast["arguments"]),
            }
            request = wire.request({"request_id": _key("action", data), **data})
            if self._pending is not None:
                if request == self._pending:
                    return copy.deepcopy(request)
                raise RuntimeError("One action already registered; coordinator must arbitrate")
            self._pending = request
            return copy.deepcopy(request)

    def submit_receipt(self, message):
        receipt = wire.receipt(message)
        with self._lock:
            completed = self._receipts.get(receipt["request_id"])
            if completed is not None:
                if _semantic_receipt(completed["receipt"]) != _semantic_receipt(receipt):
                    raise ValueError("Conflicting receipt for completed action")
                return copy.deepcopy(completed["ack"])
            if any(item["receipt"]["receipt_id"] == receipt["receipt_id"] for item in self._receipts.values()):
                raise ValueError("Receipt id already belongs to another action")
            pending = self._pending
            if pending is None or receipt["request_id"] != pending["request_id"]:
                raise ValueError("Receipt has no matching action")
            if receipt["source_id"] != pending["executor_id"]:
                raise ValueError("Receipt is not from the designated executor")
            candidate = self._fork_learner()
            learned = receipt["status"] == "observed"
            if learned:
                outcome = receipt["outcome"]
                if outcome["measure"] != "lab.success" or outcome["unit"] != "binary" or type(outcome["value"]) is not int or outcome["value"] not in (0, 1):
                    raise ValueError("Outcome outside this model's capabilities")
                candidate.learn(self.actions.index(pending["action_name"]), outcome["value"])
            else:
                candidate.finish_evaluation()
            revision = wire.counter(self._revision + int(learned), "model revision")
            ack = {"request_id": pending["request_id"], "learned": learned, "model_revision": revision}
            self._learner = candidate
            self._revision = revision
            self._prediction = None
            self._pending = None
            self._receipts[receipt["request_id"]] = {
                "request": copy.deepcopy(pending), "receipt": receipt, "ack": ack,
            }
            while len(self._receipts) > self.receipt_window:
                del self._receipts[next(iter(self._receipts))]
            return copy.deepcopy(ack)

    def metrics(self):
        with self._lock:
            return {"model_revision": self._revision, "last_sequence": self._last_sequence,
                    "context_slots": dict(self._slots), "pending_request": self._pending is not None,
                    "retained_receipts": len(self._receipts), "learner": self._learner.metrics()}

    def checkpoint(self):
        with self._lock:
            return copy.deepcopy({
                "format": 1, "contract_version": wire.VERSION, "implementation": self.IMPLEMENTATION,
                "model_id": self.model_id, "actions": list(self.actions),
                "receipt_window": self.receipt_window, "model_revision": self._revision,
                "stream_id": self._stream_id, "last_sequence": self._last_sequence,
                "context_slots": self._slots, "last_observation": self._last_observation,
                "last_result": self._last_result, "prediction": self._prediction,
                "pending_request": self._pending, "receipts": list(self._receipts.values()),
                "learner": self._learner.checkpoint(),
            })

    @classmethod
    def restore(cls, snapshot):
        fields = {"format", "contract_version", "implementation", "model_id", "actions",
                  "receipt_window", "model_revision", "stream_id", "last_sequence",
                  "context_slots", "last_observation", "last_result", "prediction",
                  "pending_request", "receipts", "learner"}
        if type(snapshot) is not dict or set(snapshot) != fields:
            raise ValueError("Invalid adapter checkpoint")
        if type(snapshot["format"]) is not int or snapshot["format"] != 1 or type(snapshot["contract_version"]) is not int or snapshot["contract_version"] != wire.VERSION or snapshot["implementation"] != cls.IMPLEMENTATION:
            raise ValueError("Unsupported adapter implementation or format")
        learner = cls.LEARNER_CLASS.restore(snapshot["learner"])
        options = {k: v for k, v in learner.config.items() if k != "seed"}
        instance = cls(model_id=snapshot["model_id"], seed=learner.config["seed"],
                       actions=snapshot["actions"], receipt_window=snapshot["receipt_window"],
                       learner_options=options)
        revision = wire.counter(snapshot["model_revision"], "model revision")
        sequence = wire.counter(snapshot["last_sequence"], "last sequence", minimum=-1)
        slots = snapshot["context_slots"]
        if type(slots) is not dict or len(slots) > learner.config["max_tasks"]:
            raise ValueError("Invalid context bindings")
        for key, slot in slots.items():
            wire.identifier(key, "context id")
            wire.counter(slot, "context slot")
        if sorted(slots.values()) != list(range(len(slots))) or set(slots.values()) != set(learner.tasks):
            raise ValueError("Context bindings and model tasks differ")
        if revision != sum(s["steps"] for s in learner.tasks.values()):
            raise ValueError("Model revision and learning exposure differ")
        last = None if snapshot["last_observation"] is None else wire.observation(snapshot["last_observation"])
        result = None if snapshot["last_result"] is None else wire.prediction(snapshot["last_result"])
        prediction = None if snapshot["prediction"] is None else wire.prediction(snapshot["prediction"])
        pending = None if snapshot["pending_request"] is None else wire.request(snapshot["pending_request"])
        if sequence == -1:
            if any(v is not None for v in (snapshot["stream_id"], last, result, prediction, pending)) or slots or revision or snapshot["receipts"]:
                raise ValueError("Inconsistent unused adapter")
        else:
            wire.identifier(snapshot["stream_id"], "stream id")
            if last is None or last["sequence"] != sequence or last["stream_id"] != snapshot["stream_id"] or last["context_id"] not in slots:
                raise ValueError("Invalid observation boundary")
            instance._translate_observation(last)
            if (result is not None) != (instance._translate_observation(last)["kind"] == "surface"):
                raise ValueError("Observation and cached result differ")
            if learner.episode["phase"] == "idle" and instance._translate_observation(last)["kind"] != "surface":
                raise ValueError("Idle model has an unfinished observation")
        if result is not None:
            if last is None or instance._translate_observation(last)["kind"] != "surface" or any(result[k] != last[k] for k in ("event_id", "stream_id", "sequence", "context_id")) or result["model_id"] != instance.model_id or result["model_revision"] > revision:
                raise ValueError("Invalid cached prediction")
            identity = {k: result[k] for k in ("event_id", "stream_id", "sequence", "context_id")}
            expected_id = _key("prediction", {**identity, "model": instance.model_id, "revision": result["model_revision"]})
            if result["prediction_id"] != expected_id or len(result["forecasts"]) != len(instance.actions):
                raise ValueError("Invalid prediction identity")
            for i, forecast in enumerate(result["forecasts"]):
                if forecast["candidate_id"] != f"choice.{i}" or forecast["action_name"] != instance.actions[i] or forecast["arguments"] or forecast["measure"] != "lab.success" or forecast["unit"] != "binary" or forecast["distribution"]["kind"] != "bernoulli":
                    raise ValueError("Cached forecast outside model capabilities")
        if (prediction is not None) != (learner.episode["phase"] == "feedback"):
            raise ValueError("Model episode and public prediction differ")
        if prediction is not None and (prediction != result or prediction["model_revision"] != revision):
            raise ValueError("Invalid live prediction revision")
        if learner.episode["phase"] != "idle":
            if last is None or slots[last["context_id"]] != learner.episode["task"]:
                raise ValueError("Observation and active model context differ")
            expected_kind = "surface" if learner.episode["phase"] == "feedback" else "token"
            if instance._translate_observation(last)["kind"] != expected_kind:
                raise ValueError("Observation and model phase differ")
        if prediction is not None:
            probabilities = learner.pending_probabilities()
            for i, forecast in enumerate(prediction["forecasts"]):
                p = forecast["distribution"]["parameters"]["p"]
                if abs(p - probabilities[i]) > 1e-10:
                    raise ValueError("Live forecast and neural state differ")
        if pending is not None:
            if prediction is None or pending["model_id"] != instance.model_id or any(pending[k] != prediction[k] for k in ("prediction_id", "model_revision", "stream_id", "sequence", "context_id")):
                raise ValueError("Invalid pending action boundary")
            forecasts = [f for f in prediction["forecasts"] if f["candidate_id"] == pending["candidate_id"]]
            if len(forecasts) != 1 or any(pending[k] != forecasts[0][k] for k in ("action_name", "arguments")):
                raise ValueError("Pending action differs from scored candidate")
            identity = {k: v for k, v in pending.items() if k != "request_id"}
            if pending["request_id"] != _key("action", identity):
                raise ValueError("Invalid action identity")
        if type(snapshot["receipts"]) is not list or len(snapshot["receipts"]) > instance.receipt_window:
            raise ValueError("Receipt budget exceeded")
        retained = {}
        receipt_ids = set()
        previous = None
        for entry in snapshot["receipts"]:
            if type(entry) is not dict or set(entry) != {"request", "receipt", "ack"}:
                raise ValueError("Invalid retained receipt")
            action, receipt = wire.request(entry["request"]), wire.receipt(entry["receipt"])
            ack = entry["ack"]
            if action["request_id"] != receipt["request_id"] or action["executor_id"] != receipt["source_id"] or action["request_id"] in retained or (pending is not None and pending["request_id"] == action["request_id"]):
                raise ValueError("Invalid completed action identity")
            if type(ack) is not dict or set(ack) != {"request_id", "learned", "model_revision"} or ack["request_id"] != action["request_id"] or type(ack["learned"]) is not bool or ack["learned"] != (receipt["status"] == "observed"):
                raise ValueError("Invalid learning acknowledgement")
            wire.counter(ack["model_revision"], "ack revision")
            if ack["model_revision"] != action["model_revision"] + int(ack["learned"]) or ack["model_revision"] > revision:
                raise ValueError("Acknowledgement and model revisions differ")
            identity = {k: v for k, v in action.items() if k != "request_id"}
            if action["request_id"] != _key("action", identity) or action["model_id"] != instance.model_id or action["stream_id"] != snapshot["stream_id"] or action["sequence"] > sequence or action["context_id"] not in slots:
                raise ValueError("Completed action belongs to another model boundary")
            if action["action_name"] not in instance.actions or action["candidate_id"] != f"choice.{instance.actions.index(action['action_name'])}" or action["arguments"]:
                raise ValueError("Invalid completed action candidate")
            if receipt["status"] == "observed":
                outcome = receipt["outcome"]
                if outcome["measure"] != "lab.success" or outcome["unit"] != "binary" or type(outcome["value"]) is not int or outcome["value"] not in (0, 1):
                    raise ValueError("Invalid retained outcome")
            if receipt["receipt_id"] in receipt_ids:
                raise ValueError("Duplicate retained receipt id")
            if previous is not None and (action["sequence"] <= previous["request"]["sequence"] or action["model_revision"] != previous["ack"]["model_revision"]):
                raise ValueError("Completed action order differs from model revisions")
            receipt_ids.add(receipt["receipt_id"])
            retained[action["request_id"]] = {"request": action, "receipt": receipt, "ack": copy.deepcopy(ack)}
            previous = retained[action["request_id"]]
        if previous is not None and previous["ack"]["model_revision"] != revision:
            raise ValueError("Last completed action and model revisions differ")
        instance._learner = learner
        instance._revision = revision
        instance._stream_id = snapshot["stream_id"]
        instance._last_sequence = sequence
        instance._slots = copy.deepcopy(slots)
        instance._last_observation, instance._last_result = last, result
        instance._prediction, instance._pending = prediction, pending
        instance._receipts = retained
        return instance
