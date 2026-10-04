"""Generic opaque symbols and bounded action lists on the existing wire ABI."""
import copy

from setharkk import contracts as wire
from .adapter import FirstPieceAdapter
from .shared import SharedLearner


class SharedAdapter(FirstPieceAdapter):
    LEARNER_CLASS = SharedLearner
    IMPLEMENTATION = "first_piece.shared-compositions-s2.v1"
    MIN_ACTIONS, MAX_ACTIONS = 2, 16

    def __init__(self, *, actions=("lab.action.0", "lab.action.1", "lab.action.2", "lab.action.3"),
                 learner_options=None, **kwargs):
        options = {} if learner_options is None else copy.deepcopy(learner_options)
        if type(options) is not dict or not isinstance(actions, (list, tuple)):
            raise ValueError("Invalid shared adapter options")
        if "n_actions" in options and options["n_actions"] != len(actions):
            raise ValueError("Action list and learner shape differ")
        options["n_actions"] = len(actions)
        super().__init__(actions=actions, learner_options=options, **kwargs)

    def _fork_learner(self):
        return self._learner._transaction_copy()

    def _translate_observation(self, event):
        if event["kind"] == "stream.symbol" and set(event["payload"]) == {"value"}:
            return {"kind": "token", "token": wire.identifier(event["payload"]["value"], "symbol")}
        if event["kind"] == "stream.end" and event["payload"] == {"value": "sealed"}:
            return {"kind": "surface", "surface": "sealed"}
        raise ValueError("Observation outside shared learner capabilities")

    def capabilities(self):
        with self._lock:
            result = super().capabilities()
            result.pop("token_range")
            result.update({"observation_kinds": ["stream.symbol", "stream.end"],
                           "prediction_trigger": "stream.end",
                           "max_symbols": self._learner.config["max_symbols"],
                           "max_predicates_per_program": self._learner.config["max_features"],
                           "shared_neural_bank": True,
                           "action_count": len(self.actions)})
            return result
