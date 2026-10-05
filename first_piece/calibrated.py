"""Recent-outcome calibration around an unchanged protected S2 competence."""
import copy
import math

from setharkk.contracts import counter
from .consolidated import ConsolidatedLearner
from .shared import _integer
from .criterion import _finite_number

WINDOW = 256
MIN_RECORDS = 32
CONTRAST_FLOOR = 1e-6
POLICY = "rolling-mixture-v1"


def empty_cache():
    return {"probabilities": [], "sums": [0.0, 0.0, 0.0, 0.0]}


def summed(probabilities, records):
    return [math.fsum(probabilities), float(sum(row[4] for row in records)),
            math.fsum(p * p for p in probabilities),
            math.fsum(p * row[4] for p, row in zip(probabilities, records))]


class CalibratedLearner(ConsolidatedLearner):
    CHECKPOINT_FORMAT = 5
    IMPLEMENTATION = "first_piece.calibrated-compositions-s2.v1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._calibration = {}
        self.pending_import_at = None

    def _calibration_enabled(self):
        return self._protected is not None and self.config["use_structure"]

    def _window(self):
        return min(WINDOW, self.config["fit_per_context"])

    def _record_probability(self, slot, row):
        route = self._route(self.program, slot, row[0], row[1])
        return self._protected["bank"].probability(row[3], route)

    def _rebuild_calibration(self):
        self._calibration = {}
        if self._calibration_enabled():
            for slot, task in self.tasks.items():
                rows = task["records"][-self._window():]
                probabilities = [self._record_probability(slot, row) for row in rows]
                self._calibration[slot] = {"probabilities": probabilities,
                                          "sums": summed(probabilities, rows)}

    def _on_accept(self):
        super()._on_accept()
        # Routes and weights may have changed. Reproject PAST labelled rows
        # through the newly admitted bank, without a neural update or new data.
        self._rebuild_calibration()

    def receive(self, event):
        result = super().receive(event)
        if self._calibration_enabled():
            self._calibration.setdefault(event["task"], empty_cache())
        return result

    def calibration_parameters(self, slot):
        cache = self._calibration.get(slot, empty_cache())
        n = len(cache["probabilities"])
        if n < MIN_RECORDS:
            return {"observations": n, "background_rate": None,
                    "retained_contrast": 1.0, "active": False}
        sp, sy, spp, spy = cache["sums"]
        background = max(0.0, min(1.0, sy / n))
        denominator = spp - 2 * background * sp + n * background * background
        numerator = spy - background * sp
        contrast = 1.0 if denominator <= 1e-12 else max(
            CONTRAST_FLOOR, min(1.0, numerator / denominator))
        return {"observations": n, "background_rate": background,
                "retained_contrast": contrast, "active": True}

    def pending_probabilities(self):
        probabilities = super().pending_probabilities()
        if not self._calibration_enabled() or self.pending_import_at is not None:
            return probabilities
        params = self.calibration_parameters(self.episode["task"])
        if not params["active"]:
            return probabilities
        b, contrast = params["background_rate"], params["retained_contrast"]
        return [(1 - contrast) * b + contrast * p for p in probabilities]

    def finish_evaluation(self):
        super().finish_evaluation()
        self.pending_import_at = None

    def learn(self, action, outcome):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No pending feedback")
        _integer(action, "action", high=self.config["n_actions"] - 1)
        _integer(outcome, "outcome", high=1)
        served = self.pending_probabilities()[action]
        enabled = self._calibration_enabled()
        slot, admissions = self.episode["task"], self.admissions
        raw = super().pending_probabilities()[action]
        dropped = None
        if enabled:
            cache = self._calibration[slot]
            if len(cache["probabilities"]) == self._window():
                dropped = (cache["probabilities"][0],
                           self.tasks[slot]["records"][-self._window()][4])
        # Search triggers and prospective decisions still score the RAW
        # competence. Calibration cannot suppress replacement of a bad rule.
        super().learn(action, outcome)
        if enabled and self.admissions == admissions:
            cache = self._calibration[slot]
            if dropped is not None:
                p, y = dropped
                cache["probabilities"].pop(0)
                cache["sums"] = [v - x for v, x in zip(
                    cache["sums"], (p, y, p * p, p * y))]
            cache["probabilities"].append(raw)
            cache["sums"] = [v + x for v, x in zip(
                cache["sums"], (raw, outcome, raw * raw, raw * outcome))]
            if self.tasks[slot]["steps"] % self._window() == 0:
                cache["sums"] = summed(cache["probabilities"],
                                      self.tasks[slot]["records"][-self._window():])
        self.pending_import_at = None
        return served

    def _observation_copy(self):
        child = super()._observation_copy()
        child._calibration = dict(self._calibration)
        return child

    def _transaction_copy(self, *, context=None):
        child = super()._transaction_copy(context=context)
        if context is None:
            child._calibration = copy.deepcopy(self._calibration)
        else:
            child._calibration = dict(self._calibration)
            if context in child._calibration:
                cache = self._calibration[context]
                child._calibration[context] = {"probabilities": list(cache["probabilities"]),
                                               "sums": list(cache["sums"])}
        return child

    def checkpoint(self):
        result = super().checkpoint()
        result["calibration"] = {
            "policy": POLICY, "window": WINDOW, "min_records": MIN_RECORDS,
            "contrast_floor": CONTRAST_FLOOR,
            "pending_import_at": self.pending_import_at,
            "contexts": {str(slot): copy.deepcopy(cache)
                         for slot, cache in self._calibration.items()}}
        return result

    def _restore_history_origin(self, snapshot):
        super()._restore_history_origin(snapshot)
        data = snapshot["calibration"]
        if type(data) is not dict or set(data) != {
                "policy", "window", "min_records", "contrast_floor",
                "pending_import_at", "contexts"}:
            raise ValueError("Invalid calibration fields")
        if (data["policy"] != POLICY or type(data["window"]) is not int
                or data["window"] != WINDOW or type(data["min_records"]) is not int
                or data["min_records"] != MIN_RECORDS
                or _finite_number(data["contrast_floor"], "contrast floor") != CONTRAST_FLOOR):
            raise ValueError("Undeclared calibration policy")
        at = data["pending_import_at"]
        if at is not None:
            counter(at, "pending import exposure")
            if at != snapshot["steps"] or snapshot["episode"].get("phase") != "feedback":
                raise ValueError("Pending import outside feedback boundary")
        self.pending_import_at = at
        contexts = data["contexts"]
        if type(contexts) is not dict:
            raise ValueError("Invalid calibration contexts")
        self._calibration = {}
        for key, cache in contexts.items():
            if type(key) is not str or not key.isdecimal() or str(int(key)) != key:
                raise ValueError("Invalid calibration slot")
            slot = _integer(int(key), "calibration slot", high=self.config["max_tasks"] - 1)
            if type(cache) is not dict or set(cache) != {"probabilities", "sums"}:
                raise ValueError("Invalid calibration cache fields")
            probs, sums = cache["probabilities"], cache["sums"]
            if type(probs) is not list or len(probs) > self._window():
                raise ValueError("Calibration cache exceeds window")
            if any(not 0 <= _finite_number(p, "cached probability") <= 1 for p in probs):
                raise ValueError("Invalid cached probability")
            if type(sums) is not list or len(sums) != 4:
                raise ValueError("Invalid calibration moment shape")
            for value in sums:
                _finite_number(value, "calibration moment")
            self._calibration[slot] = copy.deepcopy(cache)

    def _after_restore(self):
        super()._after_restore()
        expected_slots = set(self.tasks) if self._calibration_enabled() else set()
        if set(self._calibration) != expected_slots:
            raise ValueError("Calibration contexts differ from live competence")
        for slot, cache in self._calibration.items():
            rows = self.tasks[slot]["records"][-self._window():]
            if len(cache["probabilities"]) != len(rows):
                raise ValueError("Calibration window differs from labelled memory")
            for p, row in zip(cache["probabilities"], rows):
                if not math.isclose(p, self._record_probability(slot, row),
                                    rel_tol=0, abs_tol=1e-12):
                    raise ValueError("Calibration probability differs from protected bank")
            expected = summed(cache["probabilities"], rows)
            if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10)
                   for a, b in zip(cache["sums"], expected)):
                raise ValueError("Calibration moments differ from cached observations")

    @classmethod
    def from_consolidated_checkpoint(cls, snapshot):
        old = ConsolidatedLearner.restore(snapshot)
        # Restore the calibrated shell only AFTER the old model is validated.
        model = cls(**old.config)
        model.__dict__.update(copy.deepcopy(old.__dict__))
        model._rebuild_calibration()
        model.pending_import_at = old.steps if old.episode["phase"] == "feedback" else None
        return cls.restore(model.checkpoint()).checkpoint()

    @classmethod
    def from_renewable_checkpoint(cls, snapshot):
        return cls.from_consolidated_checkpoint(
            ConsolidatedLearner.from_renewable_checkpoint(snapshot))

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        return cls.from_consolidated_checkpoint(
            ConsolidatedLearner.from_finite_checkpoint(snapshot))

    def metrics(self, *, detailed=True):
        result = super().metrics(detailed=detailed)
        result.update(
            search_mode="calibrated",
            calibration_policy=POLICY,
            validation_reference="raw_protected_competence",
            search_trigger_score="raw_competence_brier",
            calibration_window=self._window(),
            calibration_probability_cache=sum(
                len(c["probabilities"]) for c in self._calibration.values()),
            calibration_moment_scalars=4 * len(self._calibration),
            calibration_by_context={str(slot): self.calibration_parameters(slot)
                                    for slot in self.tasks},
            pending_import_at=self.pending_import_at)
        return result
