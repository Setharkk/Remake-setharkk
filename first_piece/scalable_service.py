"""Resource-scaled S2 service with separately retained observed coverage."""
import copy
import threading

from setharkk import contracts as wire
from .action_service import ActionTraceAdapter, ActionTraceService
from .action_trace import configuration, record_reservation
from .coverage import CoverageLedger


class ScalableActionService(ActionTraceService):
    WORK_PROTOCOL = "first_piece.scalable-action-cooperative.v1"

    def __init__(self, *, minimum_observations=32, coverage_window=32,
                 coverage_max_age=None, **adapter_options):
        wire.counter(minimum_observations, "minimum observations", minimum=1)
        wire.counter(coverage_window, "coverage window", minimum=minimum_observations)
        options = copy.deepcopy(adapter_options.get("learner_options") or {})
        actions = adapter_options.get("actions", ("lab.action.0", "lab.action.1"))
        if not isinstance(actions, (tuple, list)):
            raise ValueError("Invalid action catalogue")
        if "n_actions" in options and options["n_actions"] != len(actions):
            raise ValueError("Action catalogue and learner differ")
        options["n_actions"] = len(actions)
        c = configuration(adapter_options.get("seed", 0), **options)
        slots = c["max_tasks"]*c["max_leaves"]*c["n_actions"]*coverage_window
        wire.counter(slots, "coverage reservation", minimum=1)
        age = max(4096, 4*slots) if coverage_max_age is None else coverage_max_age
        wire.counter(age, "coverage age", minimum=1)
        records = record_reservation(c["max_leaves"], c["window"], c["max_tasks"],
                                     c["calibration_window"], c["max_symbols"])
        if records+slots > c["record_budget"]:
            raise ValueError("Learning and coverage exceed the combined record budget")
        self._adapter = self.ADAPTER_CLASS(**adapter_options)
        self._work = None
        self._lock = threading.RLock()
        self.minimum_observations = minimum_observations
        self._coverage = CoverageLedger(self._adapter._learner, window=coverage_window, max_age=age)

    def _prepare_publication(self, work):
        if work.receipt["status"] != "observed":
            return self._coverage
        return self._coverage.after_receipt(self._adapter._learner, work.core,
                    work.action, work.receipt["outcome"]["value"])

    def _publish_auxiliary(self, publication):
        self._coverage = publication

    def coverage(self, prediction_id=None):
        with self._lock:
            prediction = self._adapter.current_prediction()
            if prediction is None or (prediction_id is not None and prediction_id != prediction["prediction_id"]):
                raise ValueError("Coverage needs the active prediction")
            core = self._adapter._learner
            leaf = core._leaf(core.state)
            actions = []
            for action in range(core.config["n_actions"]):
                counts = self._coverage.counts(core, leaf, core.context, action)
                n = counts["observations"]
                actions.append({"candidate_id": f"choice.{action}", **counts,
                                "coverage_status": "unobserved" if not n else
                                    "limited" if n < self.minimum_observations else "observed"})
            return {"schema_version": 1, "prediction_id": prediction["prediction_id"],
                    "model_revision": self._adapter._revision,
                    "scope": "recent actual labels per action in current trace leaf and context",
                    "minimum_observations": self.minimum_observations,
                    "window_per_action_leaf_context": self._coverage.window,
                    "max_age_model_revisions": self._coverage.max_age,
                    "coverage_started_at_revision": self._coverage.started_at,
                    "actions": actions, "epistemic_interval": None}

    def capabilities(self):
        with self._lock:
            result = super().capabilities()
            core = self._adapter._learner
            result.update(service_checkpoint_format=2,
                          max_depth=core.config["max_depth"],
                          coverage_window=self._coverage.window,
                          coverage_max_age_model_revisions=self._coverage.max_age,
                          coverage_reserved_record_slots=self._coverage.reserved_slots,
                          combined_reserved_record_slots=core.metrics(detailed=False)["reserved_record_slots"]+self._coverage.reserved_slots,
                          coverage="observed counts per action/leaf/context; no epistemic confidence")
            return result

    def metrics(self, *, detailed=True):
        with self._lock:
            result = super().metrics(detailed=detailed)
            result.update(coverage_retained_labels=sum(map(len, self._coverage.buckets.values())),
                          coverage_reserved_record_slots=self._coverage.reserved_slots)
            return result

    def checkpoint(self):
        with self._lock:
            return {**super().checkpoint(), "format": 2, "coverage": self._coverage.checkpoint()}

    @classmethod
    def restore(cls, snapshot):
        fields = {"format", "protocol", "minimum_observations", "adapter", "work", "coverage"}
        if (type(snapshot) is not dict or set(snapshot) != fields
                or type(snapshot["format"]) is not int or snapshot["format"] != 2
                or snapshot["protocol"] != cls.WORK_PROTOCOL):
            raise ValueError("Invalid scalable service checkpoint")
        adapter = cls.ADAPTER_CLASS.restore(snapshot["adapter"])
        ledger = CoverageLedger.restore(snapshot["coverage"], adapter._learner)
        options = {k: v for k, v in adapter._learner.config.items() if k != "seed"}
        new = cls(minimum_observations=snapshot["minimum_observations"],
                  coverage_window=ledger.window, coverage_max_age=ledger.max_age,
                  actions=adapter.actions, learner_options=options,
                  seed=adapter._learner.config["seed"])
        new._adapter, new._coverage = adapter, ledger
        if snapshot["work"] is not None:
            new._work = cls.WORK_CLASS.restore(snapshot["work"])
            pending = adapter._pending
            if (pending is None or new._work.receipt["request_id"] != pending["request_id"]
                    or new._work.receipt["source_id"] != pending["executor_id"]):
                raise ValueError("Work and pending request differ")
            learned = new._work.receipt["status"] == "observed"
            delta = int(learned and new._work.phase != "feedback")
            if (new._work.core.steps != adapter._learner.steps+delta
                    or new._work.action != adapter.actions.index(pending["action_name"])
                    or new._work.core.config != adapter._learner.config):
                raise ValueError("Staged action, capacity or exposure differs")
        return new

    @classmethod
    def from_adapter_checkpoint(cls, snapshot, *, minimum_observations=32, **coverage_options):
        adapter = cls.ADAPTER_CLASS.restore(snapshot)
        options = {k: v for k, v in adapter._learner.config.items() if k != "seed"}
        new = cls(minimum_observations=minimum_observations, actions=adapter.actions,
                  seed=adapter._learner.config["seed"], learner_options=options, **coverage_options)
        new._adapter = adapter
        new._coverage = CoverageLedger(adapter._learner, window=new._coverage.window,
            max_age=new._coverage.max_age, started_at=adapter._learner.steps)
        return new

    @classmethod
    def from_v3(cls, snapshot, **coverage_options):
        old = ActionTraceService.restore(snapshot)
        new = cls.from_adapter_checkpoint(old._adapter.checkpoint(),
            minimum_observations=old.minimum_observations, **coverage_options)
        new._work = old._work
        return new

    @classmethod
    def from_v2(cls, snapshot, *, point_budget=65536, record_budget=131072, **coverage_options):
        old = ActionTraceService.from_v2(snapshot, point_budget=point_budget, record_budget=record_budget)
        return cls.from_v3(old.checkpoint(), **coverage_options)
