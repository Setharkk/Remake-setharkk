"""Plastic spherical initialization and predictable validation ranges."""
import copy
import math

from setharkk.contracts import counter
from .calibrated import CalibratedLearner
from .consolidated import COMPARISONS, UNIVERSAL_WIDTH
from .shared import SharedSpherePredictor, log_probability, _integer
from .spherical import log_map, exp_map

FAST_HORIZONS = (128, 512, 1024, 4096, 8192, 16384)
MEAN_ITERATIONS = 8
TILTS = (1, 2, 4, 8)
REFRESH_HORIZONS = (512, 1024)
REFRESH_GAIN = .02


def spherical_mean(points, weights):
    """Deterministic intrinsic mean; source prototypes stay untouched."""
    if len(points) == 1:
        return list(points[0]), 0
    total = sum(weights)
    q, steps = list(points[0]), 0
    for _ in range(MEAN_ITERATIONS):
        tangents = [log_map(q, p) for p in points]
        tangent = [math.fsum(w * t[j] for w, t in zip(weights, tangents)) / total
                   for j in range(3)]
        if math.fsum(v * v for v in tangent) < 1e-24:
            break
        q = exp_map(q, tangent)
        steps += 1
    return q, steps


class PlasticRevisionLearner(CalibratedLearner):
    CHECKPOINT_FORMAT = 6
    IMPLEMENTATION = "first_piece.plastic-revision-s2.v1"

    def __init__(self, *args, reuse_plastic_weights=True,
                 bounded_validation_ranges=True, **kwargs):
        for flag in (reuse_plastic_weights, bounded_validation_ranges):
            if type(flag) is not bool:
                raise ValueError("Invalid revision option")
        super().__init__(*args, **kwargs)
        self.config.update(reuse_plastic_weights=reuse_plastic_weights,
                           bounded_validation_ranges=bounded_validation_ranges)
        self.archived_supersessions = 0
        self.revision_start_attempt = 1
        self.revision_import_at = None
        self._frozen_reference = None
        self._revision_variance = {name: 0.0 for name in COMPARISONS}

    def _horizons(self, attempt=None):
        attempt = max(1, self.attempts) if attempt is None else attempt
        if attempt >= self.revision_start_attempt and self.config["bounded_validation_ranges"]:
            return FAST_HORIZONS
        return super()._horizons(attempt)

    def _max_looks(self):
        return len(FAST_HORIZONS)

    def _served_readout(self, episode, route):
        if self._frozen_reference is not None and self._protected is None:
            return self._frozen_reference["bank"], route
        return super()._served_readout(episode, route)

    def _reference_kind(self):
        if self._protected is not None and self.config["use_structure"]:
            return "protected"
        return "frozen_plastic" if self._frozen_reference is not None else "moving_plastic"

    def _control_probability(self, episode, action):
        if (self.trial is not None and self.attempts >= self.revision_start_attempt
                and self.config["bounded_validation_ranges"]):
            null = self._validation(self.attempts)["conditional_null"]
            counts = null["contexts"].get(str(episode["task"]))
            return null["default"] if counts is None else (counts[1]+1)/(counts[0]+2)
        return super()._control_probability(episode, action)

    @staticmethod
    def _conditional_null(rows):
        contexts = {}
        for slot, mask, before, coin, action, outcome in rows:
            counts = contexts.setdefault(str(slot), [0, 0])
            counts[0] += 1
            counts[1] += outcome
        positive = sum(pair[1] for pair in contexts.values())
        return {"default": (positive+1)/(len(rows)+2), "contexts": contexts}

    def _initialize_banks(self, program, rows):
        candidate, control = self._new_model(), self._new_model()
        report = {"source": "neutral", "at": self.steps, "mapped_records": 0,
                  "mapped_routes": 0, "source_prototype_reads": 0,
                  "geodesic_mean_steps": 0, "ambiguous_means": 0,
                  "transferred_candidate_points": 0, "transferred_control_points": 0,
                  "optimizer_restarted": True,
                  "active_source_updates": sum(map(sum, self.active.counts)),
                  "control_source_updates": sum(map(sum, self.baseline.counts))}
        if not self.config["reuse_plastic_weights"]:
            return candidate, control, report
        mapping, candidate_labels, control_labels = {}, {}, {}
        for slot, mask, before, coin, action, outcome in rows:
            new = self._route(program, slot, mask, before)
            old = self._route(self.program, slot, mask, before) if self.program else coin
            weights = mapping.setdefault(new, {})
            weights[old] = weights.get(old, 0) + 1
            candidate_labels.setdefault((new, action), []).append(outcome)
            control_labels.setdefault((coin, action), []).append(outcome)

        def useful(bank, route, action, value, labels):
            if len(labels) < 8:
                return False
            initial = bank.points[route][action]
            bank.points[route][action] = value
            p = bank.probability(action, route)
            gain = math.fsum(log_probability(p, y) - math.log(.5) for y in labels)
            if gain <= 0:
                bank.points[route][action] = initial
                return False
            return True

        for route, weights in mapping.items():
            source_routes = sorted(weights)
            for action in range(self.config["n_actions"]):
                points = [self.active.points[r][action] for r in source_routes]
                report["source_prototype_reads"] += len(source_routes)
                try:
                    value, steps = spherical_mean(points, [weights[r] for r in source_routes])
                except ValueError:
                    # A valid bank can contain mutually antipodal prototypes.
                    # Keep the declared neutral point rather than choosing an
                    # undefined logarithm direction.
                    report["ambiguous_means"] += 1
                    continue
                report["geodesic_mean_steps"] += steps
                if useful(candidate, route, action, value,
                          candidate_labels.get((route, action), [])):
                    report["transferred_candidate_points"] += 1
        for (route, action), labels in control_labels.items():
            if useful(control, route, action, list(self.baseline.points[route][action]), labels):
                report["transferred_control_points"] += 1
        report.update(source="plastic-geodesic-gated", mapped_records=len(rows),
                      mapped_routes=len(mapping))
        return candidate, control, report

    def _principal_pairs(self, old, new, scope):
        free = sorted(f for f in set(old + new) if f < self.context_offset)
        result = set()
        for slot in range(self.config["max_tasks"]):
            if scope is not None and slot != scope:
                continue
            for pattern in range(1 << len(free)):
                truth = {f: bool(pattern & (1 << j)) for j, f in enumerate(free)}
                def route(program):
                    return sum(int(slot == f - self.context_offset if f >= self.context_offset
                                   else truth[f]) << j for j, f in enumerate(program))
                old_routes = (route(old),) if old else range(self.active.n_routes)
                result.update((r, route(new)) for r in old_routes)
        return result

    def _ranges(self):
        widths = {"relevance": UNIVERSAL_WIDTH, "improvement": UNIVERSAL_WIDTH,
                  "preservation": self._preservation_width()}
        if self.trial is None or not self.config["bounded_validation_ranges"]:
            return widths
        t = self.trial
        def logits(bank):
            return [[log_probability(bank.probability(a, r), 1) -
                     log_probability(bank.probability(a, r), 0)
                     for a in range(self.config["n_actions"])]
                    for r in range(self.active.n_routes)]
        new = logits(self.candidate)
        principal = self._principal_pairs(self.program, t["program"], t["scope"])
        new_routes = {s for _, s in principal}
        null = self._validation(self.attempts)["conditional_null"]
        probabilities = [null["default"]] + [(y+1)/(n+2) for n,y in null["contexts"].values()]
        control = [log_probability(p, 1)-log_probability(p, 0) for p in probabilities]
        widths["relevance"] = max(abs(new[s][a] - value)
            for s in new_routes for value in control
            for a in range(self.config["n_actions"]))
        if self._reference_kind() != "moving_plastic":
            bank = self._protected["bank"] if self._reference_kind() == "protected" else self._frozen_reference["bank"]
            old = logits(bank)
            widths["improvement"] = max(abs(old[r][a] - new[s][a])
                for r, s in principal for a in range(self.config["n_actions"]))
        return widths

    def _start_trial(self, scope):
        counter(self.attempts + 1, "lifetime attempts")
        if len(self.searches) == self.config["max_attempts"]:
            self._compact()
        if sum(task["steps"] > 0 for task in self.tasks.values()) == 1:
            scope = None
        self.attempts += 1
        self._revision_variance = {name: 0.0 for name in COMPARISONS}
        rows = [(slot, *r) for slot in sorted(self.tasks) for r in self.tasks[slot]["records"]]
        program = self._search(rows, scope=scope)
        initialization = None
        if program is None:
            self.decisions.append({"attempt": self.attempts, "at": self.steps, "scope": scope,
                                   "program": None, "decision": "unsupported"})
            self.next_trial = self.steps + self.config["cooldown"]
        else:
            candidate, control, initialization = self._initialize_banks(program, rows)
            if self._protected is None and self.config["use_structure"] and self.config["bounded_validation_ranges"]:
                self._frozen_reference = {"bank": copy.deepcopy(self.active), "at": self.steps}
            for _ in range(self.config["replay_passes"]):
                self.rng.shuffle(rows)
                for slot, mask, before, coin, action, y in rows:
                    candidate.update(action, y, self._route(program, slot, mask, before))
                    control.update(action, y, coin)
            self.neural_updates = counter(self.neural_updates + 2 * len(rows) *
                                         self.config["replay_passes"], "neural updates")
            self.candidate, self.control = candidate, control
            self.trial = {"program": program, "scope": scope, "fit_records": len(rows),
                          "started_at": self.steps, "last_progress_at": self.steps,
                          "fit_required_records": self.required_fit_records(),
                          "fit_updates_per_bank": len(rows) * self.config["replay_passes"],
                          "n": 0, "relevance": 0.0, "improvement": 0.0,
                          "other_n": 0, "preservation": 0.0,
                          "support": [0] * self.active.n_routes}
        mode = "consolidated" if self._protected is not None and self.config["use_structure"] else "plastic"
        self.searches[-1].update(initialization=initialization, validation={
            "horizons": list(self._horizons()), "serve_mode": mode,
            "served_at": self._protected["at"] if mode == "consolidated" else None,
            "reference": self._reference_kind(),
            "conditional_null": self._conditional_null(rows) if program is not None and
                self.config["bounded_validation_ranges"] else None,
            "variance_checks": {name: {} for name in COMPARISONS},
            "refresh_checks": []})
        self.searches[-1]["validation"]["widths"] = self._ranges()

    def _interval(self, gain, n, *, anytime=False, attempt=None, comparison=None):
        attempt = max(1, self.attempts) if attempt is None else attempt
        result = super()._interval(gain, n, anytime=anytime,
                                  attempt=attempt, comparison=comparison)
        if (not n or comparison not in COMPARISONS or
                attempt < self.revision_start_attempt or
                not self.config["bounded_validation_ranges"]):
            return result
        meta = self._validation(attempt)
        width = meta["widths"][comparison]
        checks = meta["variance_checks"][comparison]
        if str(n) not in checks:
            raise ValueError("No declared variance record for this validation look")
        variance = checks[str(n)]
        if comparison == "preservation":
            epoch = n.bit_length() - 1
            scale_n = 1 << epoch
            family = 3 * self.config["max_attempts"] * (epoch+1)*(epoch+2)
        else:
            scale_n = n
            family = 3 * len(self._horizons(attempt)) * self.config["max_attempts"]
        risk = math.log(2 * family * len(TILTS) / self._interval_alpha(attempt))
        if width == 0:
            bound, multiplier = 0.0, TILTS[0]
        else:
            base = math.sqrt(8 * risk / (scale_n * width * width))
            bound, multiplier = min(
                ((risk / (base * scale) + base * scale * variance / 8) / n, scale)
                for scale in TILTS)
        result.update(bound=bound, lower=result["mean"] - bound,
                      variance_proxy=variance, tilt_multiplier=multiplier)
        return result

    def _judge(self):
        if (self.trial is not None and self.attempts >= self.revision_start_attempt
                and self.config["bounded_validation_ranges"] and
                self.trial["n"] in self._horizons()):
            meta = self._validation(self.attempts)
            for name, value in self._revision_variance.items():
                n = self.trial["other_n"] if name == "preservation" else self.trial["n"]
                if n:
                    meta["variance_checks"][name][str(n)] = value
        super()._judge()
        if (self.trial is not None and self.attempts >= self.revision_start_attempt
                and self.config["bounded_validation_ranges"] and
                self._reference_kind() in ("frozen_plastic", "protected")
                and self.trial["n"] in REFRESH_HORIZONS):
            self._refresh_candidate()
        if self.trial is None:
            self._frozen_reference = None
            self._revision_variance = {name: 0.0 for name in COMPARISONS}


    def _fit_score(self, program, rows):
        from .shared import PENALTY
        if program is None:
            return None
        groups = {}
        for slot, mask, before, coin, action, outcome in rows:
            route = self._route(program, slot, mask, before)
            counts = groups.setdefault(route, [[0, 0] for _ in range(self.config["n_actions"])])
            counts[action][outcome] += 1
        if not groups or any(sum(map(sum, counts)) < 16 for counts in groups.values()):
            return None
        score = 0.0
        for counts in groups.values():
            for zero, one in counts:
                score += zero * math.log((zero + 1)/(zero + one + 2))
                score += one * math.log((one + 1)/(zero + one + 2))
        return score / len(rows) - PENALTY * len(program)

    def _refresh_candidate(self):
        """Use past labels to end a stale trial; the next trial spends new risk."""
        t = self.trial
        rows = [(slot, *r) for slot in sorted(self.tasks) for r in self.tasks[slot]["records"]]
        self._search(rows, scope=t["scope"])
        preview = self.searches.pop()
        proposed = preview["program"]
        current_score = self._fit_score(t["program"], rows)
        proposed_score = self._fit_score(proposed, rows)
        check = {"at": self.steps, "n": t["n"], "other_n": t["other_n"], "program": proposed,
                 "current_score": current_score, "proposed_score": proposed_score,
                 **{key: preview[key] for key in ("fit_records", "eligible_features",
                                                 "pooled_features", "hypotheses_examined")}}
        self._validation(self.attempts)["refresh_checks"].append(check)
        if (proposed is not None and proposed != t["program"] and proposed_score is not None
                and (current_score is None or proposed_score - current_score >= REFRESH_GAIN)):
            self._close_unfinished_trial("superseded")
            self.next_trial = self.steps + 1

    def _valid_supersession(self, search, entry):
        meta = search.get("validation", {})
        if (search["attempt"] < self.revision_start_attempt
                or meta.get("reference") not in ("frozen_plastic", "protected") or
                entry["validation_interactions"] not in REFRESH_HORIZONS):
            return False
        checks = [r for r in meta.get("refresh_checks", [])
                  if r["at"] == entry["at"] and r["n"] == entry["validation_interactions"]
                  and r["other_n"] == entry["preservation_interactions"]]
        pending = any(d.get("attempt") == search["attempt"] and d["at"] == entry["at"]
                      and d["decision"] == "pending" for d in self.decisions)
        return bool(pending and len(checks) == 1 and checks[0]["program"] is not None
                    and checks[0]["program"] != search["program"]
                    and checks[0]["proposed_score"] is not None
                    and (checks[0]["current_score"] is None or
                         checks[0]["proposed_score"] - checks[0]["current_score"] >= REFRESH_GAIN))

    def _compact(self):
        decisions = self.decisions
        count = sum(d["decision"] == "superseded" for d in decisions)
        # The inherited archive groups non-admitted inconclusive trials.
        # Keep a separate exact subset count without changing old formats.
        self.decisions = [dict(d, decision="inconclusive") if d["decision"] == "superseded"
                          else d for d in decisions]
        try:
            super()._compact()
        except Exception:
            self.decisions = decisions
            raise
        self.archived_supersessions += count

    def _close_unfinished_trial(self, decision):
        super()._close_unfinished_trial(decision)
        self._frozen_reference = None
        self._revision_variance = {name: 0.0 for name in COMPARISONS}

    def learn(self, action, outcome):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No pending feedback")
        _integer(action, "action", high=self.config["n_actions"] - 1)
        _integer(outcome, "outcome", high=1)
        counter(self.steps + 1, "steps")
        counter(self.neural_updates + 2, "neural updates")
        if self.trial is not None and self.attempts >= self.revision_start_attempt:
            if self._validation(self.attempts)["reference"] != self._reference_kind():
                raise ValueError("Validation reference changed during revision")
            e, t = self.episode, self.trial
            if self.config["bounded_validation_ranges"]:
                new_route = self._route(t["program"], e["task"], e["mask"], e["before"])
                old_route = self._route(self.program, e["task"], e["mask"], e["before"]) if self.program else e["coin"]
                bank, old_route = self._served_readout(e, old_route)
                def logit(p):
                    return log_probability(p, 1) - log_probability(p, 0)
                proposed = logit(self.candidate.probability(action, new_route))
                served = logit(bank.probability(action, old_route))
                if t["scope"] is None or e["task"] == t["scope"]:
                    control = logit(self._control_probability(e, action))
                    self._revision_variance["relevance"] += (proposed-control) ** 2
                    self._revision_variance["improvement"] += (proposed-served) ** 2
                else:
                    self._revision_variance["preservation"] += (proposed-served) ** 2
        return super().learn(action, outcome)

    def _search_keys(self, attempt):
        keys = super()._search_keys(attempt)
        return keys | {"initialization"} if attempt >= self.revision_start_attempt else keys

    def _validate_search(self, search):
        if search["attempt"] < self.revision_start_attempt:
            return super()._validate_search(search)
        from .plastic_revision_state import validate_search
        validate_search(self, search)

    def _after_restore(self):
        super()._after_restore()
        from .plastic_revision_state import validate_revision
        validate_revision(self)

    def _transaction_copy(self):
        child = super()._transaction_copy()
        child._frozen_reference = copy.deepcopy(self._frozen_reference)
        child._revision_variance = dict(self._revision_variance)
        return child

    def checkpoint(self):
        result = super().checkpoint()
        result.update(archived_supersessions=self.archived_supersessions, revision_variance=dict(self._revision_variance), revision_start_attempt=self.revision_start_attempt,
                      revision_import_at=self.revision_import_at,
                      frozen_reference=None if self._frozen_reference is None else {
                          "at": self._frozen_reference["at"],
                          "bank": self._frozen_reference["bank"].checkpoint()})
        return result

    def _restore_history_origin(self, snapshot):
        super()._restore_history_origin(snapshot)
        self.archived_supersessions = counter(snapshot["archived_supersessions"], "archived supersessions")
        if self.archived_supersessions > self.renewal["terminal_counts"]["inconclusive"]:
            raise ValueError("Supersessions exceed archived non-admissions")
        variance = snapshot["revision_variance"]
        if type(variance) is not dict or set(variance) != set(COMPARISONS):
            raise ValueError("Invalid revision variance fields")
        from .criterion import _finite_number
        self._revision_variance = {name: _finite_number(value, "variance proxy")
                                   for name, value in variance.items()}
        if any(value < 0 for value in self._revision_variance.values()):
            raise ValueError("Negative revision variance")
        self.revision_start_attempt = counter(snapshot["revision_start_attempt"], "revision frontier", minimum=1)
        at = snapshot["revision_import_at"]
        if self.revision_start_attempt > snapshot["attempts"] + 1:
            raise ValueError("Revision starts beyond future attempt")
        if at is not None:
            if counter(at, "revision import") > snapshot["steps"]:
                raise ValueError("Revision import is in the future")
        elif self.revision_start_attempt != 1:
            raise ValueError("Revision frontier without explicit import")
        self.revision_import_at = at
        frozen = snapshot["frozen_reference"]
        if frozen is not None:
            if type(frozen) is not dict or set(frozen) != {"at", "bank"}:
                raise ValueError("Invalid frozen plastic reference")
            bank = SharedSpherePredictor.restore(frozen["bank"])
            if (bank.n_actions != self.config["n_actions"] or
                    bank.n_routes != 2 ** self.config["max_features"] or
                    bank.rate != self.config["rate"]):
                raise ValueError("Frozen reference capacity differs")
            self._frozen_reference = {"at": counter(frozen["at"], "frozen exposure"), "bank": bank}

    @classmethod
    def from_calibrated_checkpoint(cls, snapshot):
        old = CalibratedLearner.restore(snapshot)
        model = cls(**old.config)
        model.__dict__.update(copy.deepcopy(old.__dict__))
        model.config.update(reuse_plastic_weights=True, bounded_validation_ranges=True)
        model.revision_start_attempt, model.revision_import_at = old.attempts + 1, old.steps
        model._frozen_reference = None
        return cls.restore(model.checkpoint()).checkpoint()

    @classmethod
    def from_consolidated_checkpoint(cls, snapshot):
        return cls.from_calibrated_checkpoint(CalibratedLearner.from_consolidated_checkpoint(snapshot))

    @classmethod
    def from_renewable_checkpoint(cls, snapshot):
        return cls.from_calibrated_checkpoint(CalibratedLearner.from_renewable_checkpoint(snapshot))

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        return cls.from_calibrated_checkpoint(CalibratedLearner.from_finite_checkpoint(snapshot))

    def metrics(self):
        result = super().metrics()
        extra = self.active.n_routes * self.config["n_actions"] if self._frozen_reference else 0
        result.update(search_mode="plastic_revision",
                      supersessions=self.archived_supersessions + sum(d["decision"] == "superseded" for d in self.decisions),
                      reuse_plastic_weights=self.config["reuse_plastic_weights"],
                      bounded_validation_ranges=self.config["bounded_validation_ranges"],
                      revision_start_attempt=self.revision_start_attempt,
                      revision_import_at=self.revision_import_at,
                      frozen_reference_points=extra,
                      validation_reference_kind=self._reference_kind(),
                      allocated_points_including_trial=result["allocated_points_including_trial"] + extra,
                      plastic_initialization_searches=sum(s.get("initialization", {}).get("source") == "plastic-geodesic-gated"
                          for s in self.searches if s.get("initialization") is not None))
        return result
