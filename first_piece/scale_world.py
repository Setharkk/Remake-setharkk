"""Synthetic scaling fixture. Hidden rules are never emitted to the learner."""
import random

from .world import _integer


class ScaleWorld:
    def __init__(self, seed=0, *, n_symbols=64, n_contexts=16, n_actions=4):
        _integer(n_symbols, "symbols", low=4, high=128)
        _integer(n_contexts, "contexts", low=1, high=31)
        if type(n_actions) is not int or n_actions not in (2, 4):
            raise ValueError("This fixture supports two or four actions")
        self.seed, self.n_contexts, self.n_actions = seed, n_contexts, n_actions
        self.rng = random.Random(seed)
        names_rng = random.Random(9000000 + seed)
        self.symbols = [f"s.{names_rng.getrandbits(80):020x}" for _ in range(n_symbols)]
        self.cues = self.rng.sample(self.symbols, 4)

    def episode(self, context, *, changed=False):
        _integer(context, "context", high=self.n_contexts)
        cues = list(self.cues)
        self.rng.shuffle(cues)
        extras = [s for s in self.symbols if s not in self.cues]
        tokens = cues + self.rng.sample(extras, min(4, len(extras)))
        self.rng.shuffle(tokens)
        a = int(tokens.index(self.cues[0]) < tokens.index(self.cues[1]))
        b = int(tokens.index(self.cues[2]) < tokens.index(self.cues[3]))
        target = (a ^ b) if self.n_actions == 2 else a + 2 * b
        if changed and context == 0:
            target = (target + 1) % self.n_actions
        return [{"kind": "token", "token": t, "task": context} for t in tokens] + [
            {"kind": "surface", "surface": "sealed", "task": context}], target
