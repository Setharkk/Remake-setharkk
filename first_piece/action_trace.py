"""Action-count configurable trace learner with intrinsic S2 parameters."""
import copy
import math
import random

from setharkk.contracts import counter, identifier
from .adaptive_trace import symbol_point
from .adaptive_trace_v2 import AdaptiveTraceLearnerV2, fresh_readout, calibrated, add_readout, check_readout, LOOKS
from .action_bank import ActionSpherePredictor
from .shared import log_probability
from .spherical import SpherePredictor, point, unit, distance
from .world import _tuples

LAMBDAS = tuple(2.0**k/64 for k in range(-4,12))


def configuration(seed=0, *, n_actions=2, adaptive=True, max_leaves=8, max_depth=4,
                  window=None, min_records=None, cooldown=256, replay_passes=4, rate=.03,
                  max_tasks=8, max_symbols=64, calibration_window=None,
                  point_budget=65536, record_budget=131072, horizon_scale=None):
    counter(seed, "seed")
    counter(n_actions, "action count", minimum=2)
    counter(point_budget, "point budget", minimum=1)
    counter(record_budget, "record budget", minimum=1)
    if type(adaptive) is not bool:
        raise ValueError("Invalid adaptive policy")
    limits = {"max_leaves":(max_leaves,1,8), "max_depth":(max_depth,1,4),
              "cooldown":(cooldown,128,1024), "replay_passes":(replay_passes,1,4),
              "max_tasks":(max_tasks,1,8), "max_symbols":(max_symbols,1,64)}
    for name, (value, low, high) in limits.items():
        counter(value,name,minimum=low)
        if value > high:
            raise ValueError("Trace structural budget exceeds validated range")
    window = 128*n_actions if window is None else window
    min_records = 64*n_actions if min_records is None else min_records
    calibration_window = max(256,64*n_actions) if calibration_window is None else calibration_window
    horizon_scale = (n_actions+1)//2 if horizon_scale is None else horizon_scale
    for name, value, low in (("window",window,128), ("min_records",min_records,128),
                            ("calibration_window",calibration_window,32), ("horizon_scale",horizon_scale,1)):
        counter(value,name,minimum=low)
    if min_records > window or min_records < 16*n_actions:
        raise ValueError("Fit memory cannot supply eight labels per action and branch")
    points = n_actions*(8*max_leaves+2)+2*max_leaves
    records = (max_leaves+3)*window+4*max_tasks*calibration_window
    if points > point_budget or records > record_budget:
        raise ValueError("Requested action catalogue exceeds resource budgets")
    counter(LOOKS[-1]*horizon_scale, "largest validation horizon", minimum=1)
    SpherePredictor(rate)
    return {"seed":seed, "n_actions":n_actions, "adaptive":adaptive, "rate":rate,
            **{name: spec[0] for name,spec in limits.items()},
            "window":window, "min_records":min_records, "calibration_window":calibration_window,
            "point_budget":point_budget, "record_budget":record_budget, "horizon_scale":horizon_scale}


def gain_width(p, q):
    gains = [log_probability(p,y)-log_probability(q,y) for y in (0,1)]
    return abs(gains[1]-gains[0])


