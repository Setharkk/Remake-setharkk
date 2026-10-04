"""Bounded first-occurrence relations and revisable spherical predictors.

All trainable real parameters remain S2 points. Discrete relation indices
and finite sufficient statistics are separate from the neural geometry.
"""
import copy
import math
import random

from setharkk.contracts import counter
from .criterion import evaluate_distinction
from .spherical import SpherePredictor
from .world import _integer, _tuples

PAIRS = tuple((a, b) for a in range(10) for b in range(a + 1, 10))
FEATURES = 10 + len(PAIRS)
HORIZONS = (128, 1024, 4096)
STATES = ("tracking", "validating", "exhausted")


def feature_route(mask, before, feature):
    if feature is None:
        raise ValueError("A relation index is required")
    return int(bool((mask if feature < 10 else before) & (1 << (feature if feature < 10 else feature - 10))))


def feature_description(feature):
    if feature is None:
        return None
    if feature < 10:
        return {"kind": "presence", "token": feature}
    a, b = PAIRS[feature - 10]
    return {"kind": "first_before", "first": a, "second": b}


def advance(mask, before, token):
    if not mask & (1 << token):
        for index, (a, b) in enumerate(PAIRS):
            if b == token and mask & (1 << a):
                before |= 1 << index
    return mask | (1 << token), before


def select_feature(records):
    ranked = []
    for feature in range(FEATURES):
        counts = [[[1, 1] for _ in range(2)] for _ in range(2)]
        support = [0, 0]
        for mask, before, coin, action, outcome in records:
            group = feature_route(mask, before, feature)
            support[group] += 1
            counts[group][action][outcome] += 1
        if min(support) < 32:
            continue
        score = math.fsum(math.log(counts[feature_route(mask, before, feature)][action][outcome]
                                   / sum(counts[feature_route(mask, before, feature)][action]))
                          for mask, before, coin, action, outcome in records) / len(records)
        ranked.append((score, -feature, feature))
    return max(ranked)[2] if ranked else None


def new_task(rate):
    return {"active": SpherePredictor(rate), "baseline": SpherePredictor(rate),
            "candidate": None, "control": None, "feature": None,
            "steps": 0, "attempts": 0, "admissions": 0, "replacements": 0,
            "status": "tracking", "next_trial": 256, "records": [], "losses": [],
            "trial": None, "decisions": [], "neural_updates": 0}


def idle_episode():
    return {"phase": "idle", "task": None, "mask": 0, "before": 0,
            "coin": None, "events": 0}


