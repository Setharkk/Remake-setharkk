"""Common wire contracts for a resource-budgeted action catalogue."""
import copy
import math

from .trace_service import AdaptiveTraceAdapter, AdaptiveTraceService
from .action_trace import ActionTraceLearner, configuration
from .action_work import ActionReceiptWork
from setharkk import contracts as wire


class ActionTraceAdapter(AdaptiveTraceAdapter):
    LEARNER_CLASS = ActionTraceLearner
    IMPLEMENTATION = ActionTraceLearner.IMPLEMENTATION
    MAX_ACTIONS = math.inf

    def __init__(self, *, actions=("lab.action.0","lab.action.1"), learner_options=None, seed=0, **options):
        if not isinstance(actions,(tuple,list)) or len(actions) < 2:
            raise ValueError("At least two named actions required")
        learner_options = {} if learner_options is None else copy.deepcopy(learner_options)
        if type(learner_options) is not dict or "seed" in learner_options:
            raise ValueError("Invalid action learner options")
        if "n_actions" in learner_options:
            wire.counter(learner_options["n_actions"],"action count",minimum=2)
        if "n_actions" in learner_options and learner_options["n_actions"] != len(actions):
            raise ValueError("Action catalogue and neural bank differ")
        learner_options["n_actions"] = len(actions)
        configuration(seed,**learner_options)  # Budget check before bank/list allocation.
        super().__init__(actions=actions,learner_options=learner_options,seed=seed,**options)

    def _fork_learner(self, *, observation=False, context=None):
        if observation:
            return super()._fork_learner(observation=True,context=context)
        # Immutable past rows and frozen banks are shared; all written fields are copied.
        old = self._learner
        core = copy.copy(old)
        core.rng, core.state = copy.deepcopy(old.rng), list(old.state)
        core.symbols, core.contexts = dict(old.symbols), dict(old.contexts)
        core.next_checks, core.decisions = dict(old.next_checks), list(old.decisions)
        leaf = old._leaf(old.state)
        core.nodes = {key:dict(node) for key,node in old.nodes.items()}
        core.nodes[leaf]["records"] = list(old.nodes[leaf]["records"])
        core.nodes[leaf]["bank"] = old.nodes[leaf]["bank"]._transaction_copy()
        core.history = dict(old.history)
        core.history[context] = list(old.history.get(context,[]))
        core.cals = dict(old.cals)
        def cal_copy(cal):
            return {"rows":list(cal["rows"]), "sums":list(cal["sums"])}
        touched = {(leaf,context)}
        rows = old.history.get(context,[])
        if len(rows) == old.config["calibration_window"]:
            touched.add((old._leaf(rows[0][0]),context))
        for key in touched:
            if key in old.cals:
                core.cals[key] = cal_copy(old.cals[key])
        if old.trial is not None:
            core.trial = dict(old.trial)
            core.trial["support"] = [list(row) for row in old.trial["support"]]
            core.trial["outcome_support"] = [list(row) for row in old.trial["outcome_support"]]
            core.trial["width_squares"] = dict(old.trial["width_squares"])
            core.trial["cal"] = {name:dict(values) for name,values in old.trial["cal"].items()}
            for name,values in old.trial["cal"].items():
                if context in values:
                    core.trial["cal"][name][context] = cal_copy(values[context])
        return core

    def capabilities(self):
        result = super().capabilities()
        c = self._learner.config
        result.update(checkpoint_format=3, action_count=c["n_actions"],
                      action_catalogue="fixed for this model; bounded by declared resources",
                      point_budget=c["point_budget"],record_budget=c["record_budget"],
                      validation_horizons=list(self._learner.horizons()))
        return result

    @classmethod
    def from_v2(cls, snapshot, *, point_budget=65536, record_budget=131072):
        old = AdaptiveTraceAdapter.restore(snapshot)
        data = old.checkpoint()
        data["implementation"] = cls.IMPLEMENTATION
        data["learner"] = ActionTraceLearner.from_v2(data["learner"],
            point_budget=point_budget,record_budget=record_budget).checkpoint()
        return cls.restore(data)


class ActionTraceService(AdaptiveTraceService):
    ADAPTER_CLASS = ActionTraceAdapter
    WORK_CLASS = ActionReceiptWork
    WORK_PROTOCOL = "first_piece.action-cooperative.v3"

    def coverage(self, prediction_id=None):
        with self._lock:
            prediction = self._adapter.current_prediction()
            if prediction is None or (prediction_id is not None and prediction_id != prediction["prediction_id"]):
                raise ValueError("Coverage needs the active prediction")
            core = self._adapter._learner
            leaf = core._leaf(core.state)
            counts = [[0,0] for _ in range(core.config["n_actions"])]
            for state,coin,action,outcome in core.history.get(core.context,[]):
                if core._leaf(state) == leaf:
                    counts[action][outcome] += 1
            return {"schema_version":1,"prediction_id":prediction["prediction_id"],
                    "model_revision":self._adapter._revision,
                    "scope":"recent actual labels in current trace leaf and context",
                    "minimum_observations":self.minimum_observations,
                    "actions":[{"candidate_id":f"choice.{i}","observations":sum(row),
                                "positive_outcomes":row[1],
                                "coverage_status":"unobserved" if not sum(row) else
                                    "limited" if sum(row) < self.minimum_observations else "observed"}
                               for i,row in enumerate(counts)],"epistemic_interval":None}

    @classmethod
    def from_v2(cls,snapshot,*,point_budget=65536,record_budget=131072):
        old = AdaptiveTraceService.restore(snapshot)
        data = old.checkpoint()
        data["protocol"] = cls.WORK_PROTOCOL
        data["adapter"] = ActionTraceAdapter.from_v2(data["adapter"],
            point_budget=point_budget,record_budget=record_budget).checkpoint()
        if data["work"] is not None:
            data["work"] = ActionReceiptWork.from_v2(data["work"],
                point_budget=point_budget,record_budget=record_budget).checkpoint()
        return cls.restore(data)
