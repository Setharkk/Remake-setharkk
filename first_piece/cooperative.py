"""Cooperative receipt work for the active format-8 S2 engine.

Work quotas count bounded primitives, not hard real-time milliseconds.
The committed wire adapter stays unchanged until all staged work finishes.
"""
import copy
import hashlib
import itertools
import json
import math
import random
import threading
import time

from setharkk import contracts as wire
from .adapter import _semantic_receipt
from .plastic_revision_adapter import PlasticRevisionAdapter
from .plastic_revision import COMPARISONS, REFINEMENT_GAIN, REFRESH_GAIN
from .shared import _feature_masks, log_probability, PENALTY, SharedSpherePredictor
from .world import _tuples

PROTOCOL = "first_piece.cooperative.v1"


def sealed(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"data": copy.deepcopy(data), "checksum": hashlib.sha256(raw.encode()).hexdigest()}


def unsealed(snapshot):
    if type(snapshot) is not dict or set(snapshot) != {"data", "checksum"}:
        raise ValueError("Invalid work envelope")
    if sealed(snapshot["data"])["checksum"] != snapshot["checksum"]:
        raise ValueError("Work checksum differs")
    return copy.deepcopy(snapshot["data"])


def rows_of(core):
    return [(slot, *row) for slot in sorted(core.tasks) for row in core.tasks[slot]["records"]]


def canonical(core):
    data = core.checkpoint()
    for search in data["searches"]:
        search["elapsed_seconds"] = 0
    return data


