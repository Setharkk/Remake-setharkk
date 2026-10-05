"""Optional trace backend using the existing single-writer wire contracts."""
import copy

from .adapter import FirstPieceAdapter
from .adaptive_trace_v2 import AdaptiveTraceLearnerV2
from .cooperative import CooperativeService
from .trace_work import TraceReceiptWork
from setharkk import contracts as wire


class AdaptiveTraceAdapter(FirstPieceAdapter):
    LEARNER_CLASS = AdaptiveTraceLearnerV2
    IMPLEMENTATION = AdaptiveTraceLearnerV2.IMPLEMENTATION

    def _translate_observation(self, event):
        if event["kind"] == "stream.symbol":
            if set(event["payload"]) != {"value"}:
                raise ValueError("Unsupported trace symbol payload")
            token = wire.identifier(event["payload"]["value"], "symbol")
            return {"kind": "token", "token": token}
        if event["kind"] == "stream.end":
            if event["payload"] != {"value": "sealed"}:
                raise ValueError("Unsupported trace end payload")
            return {"kind": "surface", "surface": "sealed"}
        raise ValueError("Observation outside trace capabilities")

    def _fork_learner(self, *, observation=False, context=None):
        if not observation:
            return copy.deepcopy(self._learner)
        # Observation writes only episode, RNG, vocabulary and context membership.
        core = copy.copy(self._learner)
        core.rng = copy.deepcopy(core.rng)
        core.state = list(core.state)
        core.symbols, core.contexts = dict(core.symbols), dict(core.contexts)
        return core

    def capabilities(self):
        result = super().capabilities()
        result.pop("token_range")
        result.update(observation_kinds=["stream.symbol", "stream.end"],
                      prediction_trigger="stream.end",
                      max_symbols=self._learner.config["max_symbols"],
                      token_type="opaque string", checkpoint_format=2,
                      max_leaves=self._learner.config["max_leaves"],
                      calibration="causal positive affine readout",
                      autonomous_execution=False)
        return result


class AdaptiveTraceService(CooperativeService):
    ADAPTER_CLASS = AdaptiveTraceAdapter
    WORK_CLASS = TraceReceiptWork
    WORK_PROTOCOL = "first_piece.trace-cooperative.v2"
    WORK_PRIMITIVES = ["eight-row geometry block", "one gradient", "shuffle",
                       "bounded calibration/commit"]

    def coverage(self, prediction_id=None):
        with self._lock:
            prediction = self._adapter.current_prediction()
            if prediction is None or (prediction_id is not None and prediction_id != prediction["prediction_id"]):
                raise ValueError("Coverage needs the active prediction")
            core = self._adapter._learner
            leaf = core._leaf(core.state)
            counts = [[0, 0], [0, 0]]
            for state, coin, action, outcome in core.history.get(core.context, []):
                if core._leaf(state) == leaf:
                    counts[action][outcome] += 1
            return {"schema_version": 1, "prediction_id": prediction["prediction_id"],
                    "model_revision": self._adapter._revision,
                    "scope": "recent actual labels in current trace leaf and context",
                    "minimum_observations": self.minimum_observations,
                    "actions": [{"candidate_id": f"choice.{i}", "observations": sum(row),
                                 "positive_outcomes": row[1],
                                 "coverage_status": "unobserved" if not sum(row) else
                                    "limited" if sum(row) < self.minimum_observations else "observed"}
                                for i, row in enumerate(counts)],
                    "epistemic_interval": None}
