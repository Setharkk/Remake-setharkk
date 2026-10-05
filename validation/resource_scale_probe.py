"""Declared resource/cost and multi-state experiments; failures remain visible."""
import argparse
import copy
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import time
import types

BASE = "8a969f5a399f82b703142df073dac9d811ab1288"
TOKENS = ("cedar:axis", "amber:signal", "ocean:route", "quartz:memory")
CASES = {8: 8, 16: 32}
PHASES = (("initial_noise", 2048, False, False),
          ("signal", 262144, True, False),
          ("noise", 32768, False, False),
          ("recovery", 32768, True, False),
          ("inversion", 262144, True, True))


def events(state, states, rng, *, long=False, context=0):
    first, second = state//(states//4), state%(states//4)
    word = [TOKENS[first], TOKENS[second], TOKENS[first], TOKENS[second]]
    prefix = [TOKENS[rng.randrange(4)] for _ in range(64 if long else rng.randrange(9))]
    return ([{"kind": "token", "token": token, "task": context} for token in prefix+word]
            + [{"kind": "surface", "surface": "sealed", "task": context}])


def target(state, actions, reverse):
    # Supplied world rule; no state ID or target is transmitted to the learner.
    return actions-1-state if reverse else state


def evaluate(core, states, seed, reverse):
    modes = {}
    for mode in ("ordinary", "long_prefix", "new_context"):
        clone, rng, correct, losses = copy.deepcopy(core), random.Random(seed), 0, []
        n = core.config["n_actions"]
        for i in range(states*16):
            state = i%states
            context = 16 if mode == "new_context" else rng.randrange(16)
            for event in events(state, states, rng, long=mode=="long_prefix", context=context):
                p = clone.receive(event)
            expected = target(state, n, reverse)
            correct += max(range(n), key=p.__getitem__) == expected
            losses.extend((p[a]-int(a==expected))**2 for a in range(n))
            clone.finish_evaluation()
        modes[mode] = {"policy_accuracy": correct/(states*16),
                       "brier": math.fsum(losses)/(states*16*n)}
    return modes


