"""Calibrated, revisable S2 trace experiment; optional wire backend, not a cortex."""
import copy
import math
import random

from .adaptive_trace import AdaptiveTraceLearner, symbol_point
from .shared import SharedSpherePredictor, log_probability
from .spherical import point, distance, unit
from .world import _tuples
from setharkk.contracts import counter, identifier

LOOKS = (128, 512, 2048, 8192)
FLOOR = 1e-6


def fresh_readout():
    return {"rows": [], "sums": [0.0, 0.0, 0.0, 0.0]}


def add_readout(cal, p, y, *, limit=256, remove=False):
    if remove:
        p, y = cal["rows"].pop(0)
        sign = -1
    else:
        if len(cal["rows"]) == limit:
            add_readout(cal, 0, 0, remove=True)
        cal["rows"].append([p, y])
        sign = 1
    for i, value in enumerate((p, p*p, y, p*y)):
        cal["sums"][i] += sign*value


def calibrated(cal, p):
    n = len(cal["rows"])
    if n < 32:
        return p
    sp, spp, sy, spy = cal["sums"]
    base = sy/n
    denominator = spp-2*base*sp+n*base*base
    slope = 1.0 if denominator <= 1e-12 else max(FLOOR, min(1.0, (spy-base*sp)/denominator))
    return max(0.0, min(1.0, base+slope*(p-base)))


def check_readout(cal, limit):
    if type(cal) is not dict or set(cal) != {"rows", "sums"} or type(cal["rows"]) is not list or len(cal["rows"]) > limit:
        raise ValueError("Invalid calibration memory")
    expected = [0.0]*4
    for row in cal["rows"]:
        if type(row) is not list or len(row) != 2 or type(row[0]) not in (int, float) or not math.isfinite(row[0]) or not 0 <= row[0] <= 1 or type(row[1]) is not int or row[1] not in (0, 1):
            raise ValueError("Invalid calibration observation")
        p, y = row
        for i, v in enumerate((p, p*p, y, p*y)):
            expected[i] += v
    if type(cal["sums"]) is not list or len(cal["sums"]) != 4 or any(
            type(v) not in (int, float) or not math.isfinite(v) or abs(v-e) > 1e-8
            for v, e in zip(cal["sums"], expected)):
        raise ValueError("Calibration sufficient statistics differ")