class TemporalLearner:
    def __init__(self, seed=0, *, warmup=256, max_tasks=2, max_units=4,
                 max_attempts=32, cooldown=256, rate=.03, use_structure=True):
        _integer(seed, "seed")
        _integer(warmup, "fit window", low=128, high=1024)
        _integer(max_tasks, "task budget", low=1, high=8)
        _integer(max_units, "unit budget", low=max_tasks, high=2 * max_tasks)
        _integer(max_attempts, "attempt budget", low=1, high=64)
        _integer(cooldown, "cooldown", low=128, high=4096)
        if type(use_structure) is not bool:
            raise ValueError("Boolean readout setting required")
        SpherePredictor(rate)
        self.config = {"seed": seed, "warmup": warmup, "max_tasks": max_tasks,
                       "max_units": max_units, "max_attempts": max_attempts,
                       "cooldown": cooldown, "rate": rate, "use_structure": use_structure}
        self.rng = random.Random(seed)
        self.tasks = {}
        self.episode = idle_episode()

    def receive(self, event):
        if type(event) is not dict or event.get("kind") not in ("token", "surface"):
            raise ValueError("Invalid event")
        token_event = event["kind"] == "token"
        fields = {"kind", "task", "token"} if token_event else {"kind", "task", "surface"}
        if set(event) != fields:
            raise ValueError("Unexpected event fields")
        task = _integer(event["task"], "task", high=self.config["max_tasks"] - 1)
        if token_event:
            _integer(event["token"], "token", high=9)
        elif event["surface"] != "sealed":
            raise ValueError("Unsupported surface")
        episode = self.episode
        if episode["phase"] == "feedback":
            raise RuntimeError("Resolve feedback before another event")
        if episode["phase"] == "idle" and not token_event:
            raise RuntimeError("Receive tokens before a surface")
        if episode["phase"] != "idle" and episode["task"] != task:
            raise RuntimeError("Context cannot change inside an episode")
        if episode["phase"] == "idle":
            if task not in self.tasks:
                self.tasks[task] = new_task(self.config["rate"])
                self.tasks[task]["next_trial"] = self.config["warmup"]
            self.episode = {"phase": "tokens", "task": task, "mask": 0, "before": 0,
                            "coin": self.rng.randrange(2), "events": 0}
            episode = self.episode
        if token_event:
            count = counter(episode["events"] + 1, "event count")
            mask, before = advance(episode["mask"], episode["before"], event["token"])
            episode.update(mask=mask, before=before, events=count)
            return None
        episode["phase"] = "feedback"
        return self.pending_probabilities()

    def pending_probabilities(self):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No pending prediction")
        state = self.tasks[self.episode["task"]]
        if not self.config["use_structure"]:
            model, route = state["baseline"], self.episode["coin"]
        else:
            model = state["active"]
            route = self.episode["coin"] if state["feature"] is None else feature_route(
                self.episode["mask"], self.episode["before"], state["feature"])
        return [model.probability(action, route) for action in (0, 1)]

    def _start_trial(self, state):
        state["attempts"] += 1
        feature = select_feature(state["records"])
        if feature is None:
            state["decisions"].append({"attempt": state["attempts"], "at": state["steps"],
                                       "decision": "unsupported", "feature": None})
            state["next_trial"] = state["steps"] + self.config["cooldown"]
            if state["attempts"] == self.config["max_attempts"]:
                state["status"] = "exhausted"
            return
        candidate = SpherePredictor(self.config["rate"])
        control = SpherePredictor(self.config["rate"])
        for mask, before, coin, action, outcome in state["records"]:
            candidate.update(action, outcome, feature_route(mask, before, feature))
            control.update(action, outcome, coin)
        state["neural_updates"] += 2 * len(state["records"])
        state["candidate"], state["control"] = candidate, control
        state["trial"] = {"feature": feature, "started_at": state["steps"],
                          "candidate": [], "control": [], "incumbent": [], "outcomes": [], "groups": []}
        state["status"] = "validating"

    def _judge(self, state):
        trial = state["trial"]
        n = len(trial["outcomes"])
        units = self.config["max_tasks"] + sum(s["feature"] is not None for s in self.tasks.values())
        # A replacement consumes the slot already occupied by this context.
        current = units - int(state["feature"] is not None)
        family = 2 * self.config["max_tasks"] * self.config["max_attempts"] * len(HORIZONS)
        settings = {"comparison_limit": family, "current_units": current,
                    "extra_units": 1, "max_units": self.config["max_units"]}
        relevance = evaluate_distinction(trial["control"], trial["candidate"],
                                         trial["outcomes"], trial["groups"], **settings)
        improvement = evaluate_distinction(trial["incumbent"], trial["candidate"],
                                           trial["outcomes"], trial["groups"], **settings)
        admitted = relevance["decision"] == improvement["decision"] == "accept"
        decision = "accept" if admitted else "pending"
        if not admitted:
            if relevance["decision"] == "blocked_by_budget" or improvement["decision"] == "blocked_by_budget":
                decision = "blocked_by_budget"
            elif relevance["mean_log_score_gain"] <= .01 or improvement["mean_log_score_gain"] <= .01:
                # Futility stops an unpromising trial. It is NOT a confidence
                # claim that this relation can never help after more exposure.
                decision = "futile"
            elif n == HORIZONS[-1]:
                decision = "inconclusive"
        state["decisions"].append({
            "attempt": state["attempts"], "at": state["steps"], "validation_interactions": n,
            "decision": decision, "feature": trial["feature"],
            "relevance": relevance, "improvement": improvement,
            "bound_scope": "mean conditional gain over this past block",
        })
        if decision == "pending":
            return
        if admitted:
            had_feature = state["feature"] is not None
            state["active"], state["baseline"] = state["candidate"], state["control"]
            state["feature"] = trial["feature"]
            state["admissions"] += 1
            state["replacements"] += int(had_feature)
            state["losses"] = []
        state["candidate"], state["control"], state["trial"] = None, None, None
        state["status"] = "exhausted" if state["attempts"] == self.config["max_attempts"] else "tracking"
        state["next_trial"] = state["steps"] + self.config["cooldown"]

    def learn(self, action, outcome):
        _integer(action, "action", high=1)
        _integer(outcome, "outcome", high=1)
        if self.episode["phase"] != "feedback":
            raise RuntimeError("Reach a surface before learning")
        episode = self.episode
        state = self.tasks[episode["task"]]
        counter(state["steps"] + 1, "learning exposure")
        active_route = episode["coin"] if state["feature"] is None else feature_route(
            episode["mask"], episode["before"], state["feature"])
        probability = state["active"].probability(action, active_route)
        state["steps"] += 1
        state["records"].append([episode["mask"], episode["before"], episode["coin"], action, outcome])
        state["records"] = state["records"][-self.config["warmup"]:]
        state["losses"].append((probability - outcome) ** 2)
        state["losses"] = state["losses"][-self.config["warmup"]:]
        if state["status"] == "validating":
            trial = state["trial"]
            group = feature_route(episode["mask"], episode["before"], trial["feature"])
            trial["candidate"].append(state["candidate"].probability(action, group))
            trial["control"].append(state["control"].probability(action, episode["coin"]))
            trial["incumbent"].append(probability)
            trial["outcomes"].append(outcome)
            trial["groups"].append(group)
            if len(trial["outcomes"]) in HORIZONS:
                self._judge(state)
            # Active and control predictors remain frozen throughout the block.
        else:
            state["active"].update(action, outcome, active_route)
            state["baseline"].update(action, outcome, episode["coin"])
            state["neural_updates"] += 2
            if (state["status"] != "exhausted" and state["steps"] >= state["next_trial"]
                    and len(state["records"]) == self.config["warmup"]
                    and len(state["losses"]) == self.config["warmup"]
                    and math.fsum(state["losses"]) / len(state["losses"]) > .12):
                self._start_trial(state)
        self.finish_evaluation()

    def finish_evaluation(self):
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No completed observation")
        self.episode = idle_episode()

    def checkpoint(self):
        tasks = []
        for task, state in sorted(self.tasks.items()):
            encoded = copy.deepcopy({k: v for k, v in state.items()
                                     if k not in ("active", "baseline", "candidate", "control")})
            encoded["task"] = task
            for name in ("active", "baseline", "candidate", "control"):
                encoded[name] = None if state[name] is None else state[name].checkpoint()
            tasks.append(encoded)
        return {"format": 1, "config": dict(self.config), "rng": self.rng.getstate(),
                "episode": dict(self.episode), "tasks": tasks}

    @classmethod
    def restore(cls, snapshot):
        if type(snapshot) is not dict or set(snapshot) != {"format", "config", "rng", "episode", "tasks"} or type(snapshot["format"]) is not int or snapshot["format"] != 1:
            raise ValueError("Invalid temporal checkpoint")
        expected_config = {"seed", "warmup", "max_tasks", "max_units", "max_attempts",
                           "cooldown", "rate", "use_structure"}
        if type(snapshot["config"]) is not dict or set(snapshot["config"]) != expected_config:
            raise ValueError("Invalid temporal configuration")
        instance = cls(**snapshot["config"])
        try:
            instance.rng.setstate(_tuples(snapshot["rng"]))
        except (ValueError, TypeError, OverflowError, IndexError) as exc:
            raise ValueError("Invalid random state") from exc
        if type(snapshot["tasks"]) is not list or len(snapshot["tasks"]) > instance.config["max_tasks"]:
            raise ValueError("Invalid task list")
        fields = set(new_task(instance.config["rate"])) | {"task"}
        for raw in snapshot["tasks"]:
            if type(raw) is not dict or set(raw) != fields:
                raise ValueError("Invalid temporal task")
            state = copy.deepcopy(raw)
            task = _integer(state.pop("task"), "task", high=instance.config["max_tasks"] - 1)
            if task in instance.tasks or state["status"] not in STATES:
                raise ValueError("Duplicate task or invalid status")
            for key in ("steps", "attempts", "admissions", "replacements", "next_trial", "neural_updates"):
                counter(state[key], key)
            if state["attempts"] > instance.config["max_attempts"] or not state["replacements"] <= state["admissions"] <= state["attempts"]:
                raise ValueError("Invalid attempt counts")
            if state["feature"] is not None:
                _integer(state["feature"], "feature", high=FEATURES - 1)
            if (state["feature"] is None) != (state["admissions"] == 0) or state["replacements"] != max(0, state["admissions"] - 1):
                raise ValueError("Invalid admission counts")
            for name in ("active", "baseline", "candidate", "control"):
                state[name] = None if raw[name] is None else SpherePredictor.restore(raw[name])
                if state[name] is not None and state[name].rate != instance.config["rate"]:
                    raise ValueError("Predictor rate differs from configuration")
            if state["active"] is None or state["baseline"] is None:
                raise ValueError("Missing live predictors")
            if type(state["records"]) is not list or len(state["records"]) > instance.config["warmup"]:
                raise ValueError("Record budget exceeded")
            for record in state["records"]:
                if type(record) is not list or len(record) != 5:
                    raise ValueError("Invalid sufficient statistic")
                _integer(record[0], "presence", high=1023)
                _integer(record[1], "order", high=2**len(PAIRS) - 1)
                _validate_relations(record[0], record[1])
                for value in record[2:]:
                    _integer(value, "binary statistic", high=1)
            if type(state["losses"]) is not list or len(state["losses"]) > instance.config["warmup"] or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in state["losses"]):
                raise ValueError("Invalid loss window")
            if len(state["records"]) != min(state["steps"], instance.config["warmup"]):
                raise ValueError("Record exposure differs")
            if type(state["decisions"]) is not list or len(state["decisions"]) > instance.config["max_attempts"] * len(HORIZONS):
                raise ValueError("Decision budget exceeded")
            for entry in state["decisions"]:
                if type(entry) is not dict or entry.get("decision") not in ("accept", "pending", "futile", "inconclusive", "blocked_by_budget", "unsupported"):
                    raise ValueError("Invalid decision entry")
                counter(entry.get("attempt"), "decision attempt", minimum=1)
                counter(entry.get("at"), "decision exposure")
                if entry["attempt"] > state["attempts"] or entry["at"] > state["steps"]:
                    raise ValueError("Invalid decision lineage")
                if entry["decision"] != "unsupported":
                    if entry.get("validation_interactions") not in HORIZONS:
                        raise ValueError("Invalid validation horizon")
                    for gate in ("relevance", "improvement"):
                        values = entry.get(gate)
                        if type(values) is not dict:
                            raise ValueError("Missing comparison")
                        for key in ("mean_log_score_gain", "uncertainty_bound", "gain_lower", "gain_upper", "complexity_cost"):
                            value = values.get(key)
                            if type(value) not in (int, float) or not math.isfinite(value):
                                raise ValueError("Invalid comparison statistic")
            accepted = [entry for entry in state["decisions"] if entry["decision"] == "accept"]
            if len(accepted) != state["admissions"] or (accepted and accepted[-1]["feature"] != state["feature"]):
                raise ValueError("Accepted relation and decision lineage differ")
            if state["status"] == "tracking" and state["attempts"] == instance.config["max_attempts"]:
                raise ValueError("Attempt budget exhausted without closing search")
            trial = state["trial"]
            validating = state["status"] == "validating"
            if validating != (trial is not None) or validating != (state["candidate"] is not None and state["control"] is not None):
                raise ValueError("Trial and predictors differ")
            if not validating and (state["candidate"] is not None or state["control"] is not None):
                raise ValueError("Unexpected temporary predictor")
            if state["status"] == "exhausted" and state["attempts"] != instance.config["max_attempts"]:
                raise ValueError("Premature attempt exhaustion")
            if trial is not None:
                keys = {"feature", "started_at", "candidate", "control", "incumbent", "outcomes", "groups"}
                if type(trial) is not dict or set(trial) != keys or state["attempts"] < 1:
                    raise ValueError("Invalid trial")
                _integer(trial["feature"], "trial feature", high=FEATURES - 1)
                counter(trial["started_at"], "trial start", minimum=instance.config["warmup"])
                arrays = [trial[k] for k in ("candidate", "control", "incumbent", "outcomes", "groups")]
                if any(type(v) is not list for v in arrays):
                    raise ValueError("Invalid validation arrays")
                n = len(trial["outcomes"])
                if n >= HORIZONS[-1] or any(len(v) != n for v in arrays) or state["steps"] != trial["started_at"] + n:
                    raise ValueError("Validation exposure differs")
                for value in trial["candidate"] + trial["control"] + trial["incumbent"]:
                    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                        raise ValueError("Invalid validation probability")
                for value in trial["outcomes"] + trial["groups"]:
                    _integer(value, "binary validation value", high=1)
                if any(sum(map(sum, state[k].counts)) != instance.config["warmup"] for k in ("candidate", "control")):
                    raise ValueError("Temporary fit budget differs")
            instance.tasks[task] = state
        if instance.config["max_tasks"] + sum(s["feature"] is not None for s in instance.tasks.values()) > instance.config["max_units"]:
            raise ValueError("Structural budget exceeded")
        episode = snapshot["episode"]
        if type(episode) is not dict or set(episode) != set(idle_episode()):
            raise ValueError("Invalid episode")
        if episode["phase"] == "idle":
            if episode != idle_episode():
                raise ValueError("Invalid idle memory")
        elif episode["phase"] in ("tokens", "feedback"):
            _integer(episode["task"], "episode task", high=instance.config["max_tasks"] - 1)
            _integer(episode["mask"], "presence", high=1023)
            _integer(episode["before"], "order", high=2**len(PAIRS) - 1)
            _validate_relations(episode["mask"], episode["before"])
            _integer(episode["coin"], "coin", high=1)
            counter(episode["events"], "events", minimum=1)
            if episode["task"] not in instance.tasks or not episode["mask"] or episode["events"] < episode["mask"].bit_count():
                raise ValueError("Episode and task memory differ")
        else:
            raise ValueError("Unknown episode phase")
        instance.episode = copy.deepcopy(episode)
        return instance

    def metrics(self):
        tasks = len(self.tasks)
        validating = sum(s["status"] == "validating" for s in self.tasks.values())
        return {
            "active_neural_points": 8 * tasks, "active_intrinsic_dof": 16 * tasks,
            "stored_neural_points": 8 * tasks + 8 * validating,
            "memory_presence_bits": 10, "memory_order_bits": len(PAIRS),
            "neural_updates": sum(s["neural_updates"] for s in self.tasks.values()),
            "comparison_family_limit": 2 * self.config["max_tasks"] * self.config["max_attempts"] * len(HORIZONS),
            "record_rows": sum(len(s["records"]) for s in self.tasks.values()),
            "validation_rows": sum(len(s["trial"]["outcomes"]) if s["trial"] else 0 for s in self.tasks.values()),
            "tasks": {str(task): {
                "steps": s["steps"], "status": s["status"], "attempts": s["attempts"],
                "admissions": s["admissions"], "replacements": s["replacements"],
                "feature": feature_description(s["feature"]), "decisions": copy.deepcopy(s["decisions"]),
            } for task, s in sorted(self.tasks.items())},
        }


def _validate_relations(mask, before):
    for index, (a, b) in enumerate(PAIRS):
        if before & (1 << index) and not (mask & (1 << a) and mask & (1 << b)):
            raise ValueError("Relation refers to an absent event")
    # Relative first occurrences must define a transitive total order on
    # the observed alphabet, not an impossible cyclic tournament.
    observed = [i for i in range(10) if mask & (1 << i)]
    ranks = {}
    for a in observed:
        rank = 0
        for b in observed:
            if a == b:
                continue
            low, high = sorted((a, b))
            low_first = bool(before & (1 << PAIRS.index((low, high))))
            rank += int((a == high and low_first) or (a == low and not low_first))
        ranks[a] = rank
    if sorted(ranks.values()) != list(range(len(observed))):
        raise ValueError("Impossible first-occurrence order")