def research(states, seed):
    from first_piece.action_trace import ActionTraceLearner
    n = CASES[states]
    core = ActionTraceLearner(seed, n_actions=n, max_tasks=32, max_symbols=256,
        max_leaves=32, max_depth=12, record_budget=1000000)
    rng, reports, total, peak_json = random.Random(800000+seed), [], 0, 0
    started = time.perf_counter()
    for phase, duration, signal, reverse in PHASES:
        admissions, losses, curves = core.admissions+core.revisions, [], []
        for step in range(1, duration+1):
            state, context = rng.randrange(states), rng.randrange(16)
            for event in events(state, states, rng, context=context):
                p = core.receive(event)
            action = rng.randrange(n)
            outcome = int(action == target(state,n,reverse)) if signal else rng.randrange(2)
            losses.append((p[action]-outcome)**2)
            core.learn(action,outcome)
            if step%32768 == 0:
                cp = json.loads(json.dumps(core.checkpoint()))
                restored = ActionTraceLearner.restore(cp)
                if restored.checkpoint() != core.checkpoint():
                    raise AssertionError("Multi-state continuation changed state")
                core = restored
                peak_json = max(peak_json,len(json.dumps(cp).encode()))
                score = evaluate(core,states,900000+seed,reverse)
                curves.append({"exposure":step,"evaluation":score})
                print("RESOURCE_SCALE_PROGRESS="+json.dumps({"states":states,"seed":seed,
                    "phase":phase,"exposure":step,"evaluation":score,
                    "leaves":core.leaf_count(),"seconds":time.perf_counter()-started}),flush=True)
        total += duration
        evaluation = evaluate(core,states,950000+seed,reverse)
        reports.append({"phase":phase,"episodes":duration,
            "admissions_added":core.admissions+core.revisions-admissions,
            "prequential_brier":math.fsum(losses)/duration,
            "late_half_brier":math.fsum(losses[duration//2:])/(duration//2),
            "evaluation":evaluation,"curves":curves,"metrics":core.metrics()})
    by = {r["phase"]:r for r in reports}
    criteria = {"no_initial_noise_admission":by["initial_noise"]["admissions_added"]==0,
                "no_noise_admission":by["noise"]["admissions_added"]==0,
                "late_noise_brier_le_028":by["noise"]["late_half_brier"]<=.28,
                "actual_weight_revisions":core.revisions>0,
                "within_point_budget":core.metrics()["allocated_s2_points"]<=core.config["point_budget"],
                "within_record_reservation":core.metrics()["reserved_record_slots"]<=core.config["record_budget"]}
    for phase in ("signal","noise","recovery","inversion"):
        for mode,score in by[phase]["evaluation"].items():
            criteria[phase+"_"+mode+"_accuracy_ge_090"] = score["policy_accuracy"]>=.9
            if phase == "recovery":
                criteria["recovery_"+mode+"_brier_le_005"] = score["brier"]<=.05
    return {"states":states,"actions":n,"seed":seed,"episodes":total,"phases":reports,
            "criteria":criteria,"research_pass":all(criteria.values()),
            "peak_sampled_checkpoint_bytes":peak_json,"seconds":time.perf_counter()-started}


def reference_class():
    source = subprocess.check_output(["git","show",BASE+":first_piece/action_trace.py"],text=True)
    module = types.ModuleType("first_piece.reference_action_trace")
    module.__package__ = "first_piece"
    exec(compile(source,"<frozen-reference>","exec"),module.__dict__)
    return module.ActionTraceLearner


def engineering():
    from first_piece.action_trace import ActionTraceLearner
    from first_piece.scalable_service import ScalableActionService
    from first_piece.tests.test_trace_v2 import feed_wire
    from first_piece.tests.test_action_catalogue import actions
    from first_piece.integration_probe import agent_proposal, observed_receipt
    from first_piece.tests.test_readiness import trace
    old_class, results = reference_class(), []
    for n in (8,32,128):
        options = {"n_actions":n,"adaptive":False,"max_tasks":1,"max_leaves":2,"record_budget":1000000}
        old,new = old_class(3,**options),ActionTraceLearner(3,**options)
        timings = {"reference":[],"scaled":[]}
        for i in range(2048):
            outcomes = []
            for name,core in (("reference",old),("scaled",new)):
                for e in trace(i%2,0):
                    p = core.receive(e)
                t = time.perf_counter()
                outcomes.append((p,core.learn(i%n,int(i%n==0))))
                timings[name].append(time.perf_counter()-t)
            if outcomes[0] != outcomes[1]:
                raise AssertionError("Hot-path optimisation changed forecasts")
        if old.checkpoint()!=new.checkpoint():
            raise AssertionError("Hot-path optimisation changed weights or RNG")
        results.append({"actions":n,"episodes":2048,"exact_neural_state":True,
            "receipt_mean_seconds":{k:math.fsum(v)/len(v) for k,v in timings.items()},
            "receipt_max_seconds":{k:max(v) for k,v in timings.items()}})
    direct = ActionTraceLearner(4,n_actions=32)
    service = ScalableActionService(seed=4,actions=actions(32))
    sequence, restored, peak = 0,set(),0.0
    for i in range(4096):
        for e in trace(i%2,(i//2)%4):
            expected = direct.receive(e)
        p,sequence = feed_wire(service,trace(i%2,(i//2)%4),sequence)
        if expected != [f["distribution"]["parameters"]["p"] for f in p["forecasts"]]:
            raise AssertionError("Scaled service forecast differs")
        a = (i//2)%32
        y = int(a%2 == i%2)
        direct.learn(a,y)
        req = service.register_action(agent_proposal(p,a),executor_id="probe:executor")
        receipt = observed_receipt(req,y)
        service.begin_receipt(receipt)
        while service._work is not None:
            fit = service._work.fit
            key = (service._work.phase,None if fit is None else fit.phase)
            if key not in restored:
                service = ScalableActionService.restore(json.loads(json.dumps(service.checkpoint())))
                restored.add(key)
            t = time.perf_counter()
            status = service.advance(128)
            peak = max(peak,time.perf_counter()-t)
            if status["consumed_units"]>128:
                raise AssertionError("Quota exceeded")
        if i%512==0 and direct.checkpoint()!=service._adapter._learner.checkpoint():
            raise AssertionError("Scaled service learning differs")
    if direct.checkpoint()!=service._adapter._learner.checkpoint():
        raise AssertionError("Final cooperative state differs")
    cp = service.checkpoint()
    service.submit_receipt(receipt)
    if cp!=service.checkpoint():
        raise AssertionError("Duplicate receipt added evidence")
    return {"receipt_costs":results,"parity_episodes":4096,"parity_actions":32,
            "exact_forecasts_weights_rng":True,"restored_phases":sorted(map(str,restored)),
            "max_advance_seconds":peak,"capabilities":service.capabilities()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case",help="8:seed or 16:seed; fixed protocol")
    parser.add_argument("--engineering",action="store_true")
    parser.add_argument("--out",default="resource-scale.json")
    args = parser.parse_args()
    report = {"protocol":1,"base":BASE,"os":platform.system(),"python":platform.python_version(),
              "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()}
    if args.engineering:
        report["engineering"] = engineering()
    else:
        states, seed = map(int,args.case.split(":"))
        if states not in CASES or seed not in (0,1,2):
            raise ValueError("Case outside declared protocol")
        report["research"] = research(states,seed)
    Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("RESOURCE_SCALE_JSON="+json.dumps(report,sort_keys=True),flush=True)


if __name__ == "__main__":
    main()
