"""Sequential laboratory; the public observation never reveals the hidden rule."""
import random


def _integer(value, name, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f"Invalid {name}")
    return value


def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


class HistoryWorld:
    def __init__(self, seed=0, rule=0, phase="acquisition", noise=False, task=0):
        _integer(seed, "seed")
        _integer(rule, "rule", high=1)
        _integer(task, "task")
        if phase not in ("acquisition", "transfer") or type(noise) is not bool:
            raise ValueError("Invalid world configuration")
        self.seed, self.rule, self.phase, self.noise, self.task = seed, rule, phase, noise, task
        self.inputs_rng = random.Random(seed)
        self.outcomes_rng = random.Random(seed + 1000003)
        self.completed = 0
        self.pending = None

    def observe(self):
        if self.pending is not None:
            raise RuntimeError("Resolve the current interaction first")
        cue = self.inputs_rng.randrange(2)
        if self.phase == "acquisition":
            before = self.inputs_rng.randrange(3)
            after = self.inputs_rng.randint(1, 4)
            alphabet = range(2, 6)
        else:
            before = self.inputs_rng.randint(4, 12)
            after = self.inputs_rng.randint(8, 20)
            alphabet = range(2, 10)
        history = [self.inputs_rng.choice(alphabet) for _ in range(before)]
        history += [cue]
        history += [self.inputs_rng.choice(alphabet) for _ in range(after)]
        self.pending = cue
        return {"history": history, "observation": {"task": self.task, "surface": "sealed"}}

    def act(self, action):
        _integer(action, "action", high=1)
        if self.pending is None:
            raise RuntimeError("Observe before acting")
        outcome = self.outcomes_rng.randrange(2) if self.noise else int(
            action == (self.pending ^ self.rule)
        )
        self.pending = None
        self.completed += 1
        return outcome

    def checkpoint(self):
        # This is an environment checkpoint, separate from a future learner's state.
        return {
            "format": 1, "seed": self.seed, "rule": self.rule, "phase": self.phase,
            "noise": self.noise, "task": self.task, "completed": self.completed,
            "pending": self.pending, "inputs_rng": self.inputs_rng.getstate(),
            "outcomes_rng": self.outcomes_rng.getstate(),
        }

    @classmethod
    def restore(cls, state):
        if not isinstance(state, dict) or type(state.get("format")) is not int or state["format"] != 1:
            raise ValueError("Invalid environment checkpoint")
        keys = {"format", "seed", "rule", "phase", "noise", "task", "completed",
                "pending", "inputs_rng", "outcomes_rng"}
        if set(state) != keys:
            raise ValueError("Checkpoint fields differ")
        _integer(state["completed"], "completed")
        if state["pending"] is not None:
            _integer(state["pending"], "pending", high=1)
        world = cls(state["seed"], state["rule"], state["phase"], state["noise"], state["task"])
        try:
            world.inputs_rng.setstate(_tuples(state["inputs_rng"]))
            world.outcomes_rng.setstate(_tuples(state["outcomes_rng"]))
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            raise ValueError("Invalid checkpoint RNG state") from exc
        world.completed, world.pending = state["completed"], state["pending"]
        return world
