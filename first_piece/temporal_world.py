"""Ordered synthetic world; the public stream exposes no hidden regime."""
import random

from .world import _integer, _tuples


class TemporalWorld:
    def __init__(self, seed=0, *, rule=0, pair=(0, 1), phase="acquisition",
                 mode="structured", task=0):
        _integer(seed, "seed")
        _integer(rule, "rule", high=1)
        _integer(task, "task", high=7)
        if phase not in ("acquisition", "transfer") or mode not in ("structured", "noise", "action_only"):
            raise ValueError("Invalid world condition")
        if not isinstance(pair, (tuple, list)) or len(pair) != 2 or any(type(t) is not int for t in pair) or tuple(pair) not in ((0, 1), (2, 3)):
            raise ValueError("Unsupported target relation")
        self.seed, self.rule, self.pair = seed, rule, tuple(pair)
        self.phase, self.mode, self.task = phase, mode, task
        self.inputs_rng = random.Random(seed)
        self.outcomes_rng = random.Random(seed + 1000003)
        self.completed, self.pending, self.sequence, self.cursor = 0, None, None, 0
        self.awaiting_action = False

    def next_event(self):
        if self.awaiting_action:
            raise RuntimeError("Execute or cancel before another observation")
        if self.sequence is None:
            signals = [0, 1, 2, 3]
            self.inputs_rng.shuffle(signals)
            self.pending = int(signals.index(self.pair[0]) < signals.index(self.pair[1]))
            alphabet = range(4, 7) if self.phase == "acquisition" else range(7, 10)
            self.sequence = []
            for signal in signals:
                count = self.inputs_rng.randrange(3) if self.phase == "acquisition" else self.inputs_rng.randint(4, 9)
                self.sequence.extend(self.inputs_rng.choice(alphabet) for _ in range(count))
                self.sequence.append(signal)
            tail = self.inputs_rng.randrange(3) if self.phase == "acquisition" else self.inputs_rng.randint(4, 9)
            self.sequence.extend(self.inputs_rng.choice(alphabet) for _ in range(tail))
        if self.cursor < len(self.sequence):
            token = self.sequence[self.cursor]
            self.cursor += 1
            return {"kind": "token", "token": token, "task": self.task}
        self.awaiting_action = True
        return {"kind": "surface", "surface": "sealed", "task": self.task}

    def act(self, action):
        _integer(action, "action", high=1)
        if not self.awaiting_action:
            raise RuntimeError("Reach surface before acting")
        if self.mode == "noise":
            result = self.outcomes_rng.randrange(2)
        elif self.mode == "action_only":
            result = int(action == self.rule)
        else:
            result = int(action == (self.pending ^ self.rule))
        self.completed += 1
        self.sequence, self.pending, self.cursor, self.awaiting_action = None, None, 0, False
        return result

    def change(self, *, rule=None, pair=None):
        if self.sequence is not None:
            raise RuntimeError("Change the world only between episodes")
        if rule is not None:
            _integer(rule, "rule", high=1)
        if pair is not None and (not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(type(t) is not int for t in pair) or tuple(pair) not in ((0, 1), (2, 3))):
            raise ValueError("Unsupported target relation")
        if rule is not None:
            self.rule = rule
        if pair is not None:
            self.pair = tuple(pair)

    def abort_episode(self):
        if self.sequence is None:
            raise RuntimeError("No episode to abort")
        self.sequence, self.pending, self.cursor, self.awaiting_action = None, None, 0, False

    def checkpoint(self):
        return {"format": 1, "seed": self.seed, "rule": self.rule, "pair": list(self.pair),
                "phase": self.phase, "mode": self.mode, "task": self.task,
                "completed": self.completed, "pending": self.pending,
                "sequence": None if self.sequence is None else list(self.sequence),
                "cursor": self.cursor, "awaiting_action": self.awaiting_action,
                "inputs_rng": self.inputs_rng.getstate(), "outcomes_rng": self.outcomes_rng.getstate()}

    @classmethod
    def restore(cls, state):
        keys = {"format", "seed", "rule", "pair", "phase", "mode", "task",
                "completed", "pending", "sequence", "cursor", "awaiting_action", "inputs_rng", "outcomes_rng"}
        if type(state) is not dict or set(state) != keys or type(state["format"]) is not int or state["format"] != 1:
            raise ValueError("Invalid temporal world checkpoint")
        instance = cls(state["seed"], rule=state["rule"], pair=state["pair"],
                       phase=state["phase"], mode=state["mode"], task=state["task"])
        _integer(state["completed"], "completed")
        _integer(state["cursor"], "cursor")
        if type(state["awaiting_action"]) is not bool:
            raise ValueError("Invalid action boundary")
        sequence = state["sequence"]
        if sequence is None:
            if state["pending"] is not None or state["cursor"] or state["awaiting_action"]:
                raise ValueError("Invalid idle world")
        else:
            if type(sequence) is not list or not sequence or state["cursor"] > len(sequence):
                raise ValueError("Invalid sequence")
            for token in sequence:
                _integer(token, "token", high=9)
            if any(sequence.count(i) != 1 for i in range(4)):
                raise ValueError("Missing or repeated signal")
            expected = int(sequence.index(instance.pair[0]) < sequence.index(instance.pair[1]))
            if type(state["pending"]) is not int or state["pending"] != expected or (state["awaiting_action"] and state["cursor"] != len(sequence)):
                raise ValueError("World target and saved sequence differ")
        try:
            instance.inputs_rng.setstate(_tuples(state["inputs_rng"]))
            instance.outcomes_rng.setstate(_tuples(state["outcomes_rng"]))
        except (TypeError, ValueError, OverflowError, IndexError) as exc:
            raise ValueError("Invalid random state") from exc
        instance.completed, instance.pending = state["completed"], state["pending"]
        instance.sequence = None if sequence is None else list(sequence)
        instance.cursor, instance.awaiting_action = state["cursor"], state["awaiting_action"]
        return instance
