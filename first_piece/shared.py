"""Bounded composition search and a single spherical bank shared by contexts.

This is a synthetic streaming learner, not a general autonomous controller.
Real trainable parameters are S2 points; symbolic routing is discrete.
"""
import copy
import itertools
import math
import random
import re
import time

from setharkk.contracts import counter, identifier, json_value
from .criterion import _finite_number
from .spherical import SpherePredictor, learnable_point, unit
from .world import _integer, _tuples

HORIZONS = (128, 1024, 4096)
EPSILON = .01
ALPHA = .05
PENALTY = .005
RETENTION_TOLERANCE = .1
LOSS_WINDOW = 64


class SharedSpherePredictor(SpherePredictor):
    def __init__(self, rate=.03, *, n_actions=4, n_routes=8):
        super().__init__(rate)
        _integer(n_actions, "action capacity", low=2, high=16)
        _integer(n_routes, "route capacity", low=2, high=8)
        self.n_actions, self.n_routes = n_actions, n_routes
        initial = unit([1.0, 1.0, .15])
        self.points = [[list(initial) for _ in range(n_actions)] for _ in range(n_routes)]
        self.counts = [[0 for _ in range(n_actions)] for _ in range(n_routes)]
        self._probability_cache = [[None for _ in range(n_actions)] for _ in range(n_routes)]

    def _transaction_copy(self):
        child = copy.copy(self)
        child.anchors = [list(p) for p in self.anchors]
        child.points = [[list(p) for p in row] for row in self.points]
        child.counts = [list(row) for row in self.counts]
        child._probability_cache = [list(row) for row in self._probability_cache]
        return child

    def probability(self, action, route):
        self._indices(action, route)
        key = (tuple(self.points[route][action]), tuple(self.anchors[0]),
               tuple(self.anchors[1]), self.temperature)
        cached = self._probability_cache[route][action]
        if cached is None or cached[0] != key:
            cached = (key, super().probability(action, route))
            self._probability_cache[route][action] = cached
        return cached[1]

    def _indices(self, action, route):
        _integer(action, "action", high=self.n_actions - 1)
        _integer(route, "route", high=self.n_routes - 1)

    def checkpoint(self):
        return {**super().checkpoint(), "n_actions": self.n_actions, "n_routes": self.n_routes}

    @classmethod
    def restore(cls, data):
        if type(data) is not dict or set(data) != {"format", "rate", "temperature", "anchors", "points", "counts", "n_actions", "n_routes"}:
            raise ValueError("Invalid shared predictor")
        model = cls(data["rate"], n_actions=data["n_actions"], n_routes=data["n_routes"])
        if type(data["format"]) is not int or data["format"] != 1 or data["temperature"] != .5 or data["anchors"] != model.anchors:
            raise ValueError("Unsupported spherical readout")
        for name in ("points", "counts"):
            rows = data[name]
            if type(rows) is not list or len(rows) != model.n_routes or any(type(r) is not list or len(r) != model.n_actions for r in rows):
                raise ValueError("Invalid shared bank shape")
        model.points = [[learnable_point(p, model.anchors) for p in r] for r in data["points"]]
        model.counts = [[counter(n, "neural update count") for n in r] for r in data["counts"]]
        return model


def idle_episode():
    return {"phase": "idle", "task": None, "mask": 0, "before": 0, "coin": None, "events": 0}


def pair_index(a, b, capacity):
    return a * (2 * capacity - a - 1) // 2 + b - a - 1


def set_bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit



def _feature_masks(rows, symbols, context_offset, context_capacity):
    """Exact sparse assembly or eight-row bit transpose for dense episodes."""
    width = context_offset + context_capacity
    density = sum(mask.bit_count() + before.bit_count() + 1
                  for _, mask, before, _, _, _ in rows)
    if len(rows) < 8 or density <= len(rows) * width // 8:
        masks = {}
        for index, (slot, mask, before, _, _, _) in enumerate(rows):
            bit = 1 << index
            for feature in itertools.chain(set_bits(mask),
                    (symbols + b for b in set_bits(before)), (context_offset + slot,)):
                masks[feature] = masks.get(feature, 0) | bit
        return masks
    byte_width = (width + 7) // 8
    columns = [0] * width
    for start in range(0, len(rows), 8):
        block = rows[start:start + 8]
        packed = b"".join((mask | (before << symbols) | (1 << (context_offset + slot))).to_bytes(
            byte_width, "little") for slot, mask, before, _, _, _ in block)
        for offset in range(byte_width):
            value = int.from_bytes(packed[offset::byte_width], "little")
            swap = (value ^ (value >> 7)) & 0x00AA00AA00AA00AA
            value ^= swap ^ (swap << 7)
            swap = (value ^ (value >> 14)) & 0x0000CCCC0000CCCC
            value ^= swap ^ (swap << 14)
            swap = (value ^ (value >> 28)) & 0x00000000F0F0F0F0
            value ^= swap ^ (swap << 28)
            for bit, bits in enumerate(value.to_bytes(8, "little")):
                feature = 8 * offset + bit
                if bits and feature < width:
                    columns[feature] |= bits << start
    return {feature: bits for feature, bits in enumerate(columns) if bits}


