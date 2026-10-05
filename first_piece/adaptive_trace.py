"""Experimental data-driven S2 state partition; not an autonomous cortex.

The recurrent encoder and binary partition operator are supplied. No token
count, repetition predicate or target identity is fed into the learner.
"""
import copy
import math
import random

from .plastic_revision import spherical_mean
from .shared import SharedSpherePredictor, log_probability
from .spherical import unit, point, distance, exp_map, log_map
from .world import _tuples
from setharkk.contracts import counter, identifier

LOOKS = (128, 512, 2048)


def symbol_point(symbol):
    # FNV-1a over UTF-8; a fixed, label-free observation code on one hemisphere.
    value = 2166136261
    for byte in symbol.encode("utf-8"):
        value = ((value ^ byte)*16777619) & 0xffffffff
    return unit([1.0, (value & 65535)/65535-.5, (value >> 16)/65535-.5])


def encoded_state(events):
    state = unit([1.0, 0.0, .2])
    for event in events:
        if event["kind"] == "token":
            target = symbol_point(event["token"])
            state = exp_map(state, [0.75*v for v in log_map(state,target)])
    return state


class AdaptiveTraceLearner:
    IMPLEMENTATION = "first_piece.adaptive-trace-experiment.v1"
    def __init__(self, seed=0, *, adaptive=True, max_leaves=8, max_depth=4,
                 window=256, min_records=128, cooldown=256, replay_passes=4, rate=.03):
        counter(seed,"seed")
        if type(adaptive) is not bool:
            raise ValueError("Invalid adaptive policy")
        limits = {"max_leaves":(max_leaves,1,8),"max_depth":(max_depth,1,4),
                  "window":(window,128,256),"min_records":(min_records,128,256),
                  "cooldown":(cooldown,128,1024),"replay_passes":(replay_passes,1,4)}
        for name,(value,lo,hi) in limits.items():
            counter(value,name,minimum=lo)
            if value > hi:
                raise ValueError("Budget exceeds measured experimental capacity")
        self.config = {"seed":seed,"adaptive":adaptive,"rate":rate,
                       **{name:value[0] for name,value in limits.items()}}
        self.rng = random.Random(seed)
        self.nodes = {0:self._node(0)}
        self.trial = None
        self.phase = "idle"
        self.state = unit([1,0,.2])
        self.context = None
        self.coin = None
        self.symbols = {}
        self.contexts = {}
        self.steps = self.attempts = self.admissions = self.neural_updates = self.fit_records_total = 0
        self.next_trial = min_records
        self.decisions = []

    def _bank(self):
        return SharedSpherePredictor(self.config["rate"],n_actions=2,n_routes=2)

    def _node(self,depth):
        return {"depth":depth,"children":None,"centers":None,
                "bank":self._bank(),"protected":None,"records":[]}

    def _leaf(self,state):
        node = 0
        while self.nodes[node]["children"] is not None:
            item = self.nodes[node]
            route = min(range(2),key=lambda r:distance(state,item["centers"][r]))
            node = item["children"][route]
        return node

    def receive(self,event):
        if type(event) is not dict or event.get("kind") not in ("token","surface"):
            raise ValueError("Unsupported trace event")
        kind = event["kind"]
        if set(event) != ({"kind","token","task"} if kind == "token" else {"kind","surface","task"}):
            raise ValueError("Unexpected trace event fields")
        task = counter(event["task"],"context")
        if self.phase == "feedback" or (self.phase == "tokens" and task != self.context):
            raise RuntimeError("Resolve the active episode")
        if kind == "token":
            token = identifier(event["token"],"symbol")
            if token not in self.symbols and len(self.symbols) >= self.config.get("max_symbols",64):
                raise ValueError("Experimental vocabulary budget exhausted")
        elif event["surface"] != "sealed" or self.phase != "tokens":
            raise ValueError("Unsupported episode end")
        if self.phase == "idle":
            if kind != "token":
                raise RuntimeError("Observe before end")
            if task not in self.contexts and len(self.contexts) >= self.config.get("max_tasks",8):
                raise ValueError("Experimental context budget exhausted")
            self.contexts.setdefault(task,0)
            self.context,self.coin,self.phase = task,self.rng.randrange(2),"tokens"
            self.state = unit([1,0,.2])
        if kind == "token":
            self.symbols.setdefault(token,symbol_point(token))
            self.state = exp_map(self.state,[.75*v for v in log_map(self.state,self.symbols[token])])
            return None
        self.phase = "feedback"
        return self.pending_probabilities()

    def _served(self,leaf):
        if self.trial is not None and self.trial["leaf"] == leaf:
            return self.trial["reference"]
        return self.nodes[leaf]["protected"] or self.nodes[leaf]["bank"]

    def pending_probabilities(self):
        if self.phase != "feedback":
            raise RuntimeError("No pending trace forecast")
        bank = self._served(self._leaf(self.state))
        return [bank.probability(a,0) for a in range(2)]

    def finish_evaluation(self):
        if self.phase != "feedback":
            raise RuntimeError("No completed trace")
        self.phase,self.context,self.coin = "idle",None,None
        self.state = unit([1,0,.2])

    def _propose(self,leaf):
        node, rows = self.nodes[leaf], self.nodes[leaf]["records"]
        centers = [list(rows[0][0])]
        centers.append(list(max(rows,key=lambda row:distance(row[0],centers[0]))[0]))
        centers[0] = list(max(rows,key=lambda row:distance(row[0],centers[1]))[0])
        if distance(*centers) < 1e-6:
            self.next_trial = self.steps+self.config["cooldown"]
            return
        for _ in range(8):
            groups = [[],[]]
            for state,coin,action,outcome in rows:
                route = min(range(2),key=lambda r:distance(state,centers[r]))
                groups[route].append(state)
            if any(len(group) < 16 for group in groups):
                self.next_trial = self.steps+self.config["cooldown"]
                return
            centers = [spherical_mean(group,[1]*len(group))[0] for group in groups]
        counts = [[0,0] for _ in range(2)]
        for state,coin,action,outcome in rows:
            route = min(range(2),key=lambda r:distance(state,centers[r]))
            counts[route][action] += 1
        if min(min(row) for row in counts) < 8:
            self.next_trial = self.steps+self.config["cooldown"]
            return
        candidate, control = self._bank(),self._bank()
        replay = list(rows)
        for _ in range(self.config["replay_passes"]):
            self.rng.shuffle(replay)
            for state,coin,action,outcome in replay:
                route = min(range(2),key=lambda r:distance(state,centers[r]))
                candidate.update(action,outcome,route)
                control.update(action,outcome,coin)
        self.attempts += 1
        self.fit_records_total += len(rows)
        self.neural_updates += 2*len(rows)*self.config["replay_passes"]
        self.trial = {"leaf":leaf,"centers":centers,"candidate":candidate,"control":control,
                      "reference":copy.deepcopy(self._served(leaf)),"n":0,
                      "improvement":0.0,"relevance":0.0,"support":[[0,0],[0,0]],
                      "started_at":self.steps,"fit_records":len(rows)}

    def _judge(self):
        t = self.trial
        alpha = .05/(self.attempts*(self.attempts+1))
        radius = 2*math.log(99)*math.sqrt(math.log(2*2*len(LOOKS)/alpha)/(2*t["n"]))
        lower = min(t["improvement"],t["relevance"])/t["n"]-radius
        support = min(min(row) for row in t["support"]) >= 8 and min(map(sum,t["support"])) >= 16
        mean = min(t["improvement"],t["relevance"])/t["n"]
        decision = "accept" if lower > .01 and support else (
            "futile" if mean <= .01 else "inconclusive" if t["n"] == LOOKS[-1] else "pending")
        self.decisions.append({"attempt":self.attempts,"at":self.steps,"leaf":t["leaf"],
                              "n":t["n"],"lower":lower,"mean":mean,"radius":radius,
                              "alpha":alpha,"decision":decision})
        # Bound the detailed journal without resetting lifetime risk.
        self.decisions = self.decisions[-48:]
        if decision == "pending":
            return
        if decision == "accept":
            parent = self.nodes[t["leaf"]]
            ids = [max(self.nodes)+1,max(self.nodes)+2]
            for route,index in enumerate(ids):
                child = self._node(parent["depth"]+1)
                child["bank"].points[0] = copy.deepcopy(t["candidate"].points[route])
                child["bank"].counts[0] = list(t["candidate"].counts[route])
                child["protected"] = copy.deepcopy(child["bank"])
                child["records"] = [copy.deepcopy(row) for row in parent["records"] if
                    min(range(2),key=lambda r:distance(row[0],t["centers"][r])) == route]
                self.nodes[index] = child
            parent["children"],parent["centers"],parent["records"] = ids,t["centers"],[]
            self.admissions += 1
        self.trial = None
        self.next_trial = self.steps+self.config["cooldown"]

    def learn(self,action,outcome):
        if self.phase != "feedback":
            raise RuntimeError("No pending trace feedback")
        if type(action) is not int or action not in (0,1) or type(outcome) is not int or outcome not in (0,1):
            raise ValueError("Unsupported trace outcome")
        leaf, state, coin = self._leaf(self.state),list(self.state),self.coin
        probability = self.pending_probabilities()[action]
        node = self.nodes[leaf]
        if self.trial is not None and self.trial["leaf"] == leaf:
            t = self.trial
            route = min(range(2),key=lambda r:distance(state,t["centers"][r]))
            proposed = log_probability(t["candidate"].probability(action,route),outcome)
            t["improvement"] += proposed-log_probability(t["reference"].probability(action,0),outcome)
            t["relevance"] += proposed-log_probability(t["control"].probability(action,coin),outcome)
            t["support"][route][action] += 1
            t["n"] += 1
        node["bank"].update(action,outcome,0)
        self.neural_updates += 1
        node["records"].append([state,coin,action,outcome])
        if len(node["records"]) > self.config["window"]:
            del node["records"][0]
        self.steps += 1
        self.contexts[self.context] += 1
        if self.trial is not None and self.trial["leaf"] == leaf and self.trial["n"] in LOOKS:
            self._judge()
        elif (self.trial is None and self.config["adaptive"] and self.steps >= self.next_trial
              and self.leaf_count() < self.config["max_leaves"] and node["depth"] < self.config["max_depth"]
              and len(node["records"]) >= self.config["min_records"]):
            recent = node["records"][-self.config["min_records"]:]
            bank = node["protected"] or node["bank"]
            loss = math.fsum((bank.probability(a,0)-y)**2 for _,_,a,y in recent)/len(recent)
            if loss > .18:
                self._propose(leaf)
            else:
                self.next_trial = self.steps+self.config["cooldown"]
        self.finish_evaluation()
        return probability

    def leaf_count(self):
        return sum(node["children"] is None for node in self.nodes.values())

    def metrics(self):
        points = sum(4+4*int(node["protected"] is not None)+2*int(node["children"] is not None)
                     for node in self.nodes.values())
        if self.trial is not None:
            points += 14  # two centers and three four-point banks.
        return {"steps":self.steps,"contexts":len(self.contexts),"symbols":len(self.symbols),
                "leaves":self.leaf_count(),"nodes":len(self.nodes),"allocated_s2_points":points,
                "retained_records":sum(len(node["records"]) for node in self.nodes.values()),
                "attempts":self.attempts,"admissions":self.admissions,"neural_updates":self.neural_updates,
                "lifetime_alpha_upper_bound":.05,"decisions":copy.deepcopy(self.decisions),
                "trial_n":None if self.trial is None else self.trial["n"]}

    def checkpoint(self):
        nodes = {}
        for key,node in self.nodes.items():
            nodes[str(key)] = {**copy.deepcopy({k:v for k,v in node.items() if k not in ("bank","protected")}),
                              "bank":node["bank"].checkpoint(),
                              "protected":None if node["protected"] is None else node["protected"].checkpoint()}
        trial = None
        if self.trial is not None:
            trial = {**copy.deepcopy({k:v for k,v in self.trial.items() if k not in ("candidate","control","reference")}),
                     **{k:self.trial[k].checkpoint() for k in ("candidate","control","reference")}}
        return {"format":1,"implementation":self.IMPLEMENTATION,"config":dict(self.config),
                "rng":self.rng.getstate(),"nodes":nodes,"trial":trial,"phase":self.phase,
                "state":list(self.state),"context":self.context,"coin":self.coin,
                "symbols":copy.deepcopy(self.symbols),"contexts":{str(k):v for k,v in self.contexts.items()},
                "steps":self.steps,"attempts":self.attempts,"admissions":self.admissions,
                "neural_updates":self.neural_updates,"fit_records_total":self.fit_records_total,"next_trial":self.next_trial,
                "decisions":copy.deepcopy(self.decisions)}

    @classmethod
    def restore(cls,data):
        expected = {"format","implementation","config","rng","nodes","trial","phase","state","context","coin",
                    "symbols","contexts","steps","attempts","admissions","neural_updates","fit_records_total","next_trial","decisions"}
        if type(data) is not dict or set(data) != expected or type(data["format"]) is not int or data["format"] != 1 or data["implementation"] != cls.IMPLEMENTATION:
            raise ValueError("Invalid adaptive trace checkpoint")
        new = cls(**data["config"])
        new.rng.setstate(_tuples(data["rng"]))
        for k in ("steps","attempts","admissions","neural_updates","fit_records_total","next_trial"):
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
        if len(new.contexts) > 8 or sum(new.contexts.values()) != new.steps:
            raise ValueError("Trace contexts and exposure differ")
        if new.phase == "idle":
            if new.context is not None or new.coin is not None:
                raise ValueError("Idle trace has context")
        elif new.context not in new.contexts or new.coin not in (0,1):
            raise ValueError("Invalid active trace context")
        new.symbols = copy.deepcopy(data["symbols"])
        if len(new.symbols) > 64 or any(symbol_point(k) != v for k,v in new.symbols.items()):
            raise ValueError("Trace observation codes differ")
        new.trial = None
        if data["trial"] is not None:
            new.trial = copy.deepcopy(data["trial"])
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
            counter(new.trial["n"],"trace trial exposure")
            if new.trial["n"] >= LOOKS[-1] or sum(map(sum,new.trial["support"])) != new.trial["n"]:
                raise ValueError("Trace trial exposure differs")
            for center in new.trial["centers"]:
                point(center)
        new.decisions = copy.deepcopy(data["decisions"])
        if len(new.decisions) > 48 or new.admissions > new.attempts:
            raise ValueError("Trace decision ledger differs")
        return new
