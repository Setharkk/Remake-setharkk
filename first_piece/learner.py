"""Online, bounded event memory with a learned spherical prototype network.

One token-presence distinction per task is proposed from past feedback.
A matched random-route control is fitted on exactly the same records.
Both remain frozen during the fresh, predeclared validation horizons.
"""
import copy
import math
import random

from .criterion import evaluate_distinction
from .spherical import SpherePredictor
from .world import _integer, _tuples


STATUSES = {"collecting", "validating", "accepted", "ablated", "inconclusive",
            "rejected", "unsupported", "blocked_by_budget"}
HORIZONS = (128, 1024, 4096)


def _new_task(rate):
    return {
        "active": SpherePredictor(rate), "candidate": None, "control": None,
        "steps": 0, "status": "collecting", "token": None, "proposed_token": None,
        "records": [], "validation": {"parent": [], "proposal": [], "outcomes": [], "groups": []},
        "decisions": [], "neural_updates": 0,
    }


def _route(mask, token):
    return int(bool(mask & (1 << token)))


def _select_token(records):
    def score(token):
        counts = [[[1, 1] for _ in range(2)] for _ in range(2)]
        support = [0, 0]
        for mask, coin, action, outcome in records:
            group = _route(mask, token)
            counts[group][action][outcome] += 1
            support[group] += 1
        if min(support) < 32:
            return None
        return math.fsum(
            math.log(counts[_route(mask, token)][action][outcome]
                     / sum(counts[_route(mask, token)][action]))
            for mask, coin, action, outcome in records
        ) / len(records)

    ranked = [(value, -token, token) for token in range(10)
              if (value := score(token)) is not None]
    return max(ranked)[2] if ranked else None