def pair_coordinates(index, capacity):
    """Inverse of pair_index without constructing the full pair set."""
    _integer(capacity, "pair capacity", low=2)
    _integer(index, "pair index", high=capacity * (capacity - 1) // 2 - 1)
    low, high = 0, capacity - 2
    while low < high:
        middle = (low + high + 1) // 2
        if middle * (2 * capacity - middle - 1) // 2 <= index:
            low = middle
        else:
            high = middle - 1
    second = low + 1 + index - low * (2 * capacity - low - 1) // 2
    return low, second

def hex_mask(value):
    return format(value, "x")


def parse_hex(value, bits):
    if type(value) is not str or not re.fullmatch(r"0|[1-9a-f][0-9a-f]*", value) or len(value) > (bits + 3) // 4:
        raise ValueError("Noncanonical bit mask")
    result = int(value, 16)
    if result.bit_length() > bits:
        raise ValueError("Bit mask outside capacity")
    return result


def log_probability(p, y):
    return math.log(max(EPSILON, min(1 - EPSILON, p if y else 1 - p)))


class SharedLearner:
    CHECKPOINT_FORMAT = 2
    IMPLEMENTATION = "first_piece.shared-compositions-s2.v1"

    def _history_origin(self):
        return {"archived_attempts": 0, "archived_fit_records": 0,
                "archived_admissions": 0, "archived_at": -1, "last_admission": None}

    def _restore_history_origin(self, snapshot):
        pass

    def _attempt_limit(self):
        return self.config["max_attempts"]

    def _search_available(self):
        return self.attempts < self._attempt_limit()

    def _interval_alpha(self, attempt=None):
        return ALPHA

    def _horizons(self, attempt=None):
        return HORIZONS

    def _max_looks(self):
        return len(HORIZONS)

    def _search_keys(self, attempt):
        from .shared_state import SEARCH_KEYS
        return SEARCH_KEYS

    def _validate_search(self, search):
        pass

    def _after_restore(self):
        pass

    def _on_accept(self):
        pass

    def _served_readout(self, episode, route):
        return (self.active, route) if self.config["use_structure"] else (self.baseline, episode["coin"])

    def _control_probability(self, episode, action):
        return self.control.probability(action, episode["coin"])

    def __init__(self, seed=0, *, max_tasks=32, max_symbols=64, n_actions=4,
                 max_features=3, fit_per_context=256, min_records=512,
                 replay_passes=4, max_attempts=16, cooldown=256,
                 pool_size=96, pair_beam=12, rate=.03, use_structure=True,
                 trial_stall_limit=4096):
        counter(seed, "seed")
        limits = {"max_tasks": (max_tasks, 1, 32), "max_symbols": (max_symbols, 4, 128),
                  "n_actions": (n_actions, 2, 16), "max_features": (max_features, 1, 3),
                  "fit_per_context": (fit_per_context, 64, 1024), "min_records": (min_records, 64, 32768),
                  "replay_passes": (replay_passes, 1, 8), "max_attempts": (max_attempts, 1, 32),
                  "cooldown": (cooldown, 128, 4096), "pool_size": (pool_size, 16, 128),
                  "pair_beam": (pair_beam, 1, 32),
                  "trial_stall_limit": (trial_stall_limit, 128, 32768)}
        for name, (value, low, high) in limits.items():
            _integer(value, name, low=low, high=high)
        if type(use_structure) is not bool:
            raise ValueError("Invalid readout setting")
        self.config = {"seed": seed, **{k: v[0] for k, v in limits.items()},
                       "rate": rate, "use_structure": use_structure}
        self.rng = random.Random(seed)
        self.symbols = []
        self._symbol_ids = {}
        self.tasks = {}
        self.episode = idle_episode()
        self.program = []
        self.active = self._new_model()
        self.baseline = self._new_model()
        self.candidate = self.control = None
        self.trial = None
        self.steps = self.attempts = self.admissions = self.neural_updates = 0
        self.next_trial = min(min_records, fit_per_context)
        self.decisions = []
        self.searches = []
        self.max_sphere_residual = 0.0

    def _observation_copy(self):
        """Own exactly the state receive() can change; banks remain read-only."""
        child = copy.copy(self)
        child.config = dict(self.config)
        child.rng = random.Random(0)
        child.rng.setstate(self.rng.getstate())
        child.symbols = list(self.symbols)
        child._symbol_ids = dict(self._symbol_ids)
        child.tasks = dict(self.tasks)
        child.episode = dict(self.episode)
        return child

    def _transaction_copy(self, *, context=None):
        """Own mutable feedback state and the live validation journal.

        context=None keeps an unrestricted private fork isolated. The adapter
        supplies its pending context: only that context's rows change. Other
        task headers are still owned because admission resets all losses.
        """
        child = self._observation_copy()
        child.program = list(self.program)
        child.tasks = {
            slot: {**task,
                   "records": list(task["records"]) if context is None or slot == context else task["records"],
                   "losses": list(task["losses"]) if context is None or slot == context else task["losses"]}
            for slot, task in self.tasks.items()}
        for name in ("active", "baseline", "candidate", "control"):
            bank = getattr(self, name)
            setattr(child, name, None if bank is None else bank._transaction_copy())
        child.trial = copy.deepcopy(self.trial)
        child.decisions = list(self.decisions)
        child.searches = list(self.searches)
        if self.trial is not None:
            child.searches[-1] = copy.deepcopy(self.searches[-1])
        return child

    @property
    def pair_count(self):
        return self.config["max_symbols"] * (self.config["max_symbols"] - 1) // 2

    @property
    def context_offset(self):
        return self.config["max_symbols"] + self.pair_count

    def _new_model(self):
        return SharedSpherePredictor(self.config["rate"], n_actions=self.config["n_actions"],
                                     n_routes=2 ** self.config["max_features"])

    def _route(self, program, slot, mask, before):
        symbols = self.config["max_symbols"]
        route = 0
        for i, feature in enumerate(program):
            if feature < symbols:
                value = bool(mask & (1 << feature))
            elif feature < self.context_offset:
                value = bool(before & (1 << (feature - symbols)))
            else:
                value = slot == feature - self.context_offset
            route |= int(value) << i
        return route

    def receive(self, event):
        if type(event) is not dict or event.get("kind") not in ("token", "surface"):
            raise ValueError("Invalid event")
        token_event = event["kind"] == "token"
        if set(event) != ({"kind", "token", "task"} if token_event else {"kind", "surface", "task"}):
            raise ValueError("Unexpected event fields")
        slot = _integer(event["task"], "context slot", high=self.config["max_tasks"] - 1)
        if token_event:
            token = identifier(event["token"], "symbol")
            if token not in self._symbol_ids and len(self.symbols) == self.config["max_symbols"]:
                raise ValueError("Vocabulary budget exhausted")
        elif event["surface"] != "sealed":
            raise ValueError("Unsupported surface")
        e = self.episode
        if e["phase"] == "feedback":
            raise RuntimeError("Resolve feedback before another observation")
        if e["phase"] == "idle" and not token_event:
            raise RuntimeError("Observe symbols before an end event")
        if e["phase"] != "idle" and e["task"] != slot:
            raise RuntimeError("Context cannot change within an episode")
        # Check every failure condition before vocabulary/RNG/episode changes.
        events = counter(e["events"] + int(token_event), "event count")
        if e["phase"] == "idle":
            self.tasks.setdefault(slot, {"steps": 0, "records": [], "losses": []})
            self.episode = {"phase": "tokens", "task": slot, "mask": 0, "before": 0,
                            "coin": self.rng.randrange(self.active.n_routes), "events": 0}
            e = self.episode
        if token_event:
            if token not in self._symbol_ids:
                self._symbol_ids[token] = len(self.symbols)
                self.symbols.append(token)
            token_id = self._symbol_ids[token]
            if not e["mask"] & (1 << token_id):
                for previous in set_bits(e["mask"] & ((1 << token_id) - 1)):
                    e["before"] |= 1 << pair_index(previous, token_id, self.config["max_symbols"])
            e["mask"] |= 1 << token_id
            e["events"] = events
            return None
        e["phase"] = "feedback"
        return self.pending_probabilities()

    def required_fit_records(self):
        """Fit target limited by the buffers of contexts with actual labels."""
        labelled = sum(task["steps"] > 0 for task in self.tasks.values())
        target = min(self.config["min_records"], max(1, labelled) * self.config["fit_per_context"])
        # An abandoned, thin context must not create an unreachable target.
        # First allow the declared global warmup; then fit from a full buffer
        # plus whatever other labelled data remain, without lowering support gates.
        available = sum(len(task["records"]) for task in self.tasks.values())
        full = any(len(task["records"]) == self.config["fit_per_context"] for task in self.tasks.values())
        return min(target, available) if self.steps >= target and full else target

    def pending_probabilities(self):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No pending forecast")
        e = self.episode
        route = self._route(self.program, e["task"], e["mask"], e["before"]) if self.program else e["coin"]
        model, route = self._served_readout(e, route)
        return [model.probability(a, route) for a in range(self.config["n_actions"])]

    def finish_evaluation(self):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No pending outcome")
        self.episode = idle_episode()

    def _search(self, rows, *, scope=None):
        start = time.perf_counter()
        masks = _feature_masks(rows, self.config["max_symbols"],
                               self.context_offset, self.config["max_tasks"])
        classes = [[0, 0] for _ in range(self.config["n_actions"])]
        for index, (_, _, _, _, action, y) in enumerate(rows):
            classes[action][y] |= 1 << index
        total = len(rows)
        all_rows = (1 << total) - 1
        eligible = [f for f, m in masks.items() if min(m.bit_count(), total - m.bit_count()) >= 16]
        # Balance ranking retains XOR operands with zero marginal label gain.
        rank = lambda f: (-min(masks[f].bit_count(), total - masks[f].bit_count()), f)
        contexts = sorted((f for f in eligible if f >= self.context_offset), key=rank)
        relations = sorted((f for f in eligible if self.config["max_symbols"] <= f < self.context_offset), key=rank)
        presences = sorted((f for f in eligible if f < self.config["max_symbols"]), key=rank)
        pool = contexts[:32] + relations[:max(0, self.config["pool_size"] - len(contexts[:32]) - 16)] + presences[:16]
        chosen = set(pool)
        pool += sorted((f for f in eligible if f not in chosen), key=rank)[:self.config["pool_size"] - len(pool)]
        retained = [feature for feature in self.program if feature in eligible]
        pool = sorted((retained + [feature for feature in pool if feature not in retained])[:self.config["pool_size"]])
        examined = 0

        def score(program):
            nonlocal examined
            examined += 1
            groups = [all_rows]
            for feature in program:
                m = masks[feature]
                groups = [g & (~m & all_rows) for g in groups] + [g & m for g in groups]
            result = 0.0
            for group in groups:
                count = group.bit_count()
                if not count:
                    continue
                if count < 16:
                    return -math.inf
                for pair in classes:
                    zero, one = ((group & m).bit_count() for m in pair)
                    denom = zero + one + 2
                    if zero:
                        result += zero * math.log((zero + 1) / denom)
                    if one:
                        result += one * math.log((one + 1) / denom)
            return result / total - PENALTY * len(program)

        best = None
        pairs = []
        def consider(program):
            nonlocal best
            # Mathematically equal partitions can differ by summation roundoff.
            # Prefer a localized exception in the already declared error scope,
            # preserving the common rule's default for an unobserved context.
            local = scope is not None and self.context_offset + scope in program
            candidate = (score(program), (int(local), tuple(-f for f in program)), tuple(program))
            if math.isfinite(candidate[0]) and (best is None or
                    candidate[0] > best[0] + 1e-12 or
                    (abs(candidate[0] - best[0]) <= 1e-12 and candidate[1] > best[1])):
                best = candidate
            return candidate

        for feature in pool:
            consider((feature,))
        if self.config["max_features"] >= 2:
            for pair in itertools.combinations(pool, 2):
                pairs.append(consider(pair))
        if self.config["max_features"] >= 3:
            top_pairs = sorted(pairs, reverse=True)[:self.config["pair_beam"]]
            # Extend admitted structure even when a new XOR removes its
            # marginal gain. This is generic continuity, not a hidden rule.
            retained_pairs = list(itertools.combinations([f for f in self.program if f in pool], 2))
            pairs_to_extend = list(dict.fromkeys([pair for _, _, pair in top_pairs] + retained_pairs))
            seen = set()
            for pair in pairs_to_extend:
                for feature in pool:
                    triple = tuple(sorted((*pair, feature)))
                    if feature in pair or triple in seen:
                        continue
                    seen.add(triple)
                    consider(triple)
        report = {"attempt": self.attempts, "scope": scope, "score_source": "served",
                  "at": self.steps, "fit_records": total, "eligible_features": len(eligible),
                  "pooled_features": len(pool), "hypotheses_examined": examined,
                  "elapsed_seconds": time.perf_counter() - start,
                  "program": None if best is None else list(best[2])}
        self.searches.append(report)
        return report["program"]

    def _start_trial(self, scope):
        # A sole observed context has no complement to preserve. Use a global
        # trial rather than waiting for observations that cannot exist.
        if sum(task["steps"] > 0 for task in self.tasks.values()) == 1:
            scope = None
        self.attempts += 1
        rows = [(slot, *r) for slot in sorted(self.tasks) for r in self.tasks[slot]["records"]]
        program = self._search(rows, scope=scope)
        if program is None:
            self.decisions.append({"attempt": self.attempts, "at": self.steps, "scope": scope,
                                   "program": None, "decision": "unsupported"})
            self.next_trial = self.steps + self.config["cooldown"]
            return
        candidate, control = self._new_model(), self._new_model()
        for _ in range(self.config["replay_passes"]):
            self.rng.shuffle(rows)
            for slot, mask, before, coin, action, y in rows:
                candidate.update(action, y, self._route(program, slot, mask, before))
                control.update(action, y, coin)
        self.neural_updates = counter(self.neural_updates + 2 * len(rows) * self.config["replay_passes"], "neural updates")
        self.candidate, self.control = candidate, control
        self.trial = {"program": program, "scope": scope, "fit_records": len(rows),
                      "started_at": self.steps, "last_progress_at": self.steps,
                      "fit_required_records": self.required_fit_records(),
                      "fit_updates_per_bank": len(rows) * self.config["replay_passes"],
                      "n": 0, "relevance": 0.0, "improvement": 0.0,
                      "other_n": 0, "preservation": 0.0,
                      "support": [0] * self.active.n_routes}

    def _interval(self, gain, n, *, anytime=False, attempt=None, comparison=None):
        if not n:
            return {"n": 0, "mean": 0.0, "bound": None, "lower": None}
        mean = gain / n
        # Bounded predictable log gains; conditional Hoeffding-Azuma.
        family = 3 * len(self._horizons(attempt)) * self.config["max_attempts"]
        log_family = math.log(2 * family / self._interval_alpha(attempt))
        if anytime:
            # Stitch maximal Hoeffding bounds over [2^k, 2^(k+1)).
            # Weight epoch k by 6/(pi^2*(k+1)^2). Thus the complement may
            # arrive on an adaptive schedule without an optional-time leak.
            epoch = n.bit_length() - 1
            upper_time = 1 << (epoch + 1)
            log_family += math.log(math.pi ** 2 / 6) + 2 * math.log(epoch + 1)
            bound = -math.log(EPSILON) * math.sqrt(2 * upper_time * log_family) / n
        else:
            bound = -math.log(EPSILON) * math.sqrt(2 * log_family / n)
        return {"n": n, "mean": mean, "bound": bound, "lower": mean - bound,
                "uniform_over_time": anytime}

    def _judge(self):
        t = self.trial
        horizons = self._horizons()
        if t["n"] not in horizons:
            return
        relevance = self._interval(t["relevance"], t["n"], comparison="relevance")
        improvement = self._interval(t["improvement"], t["n"], comparison="improvement")
        preservation = self._interval(t["preservation"], t["other_n"], anytime=True, comparison="preservation")
        support = [n for n in t["support"] if n]
        # All reachable scope routes need support, not unused allocated routes.
        supported = bool(support) and min(support) >= 16
        retained = t["scope"] is None or (preservation["lower"] is not None and preservation["lower"] > -RETENTION_TOLERANCE)
        cost = PENALTY * len(t["program"])
        if supported and retained and relevance["lower"] > cost and improvement["lower"] > cost:
            decision = "accept"
        elif relevance["mean"] <= cost or improvement["mean"] <= cost:
            decision = "futile"
        elif t["n"] == horizons[-1]:
            decision = "inconclusive"
        else:
            decision = "pending"
        self.decisions.append({"attempt": self.attempts, "at": self.steps, "scope": t["scope"],
                               "program": list(t["program"]), "decision": decision,
                               "relevance": relevance, "improvement": improvement,
                               "preservation": preservation, "route_support": list(t["support"])})
        if decision == "pending":
            return
        if decision == "accept":
            self.active, self.baseline = self.candidate, self.control
            self.program = list(t["program"])
            self.admissions += 1
            self._on_accept()
            for task in self.tasks.values():
                task["losses"] = []
        self.trial = self.candidate = self.control = None
        self.next_trial = self.steps + self.config["cooldown"]

    def _close_unfinished_trial(self, reason):
        """Discard a candidate without a new statistical look or budget refund."""
        t = self.trial
        self.decisions.append({"attempt": self.attempts, "at": self.steps,
                               "scope": t["scope"], "program": list(t["program"]),
                               "decision": reason, "validation_interactions": t["n"],
                               "preservation_interactions": t["other_n"]})
        self.trial = self.candidate = self.control = None
        self.next_trial = counter(self.steps + self.config["cooldown"], "next trial")

    def learn(self, action, outcome):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No pending feedback")
        _integer(action, "action", high=self.config["n_actions"] - 1)
        _integer(outcome, "outcome", high=1)
        next_step = counter(self.steps + 1, "steps")
        counter(self.neural_updates + 2, "neural updates")
        e = self.episode
        task = self.tasks[e["task"]]
        route = self._route(self.program, e["task"], e["mask"], e["before"]) if self.program else e["coin"]
        served_model, served_route = self._served_readout(e, route)
        p = served_model.probability(action, served_route)
        if self.trial is not None:
            t = self.trial
            tr = self._route(t["program"], e["task"], e["mask"], e["before"])
            proposed = self.candidate.probability(action, tr)
            gain = log_probability(proposed, outcome) - log_probability(p, outcome)
            if t["scope"] is None or e["task"] == t["scope"]:
                t["n"] = counter(t["n"] + 1, "validation interactions")
                t["last_progress_at"] = next_step
                t["support"][tr] += 1
                t["improvement"] += gain
                t["relevance"] += log_probability(proposed, outcome) - log_probability(self._control_probability(e, action), outcome)
            else:
                t["other_n"] = counter(t["other_n"] + 1, "preservation interactions")
                t["preservation"] += gain
        for model, r in ((self.active, route), (self.baseline, e["coin"])):
            report = model.update(action, outcome, r)
            self.max_sphere_residual = max(self.max_sphere_residual, report["sphere_residual"])
        self.neural_updates += 2
        self.steps = next_step
        task["steps"] = counter(task["steps"] + 1, "context steps")
        task["losses"].append((p - outcome) ** 2)
        if len(task["losses"]) > LOSS_WINDOW:
            del task["losses"][0]
        task["records"].append([e["mask"], e["before"], e["coin"], action, outcome])
        if len(task["records"]) > self.config["fit_per_context"]:
            del task["records"][0]
        self.episode = idle_episode()
        if self.trial is not None:
            # A complement event must not repeat a predeclared scoped look.
            if self.trial["scope"] is None or e["task"] == self.trial["scope"]:
                self._judge()
            elif self.steps - self.trial["last_progress_at"] >= self.config["trial_stall_limit"]:
                self._close_unfinished_trial("expired")
        elif self.steps >= self.next_trial and self._search_available():
            enough = sum(len(t["records"]) for t in self.tasks.values()) >= self.required_fit_records()
            if enough and len(task["losses"]) == LOSS_WINDOW and math.fsum(task["losses"]) / LOSS_WINDOW > .4 * (1 / self.config["n_actions"]) * (1 - 1 / self.config["n_actions"]):
                self._start_trial(e["task"] if self.program else None)
        return p

    def metrics(self, *, detailed=True):
        points = 2 * self.active.n_routes * self.config["n_actions"]
        return {"steps": self.steps, "contexts": len(self.tasks), "symbols": len(self.symbols),
                "program": list(self.program), "attempts": self.attempts, "admissions": self.admissions,
                "trial_scope": None if self.trial is None else self.trial["scope"],
                "trial_interactions": 0 if self.trial is None else self.trial["n"],
                "trial_idle_interactions": 0 if self.trial is None else self.steps - self.trial["last_progress_at"],
                "required_fit_records": self.required_fit_records(),
                "fit_wait_reason": None if sum(len(t["records"]) for t in self.tasks.values()) >= self.required_fit_records() else "collecting_labels",
                "status": "validating" if self.trial else ("exhausted" if self.attempts == self.config["max_attempts"] else "tracking"),
                "live_points_including_control": points,
                "allocated_points_including_trial": points * (2 if self.trial else 1),
                "intrinsic_live_dof": points * 2, "intrinsic_peak_dof": points * 4,
                "fit_records": sum(len(t["records"]) for t in self.tasks.values()),
                "neural_updates": self.neural_updates, "max_sphere_residual": self.max_sphere_residual,
                **({"decisions": copy.deepcopy(self.decisions), "searches": copy.deepcopy(self.searches)}
                   if detailed else {})}

    def checkpoint(self):
        tasks = {}
        for slot, task in self.tasks.items():
            tasks[str(slot)] = {**task, "records": [[hex_mask(m), hex_mask(b), c, a, y]
                                                   for m, b, c, a, y in task["records"]]}
        episode = {**self.episode, "mask": hex_mask(self.episode["mask"]), "before": hex_mask(self.episode["before"])}
        result = {"format": self.CHECKPOINT_FORMAT, "implementation": self.IMPLEMENTATION,
                  "config": self.config, "rng": listify(self.rng.getstate()), "symbols": self.symbols,
                  "tasks": tasks, "episode": episode, "program": self.program,
                  "active": self.active.checkpoint(), "baseline": self.baseline.checkpoint(),
                  "candidate": None if self.candidate is None else self.candidate.checkpoint(),
                  "control": None if self.control is None else self.control.checkpoint(),
                  "trial": self.trial, "steps": self.steps, "attempts": self.attempts,
                  "admissions": self.admissions, "neural_updates": self.neural_updates,
                  "next_trial": self.next_trial, "decisions": self.decisions, "searches": self.searches,
                  "max_sphere_residual": self.max_sphere_residual}
        return copy.deepcopy(result)

    @classmethod
    def migrate_checkpoint_v1(cls, snapshot):
        """Explicit conversion; unfinished old trials close without admission."""
        from .shared_state import migrate_v1
        return migrate_v1(cls, snapshot)

    @classmethod
    def restore(cls, snapshot):
        if type(snapshot) is dict and snapshot.get("format") == 1:
            raise ValueError("Use migrate_checkpoint_v1 explicitly before restoring a shared format-1 checkpoint")
        if type(snapshot) is not dict or set(snapshot) != set(cls().checkpoint()):
            raise ValueError("Invalid shared checkpoint fields")
        d = copy.deepcopy(snapshot)
        # RNG tuple is Python-native; all published JSON is canonical.
        d["rng"] = _tuples(d["rng"])
        json_data = copy.deepcopy(d)
        json_data["rng"] = listify(json_data["rng"])
        json_value(json_data)
        if type(d["format"]) is not int or d["format"] != cls.CHECKPOINT_FORMAT or d["implementation"] != cls.IMPLEMENTATION:
            raise ValueError("Unsupported shared checkpoint")
        if type(d["config"]) is not dict or set(d["config"]) != set(cls().config):
            raise ValueError("Invalid shared configuration")
        model = cls(**d["config"])
        model._restore_history_origin(d)
        symbols = d["symbols"]
        if type(symbols) is not list or len(symbols) > model.config["max_symbols"] or any(type(s) is not str for s in symbols) or len(set(symbols)) != len(symbols):
            raise ValueError("Invalid vocabulary")
        for symbol in symbols:
            identifier(symbol, "symbol")
        model.symbols = symbols
        model._symbol_ids = {s: i for i, s in enumerate(symbols)}
        model.rng.setstate(d["rng"])

        def memory(mask, before):
            m = parse_hex(mask, model.config["max_symbols"])
            b = parse_hex(before, model.pair_count)
            if m.bit_length() > len(symbols):
                raise ValueError("Unbound symbol in memory")
            present = list(set_bits(m))
            allowed = 0
            ranks = {a: 0 for a in present}
            for a, second in itertools.combinations(present, 2):
                bit = 1 << pair_index(a, second, model.config["max_symbols"])
                allowed |= bit
                ranks[second if b & bit else a] += 1
            if b & ~allowed or sorted(ranks.values()) != list(range(len(present))):
                raise ValueError("Impossible first-occurrence order")
            return m, b

        tasks = d["tasks"]
        if type(tasks) is not dict or len(tasks) > model.config["max_tasks"]:
            raise ValueError("Context budget exceeded")
        for key, task in tasks.items():
            if type(key) is not str or not key.isdecimal() or str(int(key)) != key:
                raise ValueError("Invalid context slot encoding")
            slot = _integer(int(key), "context slot", high=model.config["max_tasks"] - 1)
            if type(task) is not dict or set(task) != {"steps", "records", "losses"}:
                raise ValueError("Invalid context state")
            counter(task["steps"], "context steps")
            if type(task["records"]) is not list or len(task["records"]) != min(task["steps"], model.config["fit_per_context"]):
                raise ValueError("Invalid fit buffer length")
            records = []
            for row in task["records"]:
                if type(row) is not list or len(row) != 5:
                    raise ValueError("Invalid fit record")
                m, b = memory(row[0], row[1])
                if not m:
                    raise ValueError("Empty labelled episode")
                coin = _integer(row[2], "random route", high=model.active.n_routes - 1)
                action = _integer(row[3], "action", high=model.config["n_actions"] - 1)
                y = _integer(row[4], "outcome", high=1)
                records.append([m, b, coin, action, y])
            losses = task["losses"]
            if type(losses) is not list or len(losses) > min(task["steps"], LOSS_WINDOW) or any(not 0 <= _finite_number(x, "loss") <= 1 for x in losses):
                raise ValueError("Invalid loss window")
            model.tasks[slot] = {**task, "records": records}
        for name in ("steps", "attempts", "admissions", "neural_updates", "next_trial"):
            setattr(model, name, counter(d[name], name))
        if model.steps != sum(t["steps"] for t in model.tasks.values()) or not model.admissions <= model.attempts <= model._attempt_limit():
            raise ValueError("Inconsistent exposure or search budgets")
        e = d["episode"]
        if type(e) is not dict or set(e) != set(idle_episode()) or e["phase"] not in ("idle", "tokens", "feedback"):
            raise ValueError("Invalid episode")
        m, b = memory(e["mask"], e["before"])
        counter(e["events"], "episode events")
        if e["phase"] == "idle":
            if {**e, "mask": m, "before": b} != idle_episode():
                raise ValueError("Dirty idle episode")
        elif type(e["task"]) is not int or e["task"] not in model.tasks or not m or e["events"] < m.bit_count():
            raise ValueError("Invalid active episode")
        if e["phase"] != "idle":
            _integer(e["coin"], "random route", high=model.active.n_routes - 1)
        model.episode = {**e, "mask": m, "before": b}

        def program(value):
            if type(value) is not list or len(value) > model.config["max_features"] or any(type(f) is not int for f in value) or value != sorted(set(value)):
                raise ValueError("Invalid composition")
            for f in value:
                _integer(f, "predicate", high=model.context_offset + model.config["max_tasks"] - 1)
                if f < model.config["max_symbols"] and f >= len(symbols):
                    raise ValueError("Unbound presence predicate")
                if model.config["max_symbols"] <= f < model.context_offset:
                    _, second = pair_coordinates(f - model.config["max_symbols"], model.config["max_symbols"])
                    if second >= len(symbols):
                        raise ValueError("Unbound order predicate")
                if f >= model.context_offset and f - model.context_offset not in model.tasks:
                    raise ValueError("Unbound context predicate")
            return value
        model.program = program(d["program"])
        for name in ("active", "baseline", "candidate", "control"):
            data = d[name]
            value = None if data is None else SharedSpherePredictor.restore(data)
            if value is not None and (value.n_actions != model.config["n_actions"] or value.n_routes != 2 ** model.config["max_features"] or value.rate != model.config["rate"]):
                raise ValueError("Spherical bank and configuration differ")
            setattr(model, name, value)
        if model.active is None or model.baseline is None:
            raise ValueError("Missing live bank")
        t = d["trial"]
        if (t is not None) != (model.candidate is not None) or (t is not None) != (model.control is not None):
            raise ValueError("Incomplete trial")
        if t is not None:
            if type(t) is not dict or set(t) != {"program", "scope", "fit_records", "fit_updates_per_bank", "n", "relevance", "improvement", "other_n", "preservation", "support", "started_at", "last_progress_at", "fit_required_records"}:
                raise ValueError("Invalid trial summary")
            program(t["program"])
            if not t["program"] or (t["scope"] is not None and (type(t["scope"]) is not int or t["scope"] not in model.tasks)):
                raise ValueError("Invalid trial scope")
            for name in ("fit_records", "fit_updates_per_bank", "n", "other_n"):
                counter(t[name], name)
            if not counter(t["fit_required_records"], "required fit records", minimum=64) <= t["fit_records"] <= model.config["fit_per_context"] * model.config["max_tasks"] or t["fit_updates_per_bank"] != t["fit_records"] * model.config["replay_passes"] or t["n"] >= model._horizons()[-1] or t["n"] + t["other_n"] > model.steps:
                raise ValueError("Invalid trial budget")
            if type(t["support"]) is not list or len(t["support"]) != model.active.n_routes or any(type(n) is not int or n < 0 for n in t["support"]) or sum(t["support"]) != t["n"]:
                raise ValueError("Invalid trial support")
            for name, n in (("relevance", t["n"]), ("improvement", t["n"]), ("preservation", t["other_n"])):
                if abs(_finite_number(t[name], name)) > -math.log(EPSILON) * n + 1e-8:
                    raise ValueError("Impossible trial log score")
            if t["scope"] is None and t["other_n"]:
                raise ValueError("Global trial has complement observations")
            for bank in (model.candidate, model.control):
                if sum(map(sum, bank.counts)) != t["fit_updates_per_bank"]:
                    raise ValueError("Validation bank was updated on deciding data")
        model.trial = t
        for name in ("decisions", "searches"):
            if type(d[name]) is not list or len(d[name]) > model.config["max_attempts"] * model._max_looks():
                raise ValueError("Unbounded search history")
            setattr(model, name, d[name])
        origin = model._history_origin()
        if len(model.searches) != model.attempts - origin["archived_attempts"]:
            raise ValueError("Search history and budget differ")
        if any(type(x) is not dict for x in model.decisions):
            raise ValueError("Invalid decision entry")
        if len([x for x in model.decisions if x.get("decision") == "accept"]) != model.admissions - origin["archived_admissions"] or bool(model.program) != bool(model.admissions):
            raise ValueError("Admission history differs from live program")
        accepted = [x for x in model.decisions if x.get("decision") == "accept"]
        last = accepted[-1] if accepted else origin["last_admission"]
        if last is not None and last.get("program") != model.program:
            raise ValueError("Program differs from last admission")
        live_updates = sum(sum(map(sum, bank.counts)) for bank in (model.active, model.baseline))
        if model.neural_updates < 2 * model.steps or model.neural_updates < live_updates:
            raise ValueError("Invalid neural update accounting")
        model.max_sphere_residual = _finite_number(d["max_sphere_residual"], "sphere residual")
        if not 0 <= model.max_sphere_residual <= 1e-10:
            raise ValueError("Invalid geometry residual")
        from .shared_state import validate_history
        validate_history(model)
        model._after_restore()
        return model


def listify(value):
    if isinstance(value, tuple):
        return [listify(x) for x in value]
    return value
