"""Resumable intrinsic clustering and replay for the optional trace backend."""
import copy
import math
import random

from setharkk import contracts as wire
from .cooperative import sealed, unsealed
from .plastic_revision import MEAN_ITERATIONS
from .spherical import point, distance, exp_map, log_map
from .world import _tuples

BLOCK = 8


class TraceFitWork:
    PHASES = ("farthest_a", "farthest_b", "group", "mean", "support",
              "shuffle", "replay", "publish", "done")

    def __init__(self, core, leaf, kind):
        if kind not in ("split", "revision") or leaf not in core.nodes or core.nodes[leaf]["children"] is not None:
            raise ValueError("Invalid trace fit target")
        self.core, self.leaf, self.kind = core, leaf, kind
        self.rows = copy.deepcopy(core.nodes[leaf]["records"])
        if not self.rows:
            raise ValueError("Empty trace fit")
        self.centers = [list(self.rows[0][0]), list(self.rows[0][0])]
        self.phase = "support" if kind == "revision" else "farthest_a"
        self.cursor = self.outer = self.mean_group = self.mean_iteration = 0
        self.best_distance = -1.0
        self.groups = [[], []]
        self.tangents = []
        self.q = None
        self.support = [[0, 0], [0, 0]]
        self.candidate, self.control = core._bank(), core._bank()
        self.rng = random.Random(0)
        self.rng.setstate(core.rng.getstate())
        self.order = list(range(len(self.rows)))
        self.epoch = self.row = self.bank = self.gradients = self.units = 0

    def _abort(self):
        self.core.next_trial = self.core.steps+self.core.config["cooldown"]
        self.phase = "done"

    def _start_mean(self, group):
        self.mean_group, self.mean_iteration, self.cursor = group, 0, 0
        self.q, self.tangents = list(self.groups[group][0]), []
        self.phase = "mean"

    def _finish_mean(self):
        self.centers[self.mean_group] = self.q
        if self.mean_group == 0:
            self._start_mean(1)
        else:
            self.outer += 1
            self.cursor, self.groups = 0, [[], []]
            self.phase = "support" if self.outer == 8 else "group"

    def advance(self):
        if self.phase == "done":
            return False
        n = len(self.rows)
        if self.phase in ("farthest_a", "farthest_b"):
            target = 0 if self.phase == "farthest_a" else 1
            destination = 1-target
            end = min(n, self.cursor+BLOCK)
            for i in range(self.cursor, end):
                d = distance(self.rows[i][0], self.centers[target])
                if d > self.best_distance:
                    self.best_distance, self.centers[destination] = d, list(self.rows[i][0])
            self.cursor = end
            if end == n:
                self.cursor, self.best_distance = 0, -1.0
                if self.phase == "farthest_a":
                    self.phase = "farthest_b"
                elif distance(*self.centers) < 1e-6:
                    self._abort()
                else:
                    self.phase = "group"
        elif self.phase == "group":
            end = min(n, self.cursor+BLOCK)
            for state, coin, action, outcome in self.rows[self.cursor:end]:
                route = min(range(2), key=lambda r: distance(state, self.centers[r]))
                self.groups[route].append(state)
            self.cursor = end
            if end == n:
                if any(len(group) < 16 for group in self.groups):
                    self._abort()
                else:
                    self._start_mean(0)
        elif self.phase == "mean":
            group = self.groups[self.mean_group]
            end = min(len(group), self.cursor+BLOCK)
            self.tangents.extend(log_map(self.q, p) for p in group[self.cursor:end])
            self.cursor = end
            if end == len(group):
                tangent = [math.fsum(t[j] for t in self.tangents)/len(group) for j in range(3)]
                if math.fsum(t*t for t in tangent) < 1e-24:
                    self._finish_mean()
                else:
                    self.q = exp_map(self.q, tangent)
                    self.mean_iteration += 1
                    if self.mean_iteration == MEAN_ITERATIONS:
                        self._finish_mean()
                    else:
                        self.cursor, self.tangents = 0, []
        elif self.phase == "support":
            end = min(n, self.cursor+BLOCK)
            for state, coin, action, outcome in self.rows[self.cursor:end]:
                route = 0 if self.kind == "revision" else min(range(2), key=lambda r: distance(state, self.centers[r]))
                self.support[route][action] += 1
            self.cursor = end
            if end == n:
                relevant = self.support[:1] if self.kind == "revision" else self.support
                if min(min(row) for row in relevant) < 8:
                    self._abort()
                else:
                    self.phase = "shuffle"
        elif self.phase == "shuffle":
            self.rng.shuffle(self.order)
            self.row = self.bank = 0
            self.phase = "replay"
        elif self.phase == "replay":
            state, coin, action, outcome = self.rows[self.order[self.row]]
            if self.bank == 0:
                route = 0 if self.kind == "revision" else min(range(2), key=lambda r: distance(state, self.centers[r]))
                self.candidate.update(action, outcome, route)
                self.bank = 1
            else:
                self.control.update(action, outcome, coin)
                self.bank, self.row = 0, self.row+1
                if self.row == n:
                    self.epoch += 1
                    self.phase = "publish" if self.epoch == self.core.config["replay_passes"] else "shuffle"
            self.gradients += 1
        elif self.phase == "publish":
            core = self.core
            core.attempts += 1
            core.fit_records_total += n
            core.neural_updates += self.gradients
            core.rng.setstate(self.rng.getstate())
            cal = core._trial_calibration(self.leaf, self.centers, self.candidate, self.control, self.kind)
            core.trial = {"kind": self.kind, "leaf": self.leaf, "centers": self.centers,
                          "candidate": self.candidate, "control": self.control,
                          "reference": copy.deepcopy(core._served(self.leaf)),
                          "cal": cal, "n": 0, "improvement": 0.0, "relevance": 0.0,
                          "support": [[0, 0], [0, 0]], "started_at": core.steps, "fit_records": n}
            self.phase = "done"
        else:
            raise ValueError("Unknown trace fit phase")
        self.units += 1
        return True

    def checkpoint(self):
        data = {k: copy.deepcopy(v) for k, v in self.__dict__.items()
                if k not in ("core", "rng", "candidate", "control")}
        data.update(core=self.core.checkpoint(), rng=self.rng.getstate(),
                    candidate=self.candidate.checkpoint(), control=self.control.checkpoint())
        return sealed(data)

    @classmethod
    def restore(cls, snapshot):
        from .adaptive_trace_v2 import AdaptiveTraceLearnerV2
        from .shared import SharedSpherePredictor
        data = unsealed(snapshot)
        core = AdaptiveTraceLearnerV2.restore(data["core"])
        new = cls(core, data["leaf"], data["kind"])
        if set(data) != set(new.__dict__) or data["phase"] not in cls.PHASES:
            raise ValueError("Invalid trace fit state")
        if data["rows"] != core.nodes[data["leaf"]]["records"]:
            raise ValueError("Fit data differs from staged observations")
        for k in ("cursor", "outer", "mean_group", "mean_iteration", "epoch", "row", "bank", "gradients", "units"):
            wire.counter(data[k], k)
        n = len(data["rows"])
        if sorted(data["order"]) != list(range(n)) or any(type(i) is not int for i in data["order"]):
            raise ValueError("Invalid replay permutation")
        if data["cursor"] > n or data["outer"] > 8 or data["mean_group"] not in (0, 1) or data["mean_iteration"] > MEAN_ITERATIONS:
            raise ValueError("Invalid clustering cursor")
        if type(data["centers"]) is not list or len(data["centers"]) != 2 or type(data["groups"]) is not list or len(data["groups"]) != 2:
            raise ValueError("Invalid partial clustering shape")
        for value in data["centers"]:
            point(value)
        for group in data["groups"]:
            if type(group) is not list or len(group) > n:
                raise ValueError("Invalid partial cluster memory")
            for value in group:
                point(value)
        if sum(map(len, data["groups"])) > n:
            raise ValueError("Partial clusters exceed replay memory")
        if data["q"] is not None:
            point(data["q"])
        if type(data["tangents"]) is not list or len(data["tangents"]) > n or any(
                type(t) is not list or len(t) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in t)
                for t in data["tangents"]):
            raise ValueError("Invalid partial mean tangents")
        if data["phase"] == "mean" and (not data["groups"][data["mean_group"]] or
                data["q"] is None or data["cursor"] > len(data["groups"][data["mean_group"]]) or
                len(data["tangents"]) != data["cursor"]):
            raise ValueError("Mean cursor differs from partial sum")
        support = data["support"]
        if type(support) is not list or len(support) != 2 or any(type(row) is not list or len(row) != 2 for row in support):
            raise ValueError("Invalid fit support shape")
        for row in support:
            for value in row:
                wire.counter(value, "fit support")
        if type(data["best_distance"]) not in (int, float) or not math.isfinite(data["best_distance"]):
            raise ValueError("Invalid farthest distance")
        if data["epoch"] > core.config["replay_passes"] or data["row"] > n or data["bank"] not in (0, 1):
            raise ValueError("Invalid replay cursor")
        for k, v in data.items():
            if k not in ("core", "rng", "candidate", "control"):
                setattr(new, k, copy.deepcopy(v))
        new.rng.setstate(_tuples(data["rng"]))
        new.candidate = SharedSpherePredictor.restore(data["candidate"])
        new.control = SharedSpherePredictor.restore(data["control"])
        for name, expected in (("candidate", (new.gradients+1)//2), ("control", new.gradients//2)):
            bank = getattr(new, name)
            if bank.n_actions != 2 or bank.n_routes != 2 or bank.rate != core.config["rate"] or sum(map(sum, bank.counts)) != expected:
                raise ValueError("Partial fit bank differs from gradients")
        if new.phase in ("replay", "shuffle", "publish", "done") and new.gradients:
            position = 2*(new.epoch*n+new.row)+new.bank
            if new.row == n:
                position -= 2*n
            if new.gradients != position:
                raise ValueError("Fit gradients differ from replay position")
        return new


class TraceReceiptWork:
    def __init__(self, core, action, receipt):
        self.core, self.action, self.receipt = core, action, copy.deepcopy(receipt)
        self.phase, self.units, self.fit = "feedback", 0, None

    def _defer(self, fit):
        self.fit = fit

    def advance(self):
        if self.phase == "done":
            return False
        if self.phase == "feedback":
            if self.receipt["status"] == "observed":
                self.core.learn(self.action, self.receipt["outcome"]["value"], defer=self._defer)
            else:
                self.core.finish_evaluation()
            self.phase = "fit" if self.fit is not None else "done"
        elif self.phase == "fit":
            self.fit.advance()
            if self.fit.phase == "done":
                self.phase = "done"
        else:
            raise ValueError("Unknown trace receipt phase")
        self.units += 1
        return True

    def checkpoint(self):
        return sealed({"core": self.core.checkpoint(), "action": self.action, "receipt": self.receipt,
                       "phase": self.phase, "units": self.units,
                       "fit": None if self.fit is None else self.fit.checkpoint()})

    @classmethod
    def restore(cls, snapshot):
        from .adaptive_trace_v2 import AdaptiveTraceLearnerV2
        data = unsealed(snapshot)
        if set(data) != {"core", "action", "receipt", "phase", "units", "fit"}:
            raise ValueError("Invalid trace receipt state")
        receipt = wire.receipt(data["receipt"])
        fit = None if data["fit"] is None else TraceFitWork.restore(data["fit"])
        core = AdaptiveTraceLearnerV2.restore(data["core"])
        if fit is not None and fit.core.checkpoint() != core.checkpoint():
            raise ValueError("Receipt and fit core differ")
        if fit is not None:
            core = fit.core
        new = cls(core, data["action"], receipt)
        if type(new.action) is not int or new.action not in (0, 1) or data["phase"] not in ("feedback", "fit", "done"):
            raise ValueError("Invalid trace receipt action/phase")
        wire.counter(data["units"], "work units")
        if receipt["status"] == "observed":
            o = receipt["outcome"]
            if o["measure"] != "lab.success" or o["unit"] != "binary" or type(o["value"]) is not int or o["value"] not in (0, 1):
                raise ValueError("Invalid trace work outcome")
        if data["phase"] == "feedback":
            if core.phase != "feedback" or fit is not None or data["units"] != 0:
                raise ValueError("Feedback already advanced")
        elif core.phase != "idle":
            raise ValueError("Advanced receipt has pending feedback")
        if data["phase"] == "fit" and (fit is None or fit.phase == "done"):
            raise ValueError("Missing live fit")
        if data["phase"] == "done" and fit is not None and fit.phase != "done":
            raise ValueError("Unfinished fit marked complete")
        new.phase, new.units, new.fit = data["phase"], data["units"], fit
        return new