class DistinctionLearner:
    def __init__(self, seed=0, *, warmup=256, max_tasks=2, max_units=4,
                 rate=.03, allow_distinctions=True, retain_memory=True):
        _integer(seed, "seed")
        _integer(warmup, "warmup", low=128, high=1024)
        _integer(max_tasks, "task budget", low=1, high=8)
        _integer(max_units, "unit budget", low=max_tasks, high=2 * max_tasks)
        if type(allow_distinctions) is not bool or type(retain_memory) is not bool:
            raise ValueError("Boolean ablation settings required")
        SpherePredictor(rate)  # Validate before allocating mutable state.
        self.config = {"seed": seed, "warmup": warmup, "max_tasks": max_tasks,
                       "max_units": max_units, "rate": rate,
                       "allow_distinctions": allow_distinctions, "retain_memory": retain_memory}
        self.rng = random.Random(seed)
        self.tasks = {}
        self.episode = {"phase": "idle", "task": None, "mask": 0, "coin": None, "events": 0}

    def receive(self, event):
        if not isinstance(event, dict) or event.get("kind") not in ("token", "surface"):
            raise ValueError("Invalid event")
        kind = event["kind"]
        expected = {"kind", "task", "token"} if kind == "token" else {"kind", "task", "surface"}
        if set(event) != expected:
            raise ValueError("Unexpected event fields")
        task = _integer(event["task"], "task", high=self.config["max_tasks"] - 1)
        if kind == "token":
            _integer(event["token"], "token", high=9)
        elif event["surface"] != "sealed":
            raise ValueError("Invalid surface")
        if self.episode["phase"] == "feedback":
            raise RuntimeError("Resolve feedback before receiving another event")
        if self.episode["phase"] == "idle" and kind != "token":
            raise RuntimeError("Receive events before the surface")
        if self.episode["phase"] != "idle" and task != self.episode["task"]:
            raise RuntimeError("Cannot change task during an episode")
        if self.episode["phase"] == "idle":
            if task not in self.tasks:
                self.tasks[task] = _new_task(self.config["rate"])
            self.episode = {"phase": "tokens", "task": task, "mask": 0,
                            "coin": self.rng.randrange(2), "events": 0}
        if not self.config["retain_memory"]:
            self.episode["mask"] = 0
        if kind == "token":
            self.episode["mask"] |= 1 << event["token"]
            self.episode["events"] += 1
            return None
        self.episode["phase"] = "feedback"
        state = self.tasks[task]
        route = self.episode["coin"] if state["token"] is None else _route(self.episode["mask"], state["token"])
        return [state["active"].probability(action, route) for action in (0, 1)]

    def _propose(self, state):
        token = _select_token(state["records"])
        state["proposed_token"] = token
        if token is None:
            state["status"] = "unsupported"
            state["records"] = []
            return
        candidate = SpherePredictor(self.config["rate"])
        control = SpherePredictor(self.config["rate"])
        for mask, coin, action, outcome in state["records"]:
            candidate.update(action, outcome, _route(mask, token))
            control.update(action, outcome, coin)
        state["neural_updates"] += 2 * len(state["records"])
        state["candidate"], state["control"] = candidate, control
        state["status"] = "validating"
        state["records"] = []

    def learn(self, action, outcome):
        _integer(action, "action", high=1)
        _integer(outcome, "outcome", high=1)
        if self.episode["phase"] != "feedback":
            raise RuntimeError("Reach a surface before learning its outcome")
        task = self.episode["task"]
        state = self.tasks[task]
        mask, coin = self.episode["mask"], self.episode["coin"]
        state["steps"] += 1
        status = state["status"]
        if status == "validating":
            group = _route(mask, state["proposed_token"])
            validation = state["validation"]
            # Frozen parameters: no validation label enters either fit.
            validation["parent"].append(state["control"].probability(action, coin))
            validation["proposal"].append(state["candidate"].probability(action, group))
            validation["outcomes"].append(outcome)
            validation["groups"].append(group)
            n = len(validation["outcomes"])
            if n in HORIZONS:
                admitted = sum(s["token"] is not None for s in self.tasks.values())
                decision = evaluate_distinction(
                    **validation, comparison_limit=1000,
                    current_units=self.config["max_tasks"] + admitted,
                    max_units=self.config["max_units"],
                )
                state["decisions"].append({
                    **decision, "task_interactions": state["steps"],
                    "proposed_token": state["proposed_token"],
                    "candidate_fit_updates": sum(map(sum, state["candidate"].counts)),
                    "control_fit_updates": sum(map(sum, state["control"].counts)),
                })
                if decision["decision"] == "accept":
                    enabled = self.config["allow_distinctions"]
                    state["active"] = state["candidate"] if enabled else state["control"]
                    state["token"] = state["proposed_token"] if enabled else None
                    state["status"] = "accepted" if enabled else "ablated"
                elif decision["decision"] in ("reject", "blocked_by_budget"):
                    state["status"] = "rejected" if decision["decision"] == "reject" else "blocked_by_budget"
                elif n == HORIZONS[-1]:
                    state["status"] = "inconclusive"
                if state["status"] != "validating":
                    state["candidate"], state["control"] = None, None
                    state["validation"] = {"parent": [], "proposal": [], "outcomes": [], "groups": []}
                    # Do not train an admitted model on the deciding block.
                    self.finish_evaluation()
                    return
        route = coin if state["token"] is None else _route(mask, state["token"])
        state["active"].update(action, outcome, route)
        state["neural_updates"] += 1
        if status == "collecting":
            state["records"].append([mask, coin, action, outcome])
            if len(state["records"]) == self.config["warmup"]:
                self._propose(state)
        self.finish_evaluation()

    def finish_evaluation(self):
        """Clear a completed episode without using a label or training."""
        if self.episode["phase"] != "feedback":
            raise RuntimeError("No completed observation to clear")
        self.episode = {"phase": "idle", "task": None, "mask": 0, "coin": None, "events": 0}

    def checkpoint(self):
        tasks = []
        for task, state in sorted(self.tasks.items()):
            encoded = copy.deepcopy({k: v for k, v in state.items()
                                     if k not in ("active", "candidate", "control")})
            encoded["task"] = task
            for key in ("active", "candidate", "control"):
                encoded[key] = None if state[key] is None else state[key].checkpoint()
            tasks.append(encoded)
        return {"format": 1, "config": dict(self.config), "rng": self.rng.getstate(),
                "episode": dict(self.episode), "tasks": tasks}

    @classmethod
    def restore(cls, snapshot):
        if not isinstance(snapshot, dict) or set(snapshot) != {"format", "config", "rng", "episode", "tasks"}:
            raise ValueError("Invalid learner checkpoint")
        if type(snapshot["format"]) is not int or snapshot["format"] != 1:
            raise ValueError("Unsupported learner checkpoint")
        config_keys = {"seed", "warmup", "max_tasks", "max_units", "rate", "allow_distinctions", "retain_memory"}
        if not isinstance(snapshot["config"], dict) or set(snapshot["config"]) != config_keys:
            raise ValueError("Invalid learner configuration")
        instance = cls(**snapshot["config"])
        try:
            instance.rng.setstate(_tuples(snapshot["rng"]))
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            raise ValueError("Invalid learner RNG state") from exc
        if not isinstance(snapshot["tasks"], list) or len(snapshot["tasks"]) > instance.config["max_tasks"]:
            raise ValueError("Invalid task states")
        fields = set(_new_task(instance.config["rate"])) | {"task"}
        for raw in snapshot["tasks"]:
            if not isinstance(raw, dict) or set(raw) != fields:
                raise ValueError("Invalid task fields")
            task = _integer(raw["task"], "task", high=instance.config["max_tasks"] - 1)
            if task in instance.tasks or raw["status"] not in STATUSES:
                raise ValueError("Duplicate task or invalid status")
            state = copy.deepcopy(raw)
            del state["task"]
            for key in ("steps", "neural_updates"):
                _integer(state[key], key)
            for key in ("token", "proposed_token"):
                if state[key] is not None:
                    _integer(state[key], key, high=9)
            for key in ("active", "candidate", "control"):
                state[key] = None if raw[key] is None else SpherePredictor.restore(raw[key])
            if state["active"] is None:
                raise ValueError("Missing active predictor")
            validating = state["status"] == "validating"
            if validating:
                if state["candidate"] is None or state["control"] is None:
                    raise ValueError("Missing frozen models")
                if any(sum(map(sum, state[k].counts)) != instance.config["warmup"]
                       for k in ("candidate", "control")):
                    raise ValueError("Frozen fit budget differs")
            elif state["candidate"] is not None or state["control"] is not None:
                raise ValueError("Unexpected frozen models")
            if (state["token"] is not None) != (state["status"] == "accepted"):
                raise ValueError("Inconsistent admission")
            if validating and state["proposed_token"] is None:
                raise ValueError("Missing proposed token")
            if state["status"] == "accepted" and (
                not instance.config["allow_distinctions"] or state["token"] != state["proposed_token"]
            ):
                raise ValueError("Inconsistent accepted distinction")
            if state["status"] == "ablated" and instance.config["allow_distinctions"]:
                raise ValueError("Inconsistent ablation")
            if not isinstance(state["records"], list) or len(state["records"]) > instance.config["warmup"]:
                raise ValueError("Invalid training records")
            for record in state["records"]:
                if not isinstance(record, list) or len(record) != 4:
                    raise ValueError("Invalid record")
                _integer(record[0], "memory mask", high=1023)
                for value in record[1:]:
                    _integer(value, "binary record", high=1)
            validation = state["validation"]
            if not isinstance(validation, dict) or set(validation) != {"parent", "proposal", "outcomes", "groups"}:
                raise ValueError("Invalid validation block")
            if any(not isinstance(values, list) for values in validation.values()):
                raise ValueError("Invalid validation arrays")
            n = len(validation["outcomes"])
            if n >= HORIZONS[-1] or any(len(v) != n for v in validation.values()) or (not validating and n):
                raise ValueError("Invalid validation length")
            if validating and state["steps"] != instance.config["warmup"] + n:
                raise ValueError("Validation exposure differs")
            if state["status"] == "collecting":
                if state["steps"] != len(state["records"]) or state["steps"] >= instance.config["warmup"]:
                    raise ValueError("Collection exposure differs")
            elif state["records"] or state["steps"] < instance.config["warmup"]:
                raise ValueError("Unexpected training records")
            for value in validation["parent"] + validation["proposal"]:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError("Invalid saved probability")
            for value in validation["outcomes"] + validation["groups"]:
                _integer(value, "binary validation value", high=1)
            if not isinstance(state["decisions"], list) or len(state["decisions"]) > len(HORIZONS):
                raise ValueError("Invalid decision log")
            for decision in state["decisions"]:
                if not isinstance(decision, dict) or decision.get("validation_interactions") not in HORIZONS:
                    raise ValueError("Invalid decision")
                for key in ("mean_log_score_gain", "uncertainty_bound", "gain_lower", "gain_upper", "complexity_cost"):
                    if not isinstance(decision.get(key), (int, float)) or not math.isfinite(decision[key]):
                        raise ValueError("Invalid decision statistic")
            instance.tasks[task] = state
        if sum(s["token"] is not None for s in instance.tasks.values()) + instance.config["max_tasks"] > instance.config["max_units"]:
            raise ValueError("Admission exceeds memory budget")
        episode = snapshot["episode"]
        if not isinstance(episode, dict) or set(episode) != {"phase", "task", "mask", "coin", "events"}:
            raise ValueError("Invalid episode state")
        _integer(episode["mask"], "memory mask", high=1023)
        _integer(episode["events"], "event count")
        if episode["phase"] == "idle":
            if episode != {"phase": "idle", "task": None, "mask": 0, "coin": None, "events": 0}:
                raise ValueError("Invalid idle episode")
        elif episode["phase"] in ("tokens", "feedback"):
            _integer(episode["task"], "episode task", high=instance.config["max_tasks"] - 1)
            if episode["task"] not in instance.tasks or episode["events"] < 1:
                raise ValueError("Unknown episode task")
            _integer(episode["coin"], "episode route", high=1)
        else:
            raise ValueError("Invalid episode phase")
        instance.episode = copy.deepcopy(episode)
        return instance

    def metrics(self):
        active_points = 4 * len(self.tasks)
        stored_points = active_points + 8 * sum(s["status"] == "validating" for s in self.tasks.values())
        return {
            "active_neural_points": active_points, "active_coordinates": 3 * active_points,
            "active_intrinsic_dof": 2 * active_points, "stored_neural_points": stored_points,
            "memory_mask_bits": 10, "neural_updates": sum(s["neural_updates"] for s in self.tasks.values()),
            "tasks": {str(task): {"steps": s["steps"], "status": s["status"], "token": s["token"],
                                 "decisions": copy.deepcopy(s["decisions"])}
                      for task, s in sorted(self.tasks.items())},
        }
