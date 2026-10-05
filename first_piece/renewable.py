"""Renewable structural search with summable lifetime risk and bounded history."""
import copy
from setharkk.contracts import counter
from .shared import ALPHA, HORIZONS, SharedLearner

TERMINALS = ("accept", "futile", "inconclusive", "unsupported", "expired", "migrated")


class RenewableLearner(SharedLearner):
    CHECKPOINT_FORMAT = 3
    IMPLEMENTATION = "first_piece.renewable-compositions-s2.v1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.renewal = {
            "archived_attempts": 0, "archived_fit_records": 0,
            "archived_admissions": 0, "archived_at": -1, "last_admission": None,
            "terminal_counts": {name: 0 for name in TERMINALS},
            "legacy_first_block": False,
        }

    def _history_origin(self):
        return self.renewal

    def _attempt_limit(self):
        # All public counters remain exactly representable in JSON consumers.
        return 2 ** 53 - 1

    def _interval_alpha(self, attempt=None):
        attempt = self.attempts if attempt is None else attempt
        block = (max(1, attempt) - 1) // self.config["max_attempts"] + 1
        if self.renewal["legacy_first_block"]:
            # The imported finite engine already allocated .05 to its first
            # block. Never retrospectively claim that it spent only .025.
            return ALPHA if block == 1 else ALPHA / (block * (block - 1))
        return ALPHA / (block * (block + 1))

    def _compact(self):
        if self.trial is not None or len(self.searches) != self.config["max_attempts"]:
            raise RuntimeError("Only a completed full search block may be archived")
        r = copy.deepcopy(self.renewal)
        searches = {s["attempt"]: s for s in self.searches}
        finals = [d for d in self.decisions if d["decision"] != "pending"]
        if len(finals) != len(self.searches):
            raise RuntimeError("Cannot archive incomplete search lineage")
        r["archived_fit_records"] = counter(r["archived_fit_records"] +
            sum(s["fit_records"] for s in self.searches if s["program"] is not None),
            "archived fits")
        for entry in finals:
            name = entry["decision"]
            r["terminal_counts"][name] = counter(r["terminal_counts"][name] + 1,
                                                  "archived terminal count")
            if name == "accept":
                r["archived_admissions"] = counter(r["archived_admissions"] + 1,
                                                    "archived admissions")
                r["last_admission"] = {
                    "attempt": entry["attempt"], "at": entry["at"],
                    "fit_records": searches[entry["attempt"]]["fit_records"],
                    "program": list(entry["program"]),
                }
        r["archived_attempts"] = self.attempts
        r["archived_at"] = finals[-1]["at"]
        self.renewal = r
        self.searches = []
        self.decisions = []

    def _start_trial(self, scope):
        counter(self.attempts + 1, "lifetime attempts")
        if len(self.searches) == self.config["max_attempts"]:
            self._compact()
        super()._start_trial(scope)

    def _transaction_copy(self, *, context=None):
        child = super()._transaction_copy(context=context)
        child.renewal = copy.deepcopy(self.renewal)
        return child

    def checkpoint(self):
        result = super().checkpoint()
        result["renewal"] = copy.deepcopy(self.renewal)
        return result

    def _restore_history_origin(self, snapshot):
        r = snapshot["renewal"]
        if type(r) is not dict or set(r) != set(self.renewal):
            raise ValueError("Invalid renewal ledger fields")
        if type(r["legacy_first_block"]) is not bool:
            raise ValueError("Invalid imported budget flag")
        for name in ("archived_attempts", "archived_fit_records", "archived_admissions"):
            counter(r[name], name)
        archived_at = counter(r["archived_at"], "archive frontier", minimum=-1)
        counter(snapshot["attempts"], "lifetime attempts")
        counter(snapshot["steps"], "feedback exposure")
        a = r["archived_attempts"]
        if a % self.config["max_attempts"] or not 0 <= snapshot["attempts"] - a <= self.config["max_attempts"]:
            raise ValueError("Archive is not a completed block prefix")
        counts = r["terminal_counts"]
        if type(counts) is not dict or set(counts) != set(TERMINALS):
            raise ValueError("Invalid archived terminal fields")
        for value in counts.values():
            counter(value, "terminal count")
        if sum(counts.values()) != a or counts["accept"] != r["archived_admissions"]:
            raise ValueError("Archive count lineage differs")
        supported = a - counts["unsupported"]
        fit = r["archived_fit_records"]
        if not 64 * supported <= fit <= supported * self.config["max_tasks"] * self.config["fit_per_context"]:
            raise ValueError("Impossible archived fit total")
        if bool(a) != (archived_at >= 0) or archived_at > snapshot["steps"]:
            raise ValueError("Invalid archived exposure")
        if not a and (fit or r["archived_admissions"] or archived_at != -1):
            raise ValueError("Dirty empty renewal ledger")
        last = r["last_admission"]
        if (last is not None) != bool(r["archived_admissions"]):
            raise ValueError("Missing archived admission lineage")
        if last is not None:
            if type(last) is not dict or set(last) != {"attempt", "at", "fit_records", "program"}:
                raise ValueError("Invalid archived last admission")
            if not 1 <= counter(last["attempt"], "last admitted attempt") <= a:
                raise ValueError("Archived admission outside prefix")
            if not 64 <= counter(last["fit_records"], "last admitted fit") <= self.config["max_tasks"] * self.config["fit_per_context"]:
                raise ValueError("Archived admission fit outside capacity")
            if not last["fit_records"] <= counter(last["at"], "last admitted exposure") <= archived_at:
                raise ValueError("Archived admission exposure differs")
        if counts["migrated"] and not r["legacy_first_block"]:
            raise ValueError("Fresh renewal ledger contains a legacy closure")
        self.renewal = copy.deepcopy(r)

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        """Explicit import: preserve .05 historical + .05 future risk budgets."""
        finite = SharedLearner.restore(snapshot)
        data = finite.checkpoint()
        data["format"], data["implementation"] = cls.CHECKPOINT_FORMAT, cls.IMPLEMENTATION
        data["renewal"] = cls(**data["config"]).renewal
        data["renewal"]["legacy_first_block"] = True
        return cls.restore(data).checkpoint()

    @classmethod
    def migrate_checkpoint_v1(cls, snapshot):
        raise ValueError("Migrate with SharedLearner.migrate_checkpoint_v1, then from_finite_checkpoint")

    def metrics(self, *, detailed=True):
        result = super().metrics(detailed=detailed)
        block = (max(1, self.attempts) - 1) // self.config["max_attempts"] + 1
        legacy = self.renewal["legacy_first_block"]
        allocated = ALPHA * (2 - 1 / block) if legacy else ALPHA * block / (block + 1)
        result.update({
            "status": "validating" if self.trial else "tracking",
            "search_mode": "renewable", "search_block": block,
            "attempts_per_block": self.config["max_attempts"],
            "block_alpha": self._interval_alpha(),
            "lifetime_alpha_upper_bound": 2 * ALPHA if legacy else ALPHA,
            "allocated_alpha_upper_bound": allocated,
            "renewal": copy.deepcopy(self.renewal),
            "history_search_limit": self.config["max_attempts"],
            "history_decision_limit": self.config["max_attempts"] * len(HORIZONS),
        })
        return result