class AdaptiveTraceLearnerV2(AdaptiveTraceLearner):
    IMPLEMENTATION = "first_piece.adaptive-trace-s2.v2"

    def __init__(self, seed=0, *, max_tasks=8, max_symbols=64, calibration_window=256, **options):
        super().__init__(seed, **options)
        if self.config["min_records"] > self.config["window"]:
            raise ValueError("Required fit records exceed retained memory")
        for name, value, cap in (("max_tasks", max_tasks, 8), ("max_symbols", max_symbols, 64),
                                 ("calibration_window", calibration_window, 256)):
            counter(value, name, minimum=32 if name == "calibration_window" else 1)
            if value > cap:
                raise ValueError("Trace budget exceeds validated capacity")
            self.config[name] = value
        self.history = {}
        self.cals = {}
        self.revisions = 0
        self.last_token = None
        self.next_checks = {}

    @property
    def tasks(self):
        return {k: {"steps": v} for k, v in self.contexts.items()}

    @property
    def _symbol_ids(self):
        return {token: i for i, token in enumerate(self.symbols)}

    @property
    def episode(self):
        mask = 0 if self.last_token is None else 1 << self._symbol_ids[self.last_token]
        return {"phase": self.phase, "task": self.context, "mask": mask}

    def receive(self, event):
        # Validate before adding any vocabulary/context state.
        if type(event) is dict and event.get("kind") == "token":
            task, token = counter(event.get("task"), "context"), identifier(event.get("token"), "symbol")
            if task not in self.contexts and len(self.contexts) >= self.config["max_tasks"]:
                raise ValueError("Trace context budget exhausted")
            if token not in self.symbols and len(self.symbols) >= self.config["max_symbols"]:
                raise ValueError("Trace vocabulary budget exhausted")
        result = super().receive(event)
        if event["kind"] == "token":
            self.last_token = event["token"]
        return result

    def finish_evaluation(self):
        super().finish_evaluation()
        self.last_token = None

    def raw_probabilities(self):
        if self.phase != "feedback":
            raise RuntimeError("No pending trace forecast")
        bank = self._served(self._leaf(self.state))
        return [bank.probability(a, 0) for a in range(2)]

    def pending_probabilities(self):
        raw = self.raw_probabilities()
        cal = self.cals.get((self._leaf(self.state), self.context), fresh_readout())
        return [calibrated(cal, p) for p in raw]

    def _remember(self, leaf, state, coin, context, action, outcome, raw):
        limit = self.config["calibration_window"]
        rows = self.history.setdefault(context, [])
        if len(rows) == limit:
            old = rows.pop(0)
            oldleaf = self._leaf(old[0])
            key = (oldleaf, context)
            add_readout(self.cals[key], 0, 0, remove=True)
            if not self.cals[key]["rows"]:
                del self.cals[key]
        rows.append([state, coin, action, outcome])
        cal = self.cals.setdefault((leaf, context), fresh_readout())
        add_readout(cal, raw, outcome, limit=limit)

    def _rebuild_calibration(self):
        # Bounded administrative operation over <= 8*256 past observations.
        self.cals = {}
        for context, rows in self.history.items():
            for state, coin, action, outcome in rows:
                leaf = self._leaf(state)
                cal = self.cals.setdefault((leaf, context), fresh_readout())
                add_readout(cal, self._served(leaf).probability(action, 0), outcome,
                            limit=self.config["calibration_window"])

    def _trial_calibration(self, leaf, centers, candidate, control, kind):
        result = {"candidate": {}, "control": {}}
        for context, rows in self.history.items():
            for state, coin, action, outcome in rows:
                if self._leaf(state) != leaf:
                    continue
                route = 0 if kind == "revision" else min(range(2), key=lambda r: distance(state, centers[r]))
                for name, bank, r in (("candidate", candidate, route), ("control", control, coin)):
                    cal = result[name].setdefault(context, fresh_readout())
                    add_readout(cal, bank.probability(action, r), outcome,
                                limit=self.config["calibration_window"])
        return result

    def _propose(self, leaf):
        from .trace_work import TraceFitWork
        work = TraceFitWork(self, leaf, self._proposal_kind(leaf))
        while work.phase != "done":
            work.advance()

    def _proposal_kind(self, leaf):
        node = self.nodes[leaf]
        if node["protected"] is None:
            return "split"
        rows = node["records"][-self.config["min_records"]:]
        gain = math.fsum(log_probability(node["bank"].probability(a, 0), y)-
                         log_probability(node["protected"].probability(a, 0), y)
                         for _, _, a, y in rows)/max(1, len(rows))
        room = self.leaf_count() < self.config["max_leaves"] and node["depth"] < self.config["max_depth"]
        return "revision" if gain > .02 or not room else "split"

    def _judge(self):
        t = self.trial
        alpha = .05/(self.attempts*(self.attempts+1))
        comparisons = 1 if t["kind"] == "revision" else 2
        radius = 2*math.log(99)*math.sqrt(math.log(2*comparisons*len(LOOKS)/alpha)/(2*t["n"]))
        mean = t["improvement"]/t["n"] if comparisons == 1 else min(t["improvement"], t["relevance"])/t["n"]
        lower = mean-radius
        support = min(t["support"][0]) >= 16 if comparisons == 1 else (
            min(min(row) for row in t["support"]) >= 8 and min(map(sum, t["support"])) >= 16)
        decision = "accept" if lower > .01 and support else (
            "futile" if mean <= .01 else "inconclusive" if t["n"] == LOOKS[-1] else "pending")
        self.decisions.append({"attempt": self.attempts, "at": self.steps, "leaf": t["leaf"],
                              "kind": t["kind"], "n": t["n"], "lower": lower, "mean": mean,
                              "radius": radius, "alpha": alpha, "decision": decision})
        self.decisions = self.decisions[-48:]
        if decision == "pending":
            return
        if decision == "accept":
            parent = self.nodes[t["leaf"]]
            if t["kind"] == "revision":
                parent["protected"] = copy.deepcopy(t["candidate"])
                parent["bank"] = copy.deepcopy(t["candidate"])
                self.revisions += 1
            else:
                ids = [max(self.nodes)+1, max(self.nodes)+2]
                for route, index in enumerate(ids):
                    child = self._node(parent["depth"]+1)
                    child["bank"].points[0] = copy.deepcopy(t["candidate"].points[route])
                    child["bank"].counts[0] = list(t["candidate"].counts[route])
                    child["protected"] = copy.deepcopy(child["bank"])
                    child["records"] = [copy.deepcopy(row) for row in parent["records"] if
                        min(range(2), key=lambda r: distance(row[0], t["centers"][r])) == route]
                    self.nodes[index] = child
                parent["children"], parent["centers"], parent["records"] = ids, t["centers"], []
                self.admissions += 1
                self.next_checks.pop(t["leaf"], None)
        self.trial = None
        if decision == "accept":
            self._rebuild_calibration()
        self.next_trial = self.steps+self.config["cooldown"]

    def learn(self, action, outcome, *, defer=None):
        if self.phase != "feedback":
            raise RuntimeError("No pending trace feedback")
        if type(action) is not int or action not in (0, 1) or type(outcome) is not int or outcome not in (0, 1):
            raise ValueError("Unsupported trace outcome")
        leaf, state, coin, context = self._leaf(self.state), list(self.state), self.coin, self.context
        raw = self.raw_probabilities()[action]
        probability = self.pending_probabilities()[action]
        node = self.nodes[leaf]
        if self.trial is not None and self.trial["leaf"] == leaf:
            t = self.trial
            route = 0 if t["kind"] == "revision" else min(range(2), key=lambda r: distance(state, t["centers"][r]))
            cand_raw = t["candidate"].probability(action, route)
            control_raw = t["control"].probability(action, coin)
            cand_cal = t["cal"]["candidate"].setdefault(context, fresh_readout())
            control_cal = t["cal"]["control"].setdefault(context, fresh_readout())
            proposed = log_probability(calibrated(cand_cal, cand_raw), outcome)
            t["improvement"] += proposed-log_probability(probability, outcome)
            t["relevance"] += proposed-log_probability(calibrated(control_cal, control_raw), outcome)
            t["support"][route][action] += 1
            t["n"] += 1
            add_readout(cand_cal, cand_raw, outcome, limit=self.config["calibration_window"])
            add_readout(control_cal, control_raw, outcome, limit=self.config["calibration_window"])
        self._remember(leaf, state, coin, context, action, outcome, raw)
        node["bank"].update(action, outcome, 0)
        self.neural_updates += 1
        node["records"].append([state, coin, action, outcome])
        if len(node["records"]) > self.config["window"]:
            del node["records"][0]
        self.steps += 1
        self.contexts[context] += 1
        proposal = None
        if self.trial is not None and self.trial["leaf"] == leaf and self.trial["n"] in LOOKS:
            self._judge()
        elif self.trial is None and self.config["adaptive"] and self.steps >= self.next_trial and self.steps >= self.next_checks.get(leaf, 0) and len(node["records"]) >= self.config["min_records"]:
            self.next_checks[leaf] = self.steps+self.config["cooldown"]
            kind = self._proposal_kind(leaf)
            recent = node["records"][-self.config["min_records"]:]
            bank = node["protected"] or node["bank"]
            loss = math.fsum((bank.probability(a, 0)-y)**2 for _, _, a, y in recent)/len(recent)
            possible = kind == "revision" or (self.leaf_count() < self.config["max_leaves"] and node["depth"] < self.config["max_depth"])
            if loss > .18 and possible:
                proposal = (leaf, kind)
        self.finish_evaluation()
        if proposal is not None:
            from .trace_work import TraceFitWork
            job = TraceFitWork(self, *proposal)
            if defer is None:
                while job.phase != "done":
                    job.advance()
            else:
                defer(job)
        return probability

    def metrics(self, *, detailed=True):
        result = super().metrics()
        result.update(implementation=self.IMPLEMENTATION, revisions=self.revisions,
                      total_admissions=self.admissions+self.revisions,
                      calibration_records=sum(len(rows) for rows in self.history.values()),
                      work_horizons=list(LOOKS), calibration="causal positive affine readout")
        if not detailed:
            result.pop("decisions", None)
        return result

    def checkpoint(self):
        data = super().checkpoint()
        data.update(format=2, revisions=self.revisions, last_token=self.last_token,
                    next_checks={str(k): v for k, v in self.next_checks.items()},
                    history={str(k): copy.deepcopy(v) for k, v in self.history.items()},
                    cals={f"{leaf}:{context}": copy.deepcopy(v) for (leaf, context), v in self.cals.items()})
        return data

    @classmethod
    def restore(cls,data):
        expected = {"format","implementation","config","rng","nodes","trial","phase","state","context","coin",
                    "symbols","contexts","steps","attempts","admissions","neural_updates","fit_records_total","next_trial","decisions","history","cals","revisions","last_token","next_checks"}
        if type(data) is not dict or set(data) != expected or type(data["format"]) is not int or data["format"] != 2 or data["implementation"] != cls.IMPLEMENTATION:
            raise ValueError("Invalid adaptive trace checkpoint")
        new = cls(**data["config"])
        new.rng.setstate(_tuples(data["rng"]))
        for k in ("steps","attempts","admissions","neural_updates","fit_records_total","next_trial","revisions"):
            setattr(new,k,counter(data[k],k))
        if new.neural_updates != new.steps+2*new.config["replay_passes"]*new.fit_records_total:
            raise ValueError("Trace gradients differ from exposure and replay")
        if not new.attempts*new.config["min_records"] <= new.fit_records_total <= new.attempts*new.config["window"]:
            raise ValueError("Trace fit records differ from attempts")
        new.nodes = {}
        for key,item in data["nodes"].items():
            if type(key) is not str or not key.isdecimal() or str(int(key)) != key or set(item) != {"depth","children","centers","bank","protected","records"}:
                raise ValueError("Invalid trace node")
            node = copy.deepcopy(item)
            node["bank"] = SharedSpherePredictor.restore(item["bank"])
            node["protected"] = None if item["protected"] is None else SharedSpherePredictor.restore(item["protected"])
            for bank in (node["bank"],node["protected"]):
                if bank is not None and (bank.n_routes != 2 or bank.n_actions != 2 or bank.rate != new.config["rate"]):
                    raise ValueError("Trace bank capacity differs")
            counter(node["depth"],"node depth")
            if node["depth"] > new.config["max_depth"] or len(node["records"]) > new.config["window"]:
                raise ValueError("Trace memory exceeds budget")
            for row in node["records"]:
                if type(row) is not list or len(row) != 4 or any(type(v) is not int or v not in (0,1) for v in row[1:]):
                    raise ValueError("Invalid trace record")
                point(row[0])
            new.nodes[int(key)] = node
        if 0 not in new.nodes or new.nodes[0]["depth"] != 0 or new.leaf_count() > new.config["max_leaves"]:
            raise ValueError("Invalid trace root or leaf budget")
        reached = set()
        def visit(index,depth):
            if index in reached or index not in new.nodes:
                raise ValueError("Trace tree cycle or missing child")
            reached.add(index)
            node = new.nodes[index]
            if node["depth"] != depth:
                raise ValueError("Trace node depth differs")
            if node["children"] is None:
                if node["centers"] is not None:
                    raise ValueError("Leaf has branch centers")
            else:
                if type(node["children"]) is not list or len(node["children"]) != 2 or any(type(v) is not int for v in node["children"]) or len(node["centers"]) != 2 or node["records"]:
                    raise ValueError("Invalid binary trace branch")
                for center in node["centers"]:
                    point(center)
                for child in node["children"]:
                    visit(child,depth+1)
        visit(0,0)
        if reached != set(new.nodes) or len(new.nodes) != 2*new.admissions+1:
            raise ValueError("Trace topology differs from admissions")
        new.phase,new.state,new.context,new.coin = data["phase"],point(data["state"]),data["context"],data["coin"]
        if new.phase not in ("idle","tokens","feedback"):
            raise ValueError("Invalid trace episode phase")
        if any(type(k) is not str or not k.isdecimal() or str(int(k)) != k for k in data["contexts"]):
            raise ValueError("Noncanonical trace context")
        new.contexts = {int(k):counter(v,"context exposure") for k,v in data["contexts"].items()}
        if len(new.contexts) > new.config["max_tasks"] or sum(new.contexts.values()) != new.steps:
            raise ValueError("Trace contexts and exposure differ")
        if new.phase == "idle":
            if new.context is not None or new.coin is not None:
                raise ValueError("Idle trace has context")
        elif new.context not in new.contexts or new.coin not in (0,1):
            raise ValueError("Invalid active trace context")
        new.symbols = copy.deepcopy(data["symbols"])
        if len(new.symbols) > new.config["max_symbols"] or any(symbol_point(k) != v for k,v in new.symbols.items()):
            raise ValueError("Trace observation codes differ")
        new.trial = None
        if data["trial"] is not None:
            new.trial = copy.deepcopy(data["trial"])
            expected_trial = {"kind","leaf","centers","candidate","control","reference","cal","n","improvement","relevance","support","started_at","fit_records"}
            if set(new.trial) != expected_trial or new.trial["kind"] not in ("split", "revision"):
                raise ValueError("Invalid trace trial fields")
            for name in ("candidate","control","reference"):
                new.trial[name] = SharedSpherePredictor.restore(data["trial"][name])
            if new.trial["leaf"] not in new.nodes or new.nodes[new.trial["leaf"]]["children"] is not None:
                raise ValueError("Trial on absent leaf")
            for name in ("candidate","control","reference"):
                bank = new.trial[name]
                if bank.n_actions != 2 or bank.n_routes != 2 or bank.rate != new.config["rate"]:
                    raise ValueError("Trial bank differs")
            for name in ("candidate","control"):
                if sum(map(sum,new.trial[name].counts)) != new.trial["fit_records"]*new.config["replay_passes"]:
                    raise ValueError("Frozen trial bank counts differ")
            for name in ("fit_records", "started_at"):
                counter(new.trial[name], name)
            if not new.config["min_records"] <= new.trial["fit_records"] <= new.config["window"]:
                raise ValueError("Trial replay exceeds retained budget")
            support = new.trial["support"]
            if type(support) is not list or len(support) != 2 or any(type(row) is not list or len(row) != 2 for row in support):
                raise ValueError("Invalid trial support shape")
            for row in support:
                for value in row:
                    counter(value, "prospective action support")
            counter(new.trial["n"],"trace trial exposure")
            if new.trial["n"] >= LOOKS[-1] or sum(map(sum,new.trial["support"])) != new.trial["n"]:
                raise ValueError("Trace trial exposure differs")
            if len(new.trial["centers"]) != 2 or new.trial["started_at"] > new.steps or new.trial["n"] > new.steps-new.trial["started_at"]:
                raise ValueError("Invalid trace validation exposure")
            for name in ("improvement", "relevance"):
                value = new.trial[name]
                if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > new.trial["n"]*math.log(99)+1e-8:
                    raise ValueError("Invalid prospective gain")
            if new.trial["kind"] == "revision" and (any(new.trial["support"][1]) or new.nodes[new.trial["leaf"]]["protected"] is None):
                raise ValueError("Revision has branch support")
            if set(new.trial["cal"]) != {"candidate", "control"}:
                raise ValueError("Invalid trial calibration")
            for name in ("candidate", "control"):
                converted = {}
                for key, cal in new.trial["cal"][name].items():
                    context = int(key)
                    if str(context) != str(key) or context not in new.contexts:
                        raise ValueError("Invalid trial calibration context")
                    check_readout(cal, new.config["calibration_window"])
                    converted[context] = cal
                new.trial["cal"][name] = converted
            for center in new.trial["centers"]:
                point(center)
        new.decisions = copy.deepcopy(data["decisions"])
        if len(new.decisions) > 48 or new.admissions+new.revisions > new.attempts:
            raise ValueError("Trace decision ledger differs")
        new.next_checks = {}
        for key, value in data["next_checks"].items():
            index = int(key)
            if str(index) != key or index not in new.nodes or new.nodes[index]["children"] is not None:
                raise ValueError("Invalid leaf check cooldown")
            new.next_checks[index] = counter(value, "leaf check time")
        new.last_token = data["last_token"]
        if (new.phase == "idle") != (new.last_token is None) or (new.last_token is not None and new.last_token not in new.symbols):
            raise ValueError("Invalid last trace observation")
        new.history = {}
        for key, rows in data["history"].items():
            context = int(key)
            if str(context) != key or context not in new.contexts or type(rows) is not list or len(rows) > new.config["calibration_window"] or len(rows) > new.contexts[context]:
                raise ValueError("Invalid calibration history")
            for row in rows:
                if type(row) is not list or len(row) != 4 or any(type(v) is not int or v not in (0,1) for v in row[1:]):
                    raise ValueError("Invalid calibration trace")
                point(row[0])
            new.history[context] = copy.deepcopy(rows)
        expected = {}
        for context, rows in new.history.items():
            for state, coin, action, outcome in rows:
                expected.setdefault((new._leaf(state), context), []).append(outcome)
        new.cals = {}
        for key, cal in data["cals"].items():
            parts = key.split(":")
            if len(parts) != 2 or any(not p.isdecimal() or str(int(p)) != p for p in parts):
                raise ValueError("Invalid calibration key")
            pair = tuple(map(int, parts))
            check_readout(cal, new.config["calibration_window"])
            if pair not in expected or [row[1] for row in cal["rows"]] != expected[pair]:
                raise ValueError("Calibration differs from actual labelled history")
            new.cals[pair] = copy.deepcopy(cal)
        if set(new.cals) != set(expected) or sum(map(len, new.history.values())) != sum(min(n, new.config["calibration_window"]) for n in new.contexts.values()):
            raise ValueError("Calibration history coverage differs")
        return new