class SearchWork:
    """Exact format-8 score and tie-breaker, one block or hypothesis per step."""
    def __init__(self, core, rows, scope, attempt):
        self.core, self.rows, self.scope, self.attempt = core, rows, scope, attempt
        self.phase, self.cursor, self.i, self.j = "masks", 0, 0, 1
        self.masks = {}
        self.classes = [[0, 0] for _ in range(core.config["n_actions"])]
        self.pool, self.pairs, self.extend, self.seen = [], [], [], set()
        self.best, self.examined, self.eligible = None, 0, 0
        self.elapsed = 0.0

    @staticmethod
    def key(item):
        return (-math.inf if item[0] is None else item[0], item[1], item[2])

    def score(self, program):
        self.examined += 1
        total = len(self.rows)
        all_rows = (1 << total) - 1
        groups = [all_rows]
        for feature in program:
            m = self.masks[feature]
            groups = [g & (~m & all_rows) for g in groups] + [g & m for g in groups]
        result = 0.0
        for group in groups:
            count = group.bit_count()
            if not count:
                continue
            if count < 16:
                return None
            for pair in self.classes:
                zero, one = ((group & m).bit_count() for m in pair)
                denom = zero + one + 2
                if zero:
                    result += zero * math.log((zero + 1) / denom)
                if one:
                    result += one * math.log((one + 1) / denom)
        return result / total - PENALTY * len(program)

    def consider(self, program):
        local = self.scope is not None and self.core.context_offset + self.scope in program
        candidate = (self.score(program), (int(local), tuple(-f for f in program)), tuple(program))
        if candidate[0] is not None and (self.best is None or
                candidate[0] > self.best[0] + 1e-12 or
                (abs(candidate[0] - self.best[0]) <= 1e-12 and candidate[1] > self.best[1])):
            self.best = candidate
        return candidate

    def advance(self):
        start = time.perf_counter()
        try:
            self._advance()
        finally:
            self.elapsed += time.perf_counter() - start

    def _advance(self):
        if self.phase == "masks":
            stop = min(self.cursor + 8, len(self.rows))
            block = self.rows[self.cursor:stop]
            masks = _feature_masks(block, self.core.config["max_symbols"],
                                   self.core.context_offset, self.core.config["max_tasks"])
            for feature, mask in masks.items():
                self.masks[feature] = self.masks.get(feature, 0) | (mask << self.cursor)
            for index in range(self.cursor, stop):
                action, outcome = self.rows[index][4:6]
                self.classes[action][outcome] |= 1 << index
            self.cursor = stop
            if stop == len(self.rows):
                self.phase = "pool"
        elif self.phase == "pool":
            total = len(self.rows)
            eligible = [f for f, m in self.masks.items()
                        if min(m.bit_count(), total-m.bit_count()) >= 16]
            rank = lambda f: (-min(self.masks[f].bit_count(), total-self.masks[f].bit_count()), f)
            contexts = sorted((f for f in eligible if f >= self.core.context_offset), key=rank)
            relations = sorted((f for f in eligible if
                self.core.config["max_symbols"] <= f < self.core.context_offset), key=rank)
            presences = sorted((f for f in eligible if f < self.core.config["max_symbols"]), key=rank)
            pool = contexts[:32] + relations[:max(0, self.core.config["pool_size"]-len(contexts[:32])-16)] + presences[:16]
            chosen = set(pool)
            pool += sorted((f for f in eligible if f not in chosen), key=rank)[:self.core.config["pool_size"]-len(pool)]
            retained = [f for f in self.core.program if f in eligible]
            self.pool = sorted((retained+[f for f in pool if f not in retained])[:self.core.config["pool_size"]])
            self.eligible, self.cursor, self.phase = len(eligible), 0, "singles"
        elif self.phase == "singles":
            if self.cursor < len(self.pool):
                self.consider((self.pool[self.cursor],))
                self.cursor += 1
            else:
                self.phase = "pairs" if self.core.config["max_features"] >= 2 else "done"
        elif self.phase == "pairs":
            if self.i < len(self.pool)-1:
                self.pairs.append(self.consider((self.pool[self.i], self.pool[self.j])))
                self.j += 1
                if self.j == len(self.pool):
                    self.i, self.j = self.i+1, self.i+2
            else:
                self.phase = "extend" if self.core.config["max_features"] >= 3 else "done"
        elif self.phase == "extend":
            top = sorted(self.pairs, key=self.key, reverse=True)[:self.core.config["pair_beam"]]
            retained = list(itertools.combinations([f for f in self.core.program if f in self.pool], 2))
            self.extend = list(dict.fromkeys([p[2] for p in top]+retained))
            self.i, self.cursor, self.phase = 0, 0, "triples"
        elif self.phase == "triples":
            if self.i == len(self.extend) or not self.pool:
                self.phase = "done"
                return
            pair, feature = self.extend[self.i], self.pool[self.cursor]
            self.cursor += 1
            if self.cursor == len(self.pool):
                self.i, self.cursor = self.i+1, 0
            triple = tuple(sorted((*pair, feature)))
            if feature not in pair and triple not in self.seen:
                self.seen.add(triple)
                self.consider(triple)
        elif self.phase != "done":
            raise ValueError("Unknown search phase")

    def report(self):
        if self.phase != "done":
            raise RuntimeError("Search unfinished")
        return {"attempt": self.attempt, "scope": self.scope, "score_source": "served",
                "at": self.core.steps, "fit_records": len(self.rows),
                "eligible_features": self.eligible, "pooled_features": len(self.pool),
                "hypotheses_examined": self.examined, "elapsed_seconds": self.elapsed,
                "program": None if self.best is None else list(self.best[2])}

    def checkpoint(self):
        return {"phase": self.phase, "cursor": self.cursor, "i": self.i, "j": self.j,
                "masks": {str(f): format(m, "x") for f,m in self.masks.items()},
                "classes": [[format(m, "x") for m in row] for row in self.classes],
                "pool": self.pool, "pairs": self.pairs, "extend": self.extend,
                "seen": sorted(self.seen), "best": self.best, "examined": self.examined,
                "eligible": self.eligible, "elapsed": self.elapsed}

    @classmethod
    def restore(cls, core, rows, scope, attempt, snapshot):
        new = cls(core, rows, scope, attempt)
        if type(snapshot) is not dict or set(snapshot) != set(new.checkpoint()):
            raise ValueError("Invalid search work fields")
        if snapshot["phase"] not in ("masks","pool","singles","pairs","extend","triples","done"):
            raise ValueError("Unknown saved search phase")
        for name in ("cursor","i","j","examined","eligible"):
            wire.counter(snapshot[name], name)
        for name in ("phase","cursor","i","j","examined","eligible","elapsed","pool"):
            setattr(new, name, copy.deepcopy(snapshot[name]))
        capacity = core.context_offset + core.config["max_tasks"]
        if any(type(f) is not str or not f.isdecimal() or str(int(f)) != f or type(m) is not str or not m or format(int(m,16),"x") != m for f,m in snapshot["masks"].items()):
            raise ValueError("Noncanonical search mask")
        new.masks = {int(f): int(m,16) for f,m in snapshot["masks"].items()}
        if any(not 0 <= f < capacity or m.bit_length() > len(rows) for f,m in new.masks.items()):
            raise ValueError("Saved search mask outside capacity")
        new.classes = [[int(m,16) for m in row] for row in snapshot["classes"]]
        if len(new.classes) != core.config["n_actions"] or any(
                len(row) != 2 or any(m.bit_length() > len(rows) for m in row) for row in new.classes):
            raise ValueError("Invalid saved class masks")
        new.pairs = [_tuples(item) for item in snapshot["pairs"]]
        new.extend = [_tuples(item) for item in snapshot["extend"]]
        new.seen = {_tuples(item) for item in snapshot["seen"]}
        new.best = None if snapshot["best"] is None else _tuples(snapshot["best"])
        if len(new.pool) > core.config["pool_size"] or any(f not in new.masks for f in new.pool):
            raise ValueError("Saved pool outside masks")
        if new.pool != sorted(set(new.pool)) or len(new.pairs) > len(new.pool)*(len(new.pool)-1)//2:
            raise ValueError("Invalid search pool or pairs")
        if new.phase == "masks" and (new.cursor > len(rows) or new.cursor % 8):
            raise ValueError("Index cursor outside work")
        if new.phase == "singles" and new.cursor > len(new.pool):
            raise ValueError("Single cursor outside pool")
        if new.phase == "pairs" and (new.i > len(new.pool) or new.j > max(1,len(new.pool))):
            raise ValueError("Pair cursor outside pool")
        if new.phase == "triples" and (new.i > len(new.extend) or new.cursor >= max(1,len(new.pool))):
            raise ValueError("Triple cursor outside pool")
        if not math.isfinite(new.elapsed) or new.elapsed < 0:
            raise ValueError("Invalid elapsed work time")
        return new


