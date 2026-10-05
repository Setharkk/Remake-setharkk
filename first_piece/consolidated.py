"""A protected spherical competence plus renewable prospective revision."""
import copy
import math

from setharkk.contracts import counter
from .shared import EPSILON, HORIZONS, SharedSpherePredictor, log_probability
from .renewable import RenewableLearner

EXTENDED_HORIZONS = (*HORIZONS, 8192, 16384)
UNIVERSAL_WIDTH = -2 * math.log(EPSILON)
COMPARISONS = ("relevance", "improvement", "preservation")


class ConsolidatedLearner(RenewableLearner):
    CHECKPOINT_FORMAT = 4
    IMPLEMENTATION = "first_piece.consolidated-compositions-s2.v1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._protected = None
        self.policy_start_attempt = 1
        self.import_at = None

    def _horizons(self, attempt=None):
        attempt = max(1, self.attempts) if attempt is None else attempt
        return HORIZONS if attempt < self.policy_start_attempt else EXTENDED_HORIZONS

    def _max_looks(self):
        return len(EXTENDED_HORIZONS)

    def _served_readout(self, episode, route):
        if self._protected is not None and self.config["use_structure"]:
            return self._protected["bank"], route
        return super()._served_readout(episode, route)

    def _on_accept(self):
        self._protected = {"bank": copy.deepcopy(self.active), "at": self.steps,
                           "source": "admission", "program": list(self.program)}

    def _joint_routes(self, old, proposed, scope):
        # Enumerate an OVER-approximation of all feature truth assignments.
        # Context equalities use their actual slot value; all other predicates
        # are allowed to vary freely, including mutually impossible assignments.
        # This cannot omit a possible future route pair.
        free = sorted(f for f in set(old + proposed) if f < self.context_offset)
        pairs = set()
        for slot in range(self.config["max_tasks"]):
            if slot == scope:
                continue
            for pattern in range(1 << len(free)):
                truth = {f: bool(pattern & (1 << j)) for j, f in enumerate(free)}
                def route(program):
                    return sum(int(slot == f - self.context_offset if f >= self.context_offset
                                   else truth[f]) << j for j, f in enumerate(program))
                pairs.add((route(old), route(proposed)))
        return pairs

    def _preservation_width(self):
        t = self.trial
        if t is None or t["scope"] is None or self._protected is None or not self.config["use_structure"]:
            return UNIVERSAL_WIDTH
        old = self._protected
        old_logits = [[log_probability(old["bank"].probability(a, r), 1) -
                       log_probability(old["bank"].probability(a, r), 0)
                       for a in range(self.config["n_actions"])]
                      for r in range(self.active.n_routes)]
        new_logits = [[log_probability(self.candidate.probability(a, r), 1) -
                       log_probability(self.candidate.probability(a, r), 0)
                       for a in range(self.config["n_actions"])]
                      for r in range(self.active.n_routes)]
        pairs = self._joint_routes(old["program"], t["program"], t["scope"])
        return max((abs(old_logits[r][a] - new_logits[s][a])
                    for r, s in pairs for a in range(self.config["n_actions"])), default=0.0)

    def _validation(self, attempt):
        offset = self.renewal["archived_attempts"]
        index = attempt - offset - 1
        if not 0 <= index < len(self.searches):
            raise ValueError("Validation refers to an archived or absent search")
        return self.searches[index]["validation"]

    def _start_trial(self, scope):
        super()._start_trial(scope)
        mode = "consolidated" if self._protected is not None and self.config["use_structure"] else "plastic"
        self.searches[-1]["validation"] = {
            "horizons": list(EXTENDED_HORIZONS), "serve_mode": mode,
            "served_at": self._protected["at"] if mode == "consolidated" else None,
            "widths": {"relevance": UNIVERSAL_WIDTH, "improvement": UNIVERSAL_WIDTH,
                       "preservation": self._preservation_width()},
        }

    def _interval(self, gain, n, *, anytime=False, attempt=None, comparison=None):
        attempt = max(1, self.attempts) if attempt is None else attempt
        result = super()._interval(gain, n, anytime=anytime, attempt=attempt, comparison=comparison)
        if attempt < self.policy_start_attempt:
            return result
        width = UNIVERSAL_WIDTH
        if comparison is not None:
            width = self._validation(attempt)["widths"][comparison]
        if n:
            result["bound"] *= width / UNIVERSAL_WIDTH
            result["lower"] = result["mean"] - result["bound"]
        result["range_width"] = width
        return result

    def learn(self, action, outcome):
        # Guard the frozen-reference assumption before any label is consumed.
        if self.trial is not None and self.attempts >= self.policy_start_attempt:
            meta = self._validation(self.attempts)
            mode = "consolidated" if self._protected is not None and self.config["use_structure"] else "plastic"
            at = self._protected["at"] if mode == "consolidated" else None
            if meta["serve_mode"] != mode or meta["served_at"] != at:
                raise ValueError("Served validation reference changed during a trial")
        return super().learn(action, outcome)

    def _search_keys(self, attempt):
        keys = super()._search_keys(attempt)
        return keys | {"validation"} if attempt >= self.policy_start_attempt else keys

    def _validate_search(self, search):
        from .consolidated_state import validate_search
        validate_search(self, search)

    def _after_restore(self):
        from .consolidated_state import validate_memory
        validate_memory(self)

    def _transaction_copy(self, *, context=None):
        child = super()._transaction_copy(context=context)
        child._protected = copy.deepcopy(self._protected) if context is None else self._protected
        return child

    def checkpoint(self):
        result = super().checkpoint()
        result.update(policy_start_attempt=self.policy_start_attempt, import_at=self.import_at,
                      protected=None if self._protected is None else {
                          **self._protected, "bank": self._protected["bank"].checkpoint()})
        return result

    def _restore_history_origin(self, snapshot):
        super()._restore_history_origin(snapshot)
        self.policy_start_attempt = counter(snapshot["policy_start_attempt"], "policy frontier", minimum=1)
        if self.policy_start_attempt > snapshot["attempts"] + 1:
            raise ValueError("Policy frontier exceeds lifetime attempts")
        at = snapshot["import_at"]
        if at is not None and counter(at, "import exposure") > snapshot["steps"]:
            raise ValueError("Import frontier exceeds learned exposure")
        if at is None and self.policy_start_attempt != 1:
            raise ValueError("Policy frontier without an explicit import")
        self.import_at = at
        protected = snapshot["protected"]
        if protected is not None:
            if type(protected) is not dict or set(protected) != {"bank", "at", "source", "program"}:
                raise ValueError("Invalid protected competence fields")
            bank = SharedSpherePredictor.restore(protected["bank"])
            if bank.n_actions != self.config["n_actions"] or bank.n_routes != 2 ** self.config["max_features"] or bank.rate != self.config["rate"]:
                raise ValueError("Protected spherical bank differs from capacity")
            counter(protected["at"], "protected exposure")
            if protected["source"] not in ("admission", "import"):
                raise ValueError("Invalid protected source")
            self._protected = {**copy.deepcopy(protected), "bank": bank}

    @classmethod
    def from_renewable_checkpoint(cls, snapshot):
        old = RenewableLearner.restore(snapshot)
        data = old.checkpoint()
        data.update(format=cls.CHECKPOINT_FORMAT, implementation=cls.IMPLEMENTATION,
                    policy_start_attempt=old.attempts + 1, import_at=old.steps,
                    protected=None if not old.program else {
                        "bank": old.active.checkpoint(), "at": old.steps,
                        "source": "import", "program": list(old.program)})
        return cls.restore(data).checkpoint()

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        return cls.from_renewable_checkpoint(RenewableLearner.from_finite_checkpoint(snapshot))

    @classmethod
    def migrate_checkpoint_v1(cls, snapshot):
        raise ValueError("Migrate with SharedLearner, then use from_finite_checkpoint")

    def metrics(self, *, detailed=True):
        result = super().metrics(detailed=detailed)
        protected_points = 0 if self._protected is None else self.active.n_routes * self.config["n_actions"]
        points = result["live_points_including_control"] + protected_points
        result.update({
            "search_mode": "consolidated", "served_bank": "consolidated" if
                self._protected is not None and self.config["use_structure"] else "plastic",
            "protected_points": protected_points,
            "protected_at": None if self._protected is None else self._protected["at"],
            "live_points_including_control": points,
            "allocated_points_including_trial": points + (
                2 * self.active.n_routes * self.config["n_actions"] if self.trial else 0),
            "intrinsic_live_dof": points * 2,
            "intrinsic_peak_dof": (3 + 2) * self.active.n_routes * self.config["n_actions"] * 2,
            "validation_horizons": list(self._horizons()),
            "history_decision_limit": self.config["max_attempts"] * self._max_looks(),
            "policy_start_attempt": self.policy_start_attempt,
            "import_at": self.import_at,
        })
        return result
