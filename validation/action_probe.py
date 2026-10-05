"""Frozen multi-action protocol with labelled noise and explicit budget evidence."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import time
import traceback

BASE = "32a5ba2976a3955c576e9a3a0508ab92e9d44ae8"
FILES = {"first_piece/action_bank.py","first_piece/action_trace.py","first_piece/action_work.py",
         "first_piece/action_service.py","first_piece/tests/test_action_catalogue.py"}


def apply_bundle(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data["base_commit"] != BASE or set(data["files"]) != FILES:
        raise ValueError("Candidate set/base differs")
    blobs = {}
    for name,source in data["files"].items():
        raw = source.encode("utf-8")
        target = Path(name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        blobs[name] = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    print("ACTION_BLOBS_JSON="+json.dumps(blobs,sort_keys=True),flush=True)


def success(action,state,n,sparse):
    return int(action == (0 if state == 0 else n-1)) if sparse else int(action%2 == state)


def evaluate(core,seed,*,reverse=False,sparse=False,long=False,context=None):
    from validation.readiness_probe import episodes
    n,correct,losses = core.config["n_actions"],0,[]
    for events,state in episodes(seed,512,long=long,context=context):
        for event in events:
            p = core.receive(event)
        state = 1-state if reverse else state
        best = max(range(n),key=p.__getitem__)
        correct += success(best,state,n,sparse)
        losses.extend((p[a]-success(a,state,n,sparse))**2 for a in range(n))
        core.finish_evaluation()
    return {"policy_accuracy":correct/512,"brier":math.fsum(losses)/(512*n)}


def research(n,seed,sparse):
    from first_piece.action_trace import ActionTraceLearner
    from validation.readiness_probe import episodes
    core = ActionTraceLearner(seed,n_actions=n)
    action_rng,noise = random.Random(910000+seed),random.Random(920000+seed)
    reports,total,peak_bytes,peak_points = [],0,0,0
    started = time.perf_counter()
    phases = (("initial_noise",2048,False,False),("signal",32768,True,False),
              ("interruption_noise",16384,False,False),("recovery",8192,True,False),
              ("inversion",65536,True,True))
    for phase,count,signal,reverse in phases:
        before = core.admissions+core.revisions
        losses,curves = [],[]
        for index,(events,state) in enumerate(episodes(930000+seed+total,count),1):
            for event in events:
                p = core.receive(event)
            action = action_rng.randrange(n)
            state = 1-state if reverse else state
            outcome = success(action,state,n,sparse) if signal else int(noise.random()<.5)
            losses.append((p[action]-outcome)**2)
            core.learn(action,outcome)
            if index%4096 == 0:
                clone = ActionTraceLearner.restore(json.loads(json.dumps(core.checkpoint())))
                if clone.checkpoint() != core.checkpoint():
                    raise AssertionError("Full research resume changed state")
                core = clone
                peak_bytes = max(peak_bytes,len(json.dumps(core.checkpoint()).encode()))
                peak_points = max(peak_points,core.metrics()["allocated_s2_points"])
            looks = (2048,8192,16384,32768) if phase == "signal" else (8192,32768,65536)
            if phase in ("signal","inversion") and index in looks:
                curves.append({"exposure":index,**evaluate(copy.deepcopy(core),940000+seed,
                                                          reverse=reverse,sparse=sparse)})
        total += count
        evaluation = {name:evaluate(copy.deepcopy(core),950000+seed,reverse=reverse,sparse=sparse,
                                    long=name=="long_prefix",context=4 if name=="new_context" else None)
                      for name in ("ordinary","long_prefix","new_context")}
        result = {"phase":phase,"episodes":count,"admissions_added":core.admissions+core.revisions-before,
                  "prequential_brier":math.fsum(losses)/count,
                  "late_half_brier":math.fsum(losses[count//2:])/(count//2),
                  "evaluation":evaluation,"curves":curves,"metrics":core.metrics()}
        reports.append(result)
        print("ACTION_PHASE="+json.dumps({"n_actions":n,"seed":seed,"sparse":sparse,**result},sort_keys=True),flush=True)
    by_phase = {p["phase"]:p for p in reports}
    criteria = {"no_initial_noise_admission":by_phase["initial_noise"]["admissions_added"] == 0,
                "no_interruption_noise_admission":by_phase["interruption_noise"]["admissions_added"] == 0,
                "noise_brier_le_029":by_phase["interruption_noise"]["prequential_brier"] <= .29,
                "late_noise_brier_le_027":by_phase["interruption_noise"]["late_half_brier"] <= .27,
                "weights_revised":core.revisions > 0}
    for phase in ("signal","interruption_noise","recovery","inversion"):
        for name,score in by_phase[phase]["evaluation"].items():
            criteria[phase+"_"+name+"_accuracy_ge_095"] = score["policy_accuracy"] >= .95
            if phase == "recovery":
                criteria[phase+"_"+name+"_brier_le_002"] = score["brier"] <= .02
    return {"n_actions":n,"seed":seed,"sparse":sparse,"episodes":total,"phases":reports,
            "criteria":criteria,"research_pass":all(criteria.values()),
            "max_sampled_checkpoint_bytes":peak_bytes,"max_sampled_s2_points":peak_points,
            "seconds":time.perf_counter()-started}


def engineering(n):
    from first_piece.action_trace import ActionTraceLearner
    from first_piece.action_service import ActionTraceService
    from first_piece.tests.test_action_catalogue import actions
    from first_piece.tests.test_trace_v2 import feed_wire
    from first_piece.integration_probe import agent_proposal,observed_receipt
    from validation.readiness_probe import episodes
    direct,service = ActionTraceLearner(4,n_actions=n),ActionTraceService(seed=4,actions=actions(n))
    rng,sequence,units,ticks,peak = random.Random(77000),0,0,0,0.0
    restored = set()
    started = time.perf_counter()
    for index,(events,state) in enumerate(episodes(78000,8192),1):
        for event in events:
            expected = direct.receive(event)
        p,sequence = feed_wire(service,events,sequence)
        if expected != [f["distribution"]["parameters"]["p"] for f in p["forecasts"]]:
            raise AssertionError(f"Forecast differs at {index}")
        a = rng.randrange(n)
        y = success(a,state,n,False)
        direct.learn(a,y)
        req = service.register_action(agent_proposal(p,a),executor_id="probe:executor")
        receipt = observed_receipt(req,y)
        service.begin_receipt(receipt)
        while service._work is not None:
            w = service._work
            key = (w.phase,None if w.fit is None else (w.fit.phase,w.fit.epoch,w.fit.bank,w.fit.mean_group))
            if key not in restored:
                service = ActionTraceService.restore(json.loads(json.dumps(service.checkpoint())))
                restored.add(key)
            t = time.perf_counter()
            status = service.advance(128)
            peak = max(peak,time.perf_counter()-t)
            if status["consumed_units"] > 128:
                raise AssertionError("Quota exceeded")
            units += status["consumed_units"]
            ticks += 1
        if index%1024 == 0:
            if direct.checkpoint() != service._adapter._learner.checkpoint():
                raise AssertionError("Full service state differs")
            print("ACTION_PARITY="+json.dumps({"n_actions":n,"episodes":index}),flush=True)
    before = service.checkpoint()
    service.submit_receipt(receipt)
    if before != service.checkpoint():
        raise AssertionError("Duplicate receipt changed model")
    return {"n_actions":n,"episodes":8192,"exact_forecasts_and_checkpoints":True,
            "restored_phase_keys":sorted(map(str,restored)),"quota":128,"work_units":units,
            "ticks":ticks,"max_advance_seconds":peak,"seconds":time.perf_counter()-started,
            "metrics":direct.metrics()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply")
    parser.add_argument("--out",default="actions.json")
    parser.add_argument("--quick",action="store_true")
    parser.add_argument("--case",help="N:seed:sparse for one unchanged full research case")
    args = parser.parse_args()
    if args.apply:
        apply_bundle(args.apply)
        return
    report = {"protocol":1,"base":BASE,"os":platform.system(),"python":platform.python_version(),
              "candidate_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
              "cases":{},"errors":{}}
    cases = [(f"engineering_{n}",lambda count=n:engineering(count)) for n in (4,8,32)]
    if not args.quick:
        cases += [(f"n{n}_seed{s}_sparse{int(sparse)}",
                   lambda count=n,seed=s,rare=sparse:research(count,seed,rare))
                  for n in (4,8,32) for s in range(3) for sparse in (False,True)]
    if args.case:
        n,seed,sparse = map(int,args.case.split(":"))
        if n not in (4,8,32) or seed not in (0,1,2) or sparse not in (0,1):
            raise ValueError("Case outside frozen protocol")
        cases = [(f"n{n}_seed{seed}_sparse{sparse}",lambda:research(n,seed,bool(sparse)))]
    for name,fn in cases:
        try:
            report["cases"][name] = fn()
        except Exception:
            report["errors"][name] = traceback.format_exc()
            print("ACTION_ERROR="+json.dumps({name:report["errors"][name]}),flush=True)
    report["engineering_pass"] = not report["errors"]
    report["research_pass"] = None if args.quick else all(
        case["research_pass"] for case in report["cases"].values() if "research_pass" in case) and len(report["cases"]) == (1 if args.case else 21)
    Path(args.out).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("ACTION_FULL_JSON="+json.dumps(report,sort_keys=True),flush=True)
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