class ActionTraceLearner(AdaptiveTraceLearnerV2):
    IMPLEMENTATION = "first_piece.action-trace-s2.v3"

    def __init__(self, seed=0, **options):
        self.config = configuration(seed, **options)
        self.rng = random.Random(seed)
        self.nodes = {0:self._node(0)}
        self.trial, self.phase = None, "idle"
        self.state, self.context, self.coin = unit([1,0,.2]), None, None
        self.symbols, self.contexts = {}, {}
        self.steps = self.attempts = self.admissions = self.neural_updates = self.fit_records_total = 0
        self.next_trial = self.config["min_records"]
        self.decisions, self.history, self.cals = [], {}, {}
        self.revisions, self.last_token, self.next_checks = 0, None, {}

    def _bank(self):
        return ActionSpherePredictor(self.config["rate"], n_actions=self.config["n_actions"],
                                    n_routes=2, point_budget=self.config["point_budget"])

    def horizons(self):
        return tuple(n*self.config["horizon_scale"] for n in LOOKS)

    def raw_probabilities(self):
        if self.phase != "feedback":
            raise RuntimeError("No pending trace forecast")
        bank = self._served(self._leaf(self.state))
        return [bank.probability(a,0) for a in range(self.config["n_actions"])]

    def _propose(self, leaf):
        from .action_work import ActionFitWork
        work = ActionFitWork(self, leaf, self._proposal_kind(leaf))
        while work.phase != "done":
            work.advance()

    def _radius(self, comparison):
        t = self.trial
        comparisons = 1 if t["kind"] == "revision" else 2
        alpha = .05/(self.attempts*(self.attempts+1))
        if t["validation"] == "legacy":
            return 2*math.log(99)*math.sqrt(math.log(2*comparisons*len(LOOKS)/alpha)/(2*t["n"]))
        penalty = math.log(4*comparisons*len(LOOKS)*len(LAMBDAS)/alpha)
        width = t["width_squares"][comparison]
        return min((penalty/lam+lam*width/8)/t["n"] for lam in LAMBDAS)

    def _revision_signal(self, leaf):
        node = self.nodes[leaf]
        if node["protected"] is None:
            return False
        counts = [[0,0] for _ in range(self.config["n_actions"])]
        for state,coin,action,outcome in node["records"][-self.config["min_records"]:]:
            counts[action][0] += 1
            counts[action][1] += outcome
        for action,(n,positive) in enumerate(counts):
            if n >= 8:
                old = node["protected"].probability(action,0)
                if (old >= .75 and positive/n <= .25) or (old <= .25 and positive/n >= .75):
                    return True
        return False

    def _proposal_kind(self, leaf):
        node = self.nodes[leaf]
        if node["protected"] is None:
            return "split"
        if self._revision_signal(leaf):
            return "revision"
        room = self.leaf_count() < self.config["max_leaves"] and node["depth"] < self.config["max_depth"]
        return "split" if room else "revision"

    def _polarity_supported(self):
        t = self.trial
        if t["kind"] != "revision" or t["validation"] == "legacy":
            return True
        if not t["flips"]:
            return False
        alpha = .05/(self.attempts*(self.attempts+1))
        penalty = math.log(4*len(t["flips"])*len(LOOKS)/alpha)
        for action,direction in t["flips"]:
            n = t["support"][0][action]
            if not n:
                return False
            mean = t["outcome_support"][0][action]/n
            radius = math.sqrt(penalty/(2*n))
            if (direction == 1 and mean-radius <= .6) or (direction == -1 and mean+radius >= .4):
                return False
        return True

    def _judge(self):
        t = self.trial
        alpha = .05/(self.attempts*(self.attempts+1))
        comparisons = 1 if t["kind"] == "revision" else 2
        names = ("improvement",) if comparisons == 1 else ("improvement","relevance")
        radius = max(self._radius(name) for name in names)
        minimum_gain = .01*2/self.config["n_actions"]
        mean = t["improvement"]/t["n"] if comparisons == 1 else min(t["improvement"], t["relevance"])/t["n"]
        lower = mean-radius
        support = min(t["support"][0]) >= 16 if comparisons == 1 else (
            min(min(row) for row in t["support"]) >= 8 and min(map(sum, t["support"])) >= 16)
        decision = "accept" if lower > minimum_gain and support and self._polarity_supported() else (
            "futile" if mean <= minimum_gain else "inconclusive" if t["n"] == self.horizons()[-1] else "pending")
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
        if type(action) is not int or not 0 <= action < self.config["n_actions"] or type(outcome) is not int or outcome not in (0, 1):
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
            cand_p, control_p = calibrated(cand_cal,cand_raw), calibrated(control_cal,control_raw)
            # Both hypothetical outcomes are evaluated before consuming this label.
            t["width_squares"]["improvement"] += gain_width(cand_p,probability)**2
            t["width_squares"]["relevance"] += gain_width(cand_p,control_p)**2
            proposed = log_probability(cand_p, outcome)
            t["improvement"] += proposed-log_probability(probability, outcome)
            t["relevance"] += proposed-log_probability(calibrated(control_cal, control_raw), outcome)
            t["support"][route][action] += 1
            t["outcome_support"][route][action] += outcome
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
        if self.trial is not None and self.trial["leaf"] == leaf and self.trial["n"] in self.horizons():
            self._judge()
        elif self.trial is None and self.config["adaptive"] and self.steps >= self.next_trial and self.steps >= self.next_checks.get(leaf, 0) and len(node["records"]) >= self.config["min_records"]:
            self.next_checks[leaf] = self.steps+self.config["cooldown"]
            kind = self._proposal_kind(leaf)
            recent = node["records"][-self.config["min_records"]:]
            bank = node["protected"] or node["bank"]
            loss = math.fsum((bank.probability(a, 0)-y)**2 for _, _, a, y in recent)/len(recent)
            possible = kind == "revision" or (self.leaf_count() < self.config["max_leaves"] and node["depth"] < self.config["max_depth"])
            if loss > .18*2/self.config["n_actions"] and possible and (kind != "revision" or self._revision_signal(leaf)):
                proposal = (leaf, kind)
        self.finish_evaluation()
        if proposal is not None:
            from .action_work import ActionFitWork
            job = ActionFitWork(self, *proposal)
            if defer is None:
                while job.phase != "done":
                    job.advance()
            else:
                defer(job)
        return probability

    def metrics(self, *, detailed=True):
        result = super().metrics(detailed=detailed)
        points = sum(node["bank"].n_actions*node["bank"].n_routes +
                     (0 if node["protected"] is None else node["protected"].n_actions*node["protected"].n_routes) +
                     (0 if node["centers"] is None else len(node["centers"])) for node in self.nodes.values())
        if self.trial is not None:
            points += sum(self.trial[name].n_actions*self.trial[name].n_routes
                          for name in ("candidate","control","reference"))+2
        c = self.config
        result.update(n_actions=c["n_actions"], allocated_s2_points=points,
                      work_horizons=list(self.horizons()),
                      reserved_s2_points=c["n_actions"]*(8*c["max_leaves"]+2)+2*c["max_leaves"],
                      reserved_record_slots=(c["max_leaves"]+3)*c["window"]+4*c["max_tasks"]*c["calibration_window"],
                      point_budget=c["point_budget"], record_budget=c["record_budget"],
                      minimum_gain=.01*2/c["n_actions"], brier_trigger=.18*2/c["n_actions"],
                      validation="predictable gain widths with declared exponential grid")
        return result

    def checkpoint(self):
        return {**super().checkpoint(), "format":3}

    @classmethod
    def restore(cls,data):
        expected = {"format","implementation","config","rng","nodes","trial","phase","state","context","coin",
                    "symbols","contexts","steps","attempts","admissions","neural_updates","fit_records_total","next_trial","decisions","history","cals","revisions","last_token","next_checks"}
        if type(data) is not dict or set(data) != expected or type(data["format"]) is not int or data["format"] != 3 or data["implementation"] != cls.IMPLEMENTATION:
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
            node["bank"] = ActionSpherePredictor.restore(item["bank"])
            node["protected"] = None if item["protected"] is None else ActionSpherePredictor.restore(item["protected"])
            for bank in (node["bank"],node["protected"]):
                if bank is not None and (bank.n_routes != 2 or bank.n_actions != new.config["n_actions"] or bank.rate != new.config["rate"] or bank.point_budget != new.config["point_budget"]):
                    raise ValueError("Trace bank capacity differs")
            counter(node["depth"],"node depth")
            if node["depth"] > new.config["max_depth"] or len(node["records"]) > new.config["window"]:
                raise ValueError("Trace memory exceeds budget")
            for row in node["records"]:
                if type(row) is not list or len(row) != 4 or type(row[1]) is not int or row[1] not in (0,1) or type(row[2]) is not int or not 0 <= row[2] < new.config["n_actions"] or type(row[3]) is not int or row[3] not in (0,1):
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
            expected_trial = {"kind","leaf","centers","candidate","control","reference","cal","n","improvement","relevance","support","started_at","fit_records","validation","width_squares","flips","outcome_support"}
            if set(new.trial) != expected_trial or new.trial["kind"] not in ("split", "revision"):
                raise ValueError("Invalid trace trial fields")
            if new.trial["validation"] not in ("widths","legacy") or (new.trial["validation"] == "legacy" and new.config["n_actions"] != 2):
                raise ValueError("Invalid validation policy")
            widths = new.trial["width_squares"]
            if type(widths) is not dict or set(widths) != {"improvement","relevance"}:
                raise ValueError("Invalid predictable width ledger")
            for value in widths.values():
                if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= new.trial["n"]*(2*math.log(99))**2+1e-8:
                    raise ValueError("Invalid accumulated gain width")
            for name in ("candidate","control","reference"):
                new.trial[name] = ActionSpherePredictor.restore(data["trial"][name])
            if new.trial["leaf"] not in new.nodes or new.nodes[new.trial["leaf"]]["children"] is not None:
                raise ValueError("Trial on absent leaf")
            for name in ("candidate","control","reference"):
                bank = new.trial[name]
                if bank.n_actions != new.config["n_actions"] or bank.n_routes != 2 or bank.rate != new.config["rate"] or bank.point_budget != new.config["point_budget"]:
                    raise ValueError("Trial bank differs")
            for name in ("candidate","control"):
                if sum(map(sum,new.trial[name].counts)) != new.trial["fit_records"]*new.config["replay_passes"]:
                    raise ValueError("Frozen trial bank counts differ")
            for name in ("fit_records", "started_at"):
                counter(new.trial[name], name)
            if not new.config["min_records"] <= new.trial["fit_records"] <= new.config["window"]:
                raise ValueError("Trial replay exceeds retained budget")
            support = new.trial["support"]
            if type(support) is not list or len(support) != 2 or any(type(row) is not list or len(row) != new.config["n_actions"] for row in support):
                raise ValueError("Invalid trial support shape")
            positives = new.trial["outcome_support"]
            if type(positives) is not list or len(positives) != 2 or any(type(row) is not list or len(row) != new.config["n_actions"] for row in positives):
                raise ValueError("Invalid future outcome support")
            for counts, successes in zip(support,positives):
                for n,y in zip(counts,successes):
                    counter(n,"future action observations")
                    counter(y,"future positive outcomes")
                    if y > n:
                        raise ValueError("Positive support exceeds observations")
            flips = new.trial["flips"]
            if type(flips) is not list or len(flips) > new.config["n_actions"]:
                raise ValueError("Invalid directional action set")
            seen_actions = set()
            for pair in flips:
                if type(pair) is not list or len(pair) != 2 or type(pair[0]) is not int or not 0 <= pair[0] < new.config["n_actions"] or pair[0] in seen_actions or type(pair[1]) is not int or pair[1] not in (-1,1):
                    raise ValueError("Invalid directional action")
                seen_actions.add(pair[0])
            for row in support:
                for value in row:
                    counter(value, "prospective action support")
            counter(new.trial["n"],"trace trial exposure")
            if new.trial["n"] >= new.horizons()[-1] or sum(map(sum,new.trial["support"])) != new.trial["n"]:
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
                if type(row) is not list or len(row) != 4 or type(row[1]) is not int or row[1] not in (0,1) or type(row[2]) is not int or not 0 <= row[2] < new.config["n_actions"] or type(row[3]) is not int or row[3] not in (0,1):
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

    @classmethod
    def from_v2(cls, snapshot, *, point_budget=65536, record_budget=131072):
        old = AdaptiveTraceLearnerV2.restore(snapshot)
        data = old.checkpoint()
        data["format"], data["implementation"] = 3, cls.IMPLEMENTATION
        data["config"].update(n_actions=2, point_budget=point_budget,
                              record_budget=record_budget, horizon_scale=1)
        def convert(bank):
            return None if bank is None else ActionSpherePredictor.from_v2(
                bank, point_budget=point_budget).checkpoint()
        for node in data["nodes"].values():
            for name in ("bank","protected"):
                node[name] = convert(node[name])
        if data["trial"] is not None:
            t = data["trial"]
            for name in ("candidate","control","reference"):
                t[name] = convert(t[name])
            t["validation"], t["width_squares"] = "legacy", {"improvement":0.0,"relevance":0.0}
            t["flips"], t["outcome_support"] = [], [[0,0],[0,0]]
        return cls.restore(data)