class ReceiptWork:
    def __init__(self, core, action, receipt):
        self.core, self.action, self.receipt = core, action, copy.deepcopy(receipt)
        self.phase, self.intent, self.units = "feedback", None, 0
        self.search = None
        self.fit = None
        self.refinement = None
        self.rows = None

    def _feedback(self):
        if self.receipt["status"] != "observed":
            self.core.finish_evaluation()
            self.phase = "done"
            return
        intents = []
        names = ("_start_trial", "_refresh_candidate", "_consider_refinement")
        previous = {name: self.core.__dict__.get(name) for name in names}
        present = {name: name in self.core.__dict__ for name in names}
        self.core._start_trial = lambda scope, refinement_gain=None: intents.append(
            {"kind":"start", "scope":scope, "gain":refinement_gain})
        self.core._refresh_candidate = lambda: intents.append(
            {"kind":"refresh", "scope":self.core.trial["scope"], "gain":None})
        self.core._consider_refinement = lambda: intents.append(
            {"kind":"refinement", "scope":None, "gain":None}) if not intents else None
        try:
            self.core.learn(self.action, self.receipt["outcome"]["value"])
        finally:
            for name in names:
                if present[name]:
                    setattr(self.core, name, previous[name])
                else:
                    delattr(self.core, name)
        if len(intents) > 1:
            raise RuntimeError("Multiple feedback work intentions")
        if not intents:
            self.phase = "done"
        else:
            self.intent = intents[0]
            self._begin_intent()

    def _begin_intent(self):
        self.rows = rows_of(self.core)
        if self.intent["kind"] == "refinement":
            self.phase = "refinement_policy"
            self.refinement = {"cursor":0, "gains":[], "support":{}}
        elif self.intent["kind"] == "refresh":
            self.search = SearchWork(self.core, self.rows, self.intent["scope"], self.core.attempts)
            self.phase = "search"
        else:
            if sum(task["steps"] > 0 for task in self.core.tasks.values()) == 1:
                self.intent["scope"] = None
            if self.intent["gain"] is None:
                self.search = SearchWork(self.core, self.rows, self.intent["scope"], self.core.attempts+1)
                self.phase = "search"
            else:
                self.phase = "initialize"

    def advance(self):
        if self.phase == "done":
            return False
        if self.phase == "feedback":
            self._feedback()
        elif self.phase == "search":
            self.search.advance()
            if self.search.phase == "done":
                self.phase = "refresh" if self.intent["kind"] == "refresh" else "initialize"
        elif self.phase == "refinement_policy":
            protected = self.core._protected["bank"]
            for route in range(2 ** len(self.core.program)):
                def policy(bank):
                    p = [bank.probability(a, route) for a in range(self.core.config["n_actions"])]
                    return max(range(len(p)), key=p.__getitem__)
                if policy(self.core.active) != policy(protected):
                    self.phase = "done"
                    break
            else:
                self.phase = "refinement_rows"
        elif self.phase == "refinement_rows":
            rows = self.rows
            state = self.refinement
            stop = min(state["cursor"]+8,len(rows))
            for slot, mask, before, coin, action, outcome in rows[state["cursor"]:stop]:
                route = self.core._route(self.core.program, slot, mask, before)
                key = str(route)
                state["support"][key] = state["support"].get(key,0)+1
                state["gains"].append(log_probability(self.core.active.probability(action,route),outcome) -
                    log_probability(self.core._protected["bank"].probability(action,route),outcome))
            state["cursor"] = stop
            if stop == len(rows):
                gain = math.fsum(state["gains"])/len(rows) if rows else 0
                if (len(rows) >= self.core.required_fit_records() and state["support"] and
                        min(state["support"].values()) >= 16 and gain >= REFINEMENT_GAIN):
                    self.intent = {"kind":"start","scope":None,"gain":gain}
                    self.phase = "initialize"
                else:
                    self.phase = "done"
        elif self.phase == "refresh":
            preview, rows, t = self.search.report(), self.rows, self.core.trial
            proposed = preview["program"]
            current = self.core._fit_score(t["program"],rows)
            score = self.core._fit_score(proposed,rows)
            check = {"at":self.core.steps,"n":t["n"],"other_n":t["other_n"],"program":proposed,
                     "current_score":current,"proposed_score":score,
                     **{k:preview[k] for k in ("fit_records","eligible_features","pooled_features","hypotheses_examined")}}
            self.core._validation(self.core.attempts)["refresh_checks"].append(check)
            if proposed is not None and proposed != t["program"] and score is not None and (
                    current is None or score-current >= REFRESH_GAIN):
                self.core._close_unfinished_trial("superseded")
                self.core.next_trial = self.core.steps+1
            self.phase = "done"
        elif self.phase == "initialize":
            rows = self.rows
            program = self.search.report()["program"] if self.intent["gain"] is None else list(self.core.program)
            if program is None:
                self._publish_trial(None)
                self.phase = "done"
            else:
                candidate, control, report = self.core._initialize_banks(program,rows)
                rng = random.Random(0)
                rng.setstate(self.core.rng.getstate())
                self.fit = {"program":program,"candidate":candidate,"control":control,"report":report,
                            "order":list(range(len(rows))),"rng":rng,"epoch":0,"row":0,"bank":0,"gradients":0}
                self.phase = "shuffle"
        elif self.phase == "shuffle":
            self.fit["rng"].shuffle(self.fit["order"])
            self.fit["row"], self.fit["bank"] = 0, 0
            self.phase = "replay"
        elif self.phase == "replay":
            f = self.fit
            row = self.rows[f["order"][f["row"]]]
            slot, mask, before, coin, action, outcome = row
            if f["bank"] == 0:
                f["candidate"].update(action,outcome,self.core._route(f["program"],slot,mask,before))
                f["bank"] = 1
            else:
                f["control"].update(action,outcome,coin)
                f["bank"], f["row"] = 0, f["row"]+1
                if f["row"] == len(f["order"]):
                    f["epoch"] += 1
                    self.phase = "finalize" if f["epoch"] == self.core.config["replay_passes"] else "shuffle"
            f["gradients"] += 1
        elif self.phase == "finalize":
            self._publish_trial(self.fit)
            self.phase = "done"
        else:
            raise ValueError("Unknown receipt work phase")
        self.units += 1
        return True

    def _publish_trial(self, fit):
        core = self.core
        wire.counter(core.attempts+1,"lifetime attempts")
        if len(core.searches) == core.config["max_attempts"]:
            core._compact()
        core.attempts += 1
        core._revision_variance = {name:0.0 for name in COMPARISONS}
        scope, gain = self.intent["scope"], self.intent["gain"]
        rows = self.rows
        if gain is None:
            report = self.search.report()
        else:
            report = {"attempt":core.attempts,"scope":scope,"score_source":"served","at":core.steps,
                      "fit_records":len(rows),"eligible_features":0,"pooled_features":0,
                      "hypotheses_examined":0,"elapsed_seconds":0.0,"program":list(core.program)}
        core.searches.append(report)
        program = report["program"]
        if fit is None:
            core.decisions.append({"attempt":core.attempts,"at":core.steps,"scope":scope,
                                   "program":None,"decision":"unsupported"})
            core.next_trial = core.steps+core.config["cooldown"]
            initialization = None
        else:
            if core._protected is None and core.config["use_structure"] and core.config["bounded_validation_ranges"]:
                core._frozen_reference = {"bank":copy.deepcopy(core.active),"at":core.steps}
            core.rng.setstate(fit["rng"].getstate())
            core.neural_updates = wire.counter(core.neural_updates+fit["gradients"],"neural updates")
            core.candidate, core.control = fit["candidate"], fit["control"]
            core.trial = {"program":program,"scope":scope,"fit_records":len(rows),
                          "started_at":core.steps,"last_progress_at":core.steps,
                          "fit_required_records":core.required_fit_records(),
                          "fit_updates_per_bank":len(rows)*core.config["replay_passes"],
                          "n":0,"relevance":0.0,"improvement":0.0,"other_n":0,
                          "preservation":0.0,"support":[0]*core.active.n_routes}
            initialization = fit["report"]
            rows = [rows[i] for i in fit["order"]]
        mode = "consolidated" if core._protected is not None and core.config["use_structure"] else "plastic"
        report.update(initialization=initialization, validation={
            "horizons":list(core._horizons()),"serve_mode":mode,
            "served_at":core._protected["at"] if mode == "consolidated" else None,
            "reference":core._reference_kind(),"purpose":"confidence" if gain is not None else "structure",
            "refinement_gain":gain,"conditional_null":core._conditional_null(rows) if program is not None and
                core.config["bounded_validation_ranges"] else None,
            "variance_checks":{name:{} for name in COMPARISONS},"refresh_checks":[]})
        report["validation"]["widths"] = core._ranges()

    def checkpoint(self):
        fit = None
        if self.fit is not None:
            fit = {**{k:v for k,v in self.fit.items() if k not in ("candidate","control","rng")},
                   "candidate":self.fit["candidate"].checkpoint(),"control":self.fit["control"].checkpoint(),
                   "rng":self.fit["rng"].getstate()}
        return sealed({"core":self.core.checkpoint(),"action":self.action,"receipt":self.receipt,
                       "phase":self.phase,"intent":self.intent,"units":self.units,
                       "search":None if self.search is None else self.search.checkpoint(),
                       "fit":fit,"refinement":self.refinement})

    @classmethod
    def restore(cls,snapshot):
        data = unsealed(snapshot)
        from .plastic_revision import PlasticRevisionLearner
        core = PlasticRevisionLearner.restore(data["core"])
        new = cls(core,data["action"],wire.receipt(data["receipt"]))
        if set(data) != {"core","action","receipt","phase","intent","units","search","fit","refinement"}:
            raise ValueError("Invalid receipt work fields")
        if data["phase"] not in ("feedback","done","search","refinement_policy","refinement_rows",
                                  "refresh","initialize","shuffle","replay","finalize"):
            raise ValueError("Invalid receipt phase")
        wire.counter(data["units"],"work units")
        if type(data["action"]) is not int or not 0 <= data["action"] < core.config["n_actions"]:
            raise ValueError("Work action outside bank")
        new.phase,new.intent,new.units,new.refinement = data["phase"],data["intent"],data["units"],data["refinement"]
        new.rows = rows_of(core)
        if new.receipt["status"] == "observed":
            outcome = new.receipt["outcome"]
            if outcome["measure"] != "lab.success" or outcome["unit"] != "binary" or type(outcome["value"]) is not int or outcome["value"] not in (0,1):
                raise ValueError("Invalid staged outcome")
        if new.phase == "feedback":
            if core.episode["phase"] != "feedback" or any(data[k] is not None for k in ("intent","search","fit","refinement")) or new.units:
                raise ValueError("Feedback work already advanced")
        elif core.episode["phase"] != "idle":
            raise ValueError("Advanced work has pending feedback")
        if new.phase == "search" and data["search"] is None:
            raise ValueError("Search state absent")
        if new.phase in ("shuffle","replay","finalize") and data["fit"] is None:
            raise ValueError("Replay state absent")
        if new.phase in ("refinement_policy","refinement_rows") and data["refinement"] is None:
            raise ValueError("Refinement state absent")
        if data["intent"] is not None and (type(data["intent"]) is not dict or set(data["intent"]) != {"kind","scope","gain"} or data["intent"]["kind"] not in ("start","refresh","refinement")):
            raise ValueError("Unknown work intent")
        if data["search"] is not None:
            kind = new.intent["kind"]
            attempt = core.attempts if kind == "refresh" else core.attempts+1
            new.search = SearchWork.restore(core,new.rows,new.intent["scope"],attempt,data["search"])
        if data["fit"] is not None:
            fit = data["fit"]
            new.fit = copy.deepcopy(fit)
            new.fit["candidate"] = SharedSpherePredictor.restore(fit["candidate"])
            new.fit["control"] = SharedSpherePredictor.restore(fit["control"])
            new.fit["rng"] = random.Random(0)
            new.fit["rng"].setstate(_tuples(fit["rng"]))
            n = len(new.rows)
            for name in ("candidate","control"):
                bank = new.fit[name]
                if bank.n_actions != core.config["n_actions"] or bank.n_routes != core.active.n_routes or bank.rate != core.config["rate"]:
                    raise ValueError("Partial replay capacity differs")
            if any(type(i) is not int for i in fit["order"]) or sorted(fit["order"]) != list(range(n)):
                raise ValueError("Replay permutation differs")
            for k in ("epoch","row","bank","gradients"):
                wire.counter(fit[k],k)
            if fit["epoch"] > core.config["replay_passes"] or fit["row"] > n or fit["bank"] not in (0,1):
                raise ValueError("Replay cursor outside work")
            for name, expected in (("candidate",(fit["gradients"]+1)//2),("control",fit["gradients"]//2)):
                if sum(map(sum,new.fit[name].counts)) != expected:
                    raise ValueError("Partial bank gradients differ from cursor")
            position = 2*(fit["epoch"]*n+min(fit["row"],n))+fit["bank"]
            if fit["row"] == n:
                position -= 2*n
            if fit["gradients"] != position:
                raise ValueError("Replay position differs from gradients")
        return new


class CooperativeService:
    """Versioned sidecar for the same active adapter, never a second learner."""
    ADAPTER_CLASS = PlasticRevisionAdapter
    WORK_CLASS = ReceiptWork
    WORK_PROTOCOL = PROTOCOL
    WORK_PRIMITIVES = ["eight-row index","one hypothesis","one gradient","shuffle","bounded control"]

    def __init__(self, *, minimum_observations=32, **adapter_options):
        wire.counter(minimum_observations,"minimum observations",minimum=1)
        if minimum_observations > 1024:
            raise ValueError("Coverage threshold exceeds buffer budget")
        self._adapter = self.ADAPTER_CLASS(**adapter_options)
        self._work = None
        self._lock = threading.RLock()
        self.minimum_observations = minimum_observations

    @classmethod
    def from_adapter_checkpoint(cls,snapshot,*,minimum_observations=32):
        """Adopt an active format-8 adapter, including its pending action."""
        new = cls(minimum_observations=minimum_observations)
        new._adapter = cls.ADAPTER_CLASS.restore(snapshot)
        return new

    def submit_observation(self,message):
        with self._lock:
            return self._adapter.submit_observation(message)

    def register_action(self,message,*,executor_id):
        with self._lock:
            return self._adapter.register_action(message,executor_id=executor_id)

    def current_prediction(self):
        with self._lock:
            return self._adapter.current_prediction()

    def capabilities(self):
        with self._lock:
            return {**self._adapter.capabilities(),"work_protocol":self.WORK_PROTOCOL,
                    "work_primitives":list(self.WORK_PRIMITIVES),
                    "coverage":"recent observed labels, not epistemic confidence"}

    def begin_receipt(self,message):
        receipt = wire.receipt(message)
        with self._lock:
            adapter = self._adapter
            completed = adapter._receipts.get(receipt["request_id"])
            if completed is not None:
                if _semantic_receipt(completed["receipt"]) != _semantic_receipt(receipt):
                    raise ValueError("Conflicting completed receipt")
                return {"state":"completed","ack":copy.deepcopy(completed["ack"])}
            if any(v["receipt"]["receipt_id"] == receipt["receipt_id"] for v in adapter._receipts.values()):
                raise ValueError("Receipt id belongs to another action")
            if self._work is not None:
                if _semantic_receipt(self._work.receipt) != _semantic_receipt(receipt):
                    raise ValueError("Another receipt is being processed")
                return self.work_status()
            pending = adapter._pending
            if pending is None or receipt["request_id"] != pending["request_id"] or receipt["source_id"] != pending["executor_id"]:
                raise ValueError("Receipt has no matching designated action")
            learned = receipt["status"] == "observed"
            if learned:
                outcome = receipt["outcome"]
                if outcome["measure"] != "lab.success" or outcome["unit"] != "binary" or type(outcome["value"]) is not int or outcome["value"] not in (0,1):
                    raise ValueError("Outcome outside binary capabilities")
            candidate = adapter._fork_learner(observation=not learned,context=adapter._slots[pending["context_id"]])
            self._work = self.WORK_CLASS(candidate,adapter.actions.index(pending["action_name"]),receipt)
            return self.work_status()

    def work_status(self):
        with self._lock:
            if self._work is None:
                return {"protocol":self.WORK_PROTOCOL,"state":"idle","model_revision":self._adapter._revision}
            return {"protocol":self.WORK_PROTOCOL,"state":"working","phase":self._work.phase,
                    "request_id":self._work.receipt["request_id"],"units":self._work.units,
                    "model_revision":self._adapter._revision}

    def advance(self,max_units=128):
        wire.counter(max_units,"work quota",minimum=1)
        if max_units > 65536:
            raise ValueError("Quota exceeds cooperative budget")
        with self._lock:
            if self._work is None:
                return {**self.work_status(),"consumed_units":0}
            work, consumed = self._work, 0
            while consumed < max_units and work.phase != "done":
                try:
                    work.advance()
                except Exception:
                    # Discard unpublished changes; keep the same execution receipt.
                    # Retrying recomputes private work, never the external action.
                    adapter = self._adapter
                    learned = work.receipt["status"] == "observed"
                    pending = adapter._pending
                    core = adapter._fork_learner(observation=not learned,
                        context=adapter._slots[pending["context_id"]])
                    self._work = self.WORK_CLASS(core,work.action,work.receipt)
                    raise
                consumed += 1
            if work.phase != "done":
                return {**self.work_status(),"consumed_units":consumed}
            adapter, receipt = self._adapter, work.receipt
            pending = adapter._pending
            learned = receipt["status"] == "observed"
            revision = wire.counter(adapter._revision+int(learned),"model revision")
            ack = {"request_id":pending["request_id"],"learned":learned,"model_revision":revision}
            entry = {"request":copy.deepcopy(pending),"receipt":copy.deepcopy(receipt),"ack":ack}
            adapter._learner,adapter._revision = work.core,revision
            adapter._prediction,adapter._pending = None,None
            adapter._receipts[receipt["request_id"]] = entry
            while len(adapter._receipts) > adapter.receipt_window:
                del adapter._receipts[next(iter(adapter._receipts))]
            self._work = None
            return {"protocol":self.WORK_PROTOCOL,"state":"completed","ack":copy.deepcopy(ack),
                    "consumed_units":consumed,"total_units":work.units}

    def submit_receipt(self,message):
        status = self.begin_receipt(message)
        while status["state"] not in ("completed",):
            status = self.advance(128)
        return status["ack"]

    def coverage(self,prediction_id=None):
        with self._lock:
            prediction = self._adapter.current_prediction()
            if prediction is None or (prediction_id is not None and prediction_id != prediction["prediction_id"]):
                raise ValueError("Coverage needs the active prediction")
            core, e = self._adapter._learner,self._adapter._learner.episode
            counts = [[0,0] for _ in self._adapter.actions]
            route = core._route(core.program,e["task"],e["mask"],e["before"]) if core.program else None
            for slot,task in core.tasks.items():
                for mask,before,coin,action,outcome in task["records"]:
                    same = core._route(core.program,slot,mask,before) == route if core.program else coin == e["coin"]
                    if same:
                        counts[action][outcome] += 1
            return {"schema_version":1,"prediction_id":prediction["prediction_id"],
                    "model_revision":self._adapter._revision,"scope":"recent labels in current routing",
                    "minimum_observations":self.minimum_observations,
                    "actions":[{"candidate_id":f"choice.{i}","observations":sum(row),"positive_outcomes":row[1],
                                "coverage_status":"unobserved" if not sum(row) else
                                    "limited" if sum(row) < self.minimum_observations else "observed"}
                               for i,row in enumerate(counts)],
                    "epistemic_interval":None}

    def metrics(self,*,detailed=True):
        with self._lock:
            return {**self._adapter.metrics(detailed=detailed),"work":self.work_status()}

    def checkpoint(self):
        with self._lock:
            return {"format":1,"protocol":self.WORK_PROTOCOL,"minimum_observations":self.minimum_observations,
                    "adapter":self._adapter.checkpoint(),
                    "work":None if self._work is None else self._work.checkpoint()}

    @classmethod
    def restore(cls,snapshot):
        if type(snapshot) is not dict or set(snapshot) != {"format","protocol","minimum_observations","adapter","work"}:
            raise ValueError("Invalid cooperative checkpoint")
        if type(snapshot["format"]) is not int or snapshot["format"] != 1 or snapshot["protocol"] != cls.WORK_PROTOCOL:
            raise ValueError("Unsupported cooperative checkpoint")
        new = cls(minimum_observations=snapshot["minimum_observations"])
        new._adapter = cls.ADAPTER_CLASS.restore(snapshot["adapter"])
        if snapshot["work"] is not None:
            new._work = cls.WORK_CLASS.restore(snapshot["work"])
            pending = new._adapter._pending
            if pending is None or new._work.receipt["request_id"] != pending["request_id"] or new._work.receipt["source_id"] != pending["executor_id"]:
                raise ValueError("Work and pending request differ")
            learned = new._work.receipt["status"] == "observed"
            delta = int(learned and new._work.phase != "feedback")
            if new._work.core.steps != new._adapter._learner.steps+delta:
                raise ValueError("Staged exposure differs from committed model")
            if new._work.action != new._adapter.actions.index(pending["action_name"]):
                raise ValueError("Staged action differs")
        return new
