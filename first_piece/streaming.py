"""Event-at-a-time environment. The learner never receives a history list."""
from .world import HistoryWorld, _integer


class StreamingWorld:
    def __init__(self, seed=0, rule=0, phase="acquisition", mode="structured", task=0):
        if mode not in ("structured", "noise", "action_only"):
            raise ValueError("Invalid streaming mode")
        self.mode = mode
        self._world = HistoryWorld(seed, rule, phase, mode == "noise", task)
        self._sequence = None
        self._cursor = 0
        self._awaiting_action = False

    def next_event(self):
        if self._awaiting_action:
            raise RuntimeError("Act before requesting another event")
        if self._sequence is None:
            self._sequence = self._world.observe()["history"]
        task = self._world.task
        if self._cursor < len(self._sequence):
            token = self._sequence[self._cursor]
            self._cursor += 1
            return {"kind": "token", "token": token, "task": task}
        self._awaiting_action = True
        return {"kind": "surface", "surface": "sealed", "task": task}

    def act(self, action):
        _integer(action, "action", high=1)
        if not self._awaiting_action:
            raise RuntimeError("Reach the surface before acting")
        outcome = self._world.act(action)
        if self.mode == "action_only":
            outcome = int(action == self._world.rule)
        self._sequence = None
        self._cursor = 0
        self._awaiting_action = False
        return outcome

    def checkpoint(self):
        return {"format": 1, "mode": self.mode, "world": self._world.checkpoint(),
                "sequence": None if self._sequence is None else list(self._sequence),
                "cursor": self._cursor, "awaiting_action": self._awaiting_action}

    @classmethod
    def restore(cls, state):
        keys = {"format", "mode", "world", "sequence", "cursor", "awaiting_action"}
        if not isinstance(state, dict) or set(state) != keys or type(state.get("format")) is not int or state["format"] != 1:
            raise ValueError("Invalid streaming checkpoint")
        world = HistoryWorld.restore(state["world"])
        instance = cls(world.seed, world.rule, world.phase, state["mode"], world.task)
        if world.noise != (state["mode"] == "noise") or type(state["awaiting_action"]) is not bool:
            raise ValueError("Inconsistent streaming checkpoint")
        cursor = _integer(state["cursor"], "cursor")
        sequence = state["sequence"]
        if sequence is None:
            if cursor or state["awaiting_action"] or world.pending is not None:
                raise ValueError("Inconsistent idle stream")
        else:
            if not isinstance(sequence, list) or not sequence or cursor > len(sequence):
                raise ValueError("Invalid saved sequence")
            for token in sequence:
                _integer(token, "token", high=9)
            cues = [t for t in sequence if t in (0, 1)]
            if len(cues) != 1 or world.pending != cues[0]:
                raise ValueError("Sequence and world state differ")
            if state["awaiting_action"] and cursor != len(sequence):
                raise ValueError("Surface before end of sequence")
        instance._world = world
        instance._sequence = None if sequence is None else list(sequence)
        instance._cursor = cursor
        instance._awaiting_action = state["awaiting_action"]
        return instance
