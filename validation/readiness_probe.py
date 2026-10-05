"""Frozen readiness protocol: engineering parity and paired representation curves."""
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

BASE = "9dbc2876d8347667dd46deddd9f340be96640c4d"


def apply_bundle(path):
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    if bundle["base_commit"] != BASE:
        raise ValueError("Unexpected candidate base")
    expected = {"first_piece/cooperative.py","first_piece/adaptive_trace.py",
                "first_piece/tests/test_readiness.py"}
    if set(bundle["files"]) != expected:
        raise ValueError("Candidate path set differs")
    blobs = {}
    for name,source in bundle["files"].items():
        raw = source.encode("utf-8")
        target = Path(name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        blobs[name] = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    print("READINESS_BLOBS_JSON="+json.dumps(blobs,sort_keys=True),flush=True)


def observation(service,events,sequence):
    from first_piece.tests.test_shared import wire_symbol
    p = None
    for event in events:
        p = service.submit_observation(wire_symbol(sequence,event.get("token","sealed"),
            context=f"ctx:{event['task']}",end=event["kind"] == "surface"))
        sequence += 1
    return p,sequence


def long_parity():
    from first_piece.cooperative import CooperativeService, canonical
    from first_piece.plastic_revision import PlasticRevisionLearner
    from first_piece.scale_world import ScaleWorld
    from first_piece.integration_probe import agent_proposal, observed_receipt
    direct = PlasticRevisionLearner(0,max_tasks=16,max_symbols=64)
    service = CooperativeService(seed=0,learner_options={"max_tasks":16,"max_symbols":64})
    world,actions,noise = ScaleWorld(400,n_contexts=16),random.Random(8200000),random.Random(8300000)
    sequence = total_units = ticks = 0
    peak = 0.0
    resumed = set()
    phases = {}
    started = time.perf_counter()
    for index in range(32000):
        events,target = world.episode(index%16)
        for event in events:
            expected = direct.receive(event)
        p,sequence = observation(service,events,sequence)
        actual = [f["distribution"]["parameters"]["p"] for f in p["forecasts"]]
        if actual != expected:
            raise AssertionError(f"Forecast parity lost at {index}")
        action = actions.randrange(4)
        outcome = int(noise.random() < .5) if index < 16000 else int(action == target)
        direct.learn(action,outcome)
        request = service.register_action(agent_proposal(p,action),executor_id="probe:executor")
        receipt = observed_receipt(request,outcome)
        service.begin_receipt(receipt)
        while service._work is not None:
            work = service._work
            kind = work.intent["kind"] if work.intent else "feedback"
            phase = work.phase
            key = (kind,phase,work.search.phase if phase == "search" else
                   work.fit["bank"] if phase == "replay" else None)
            phases[kind+":"+phase] = phases.get(kind+":"+phase,0)+1
            if key not in resumed:
                service = CooperativeService.restore(json.loads(json.dumps(service.checkpoint())))
                resumed.add(key)
            t = time.perf_counter()
            status = service.advance(128)
            peak = max(peak,time.perf_counter()-t)
            if status["consumed_units"] > 128:
                raise AssertionError("Quota exceeded")
            total_units += status["consumed_units"]
            ticks += 1
        if (index+1)%4000 == 0:
            if canonical(direct) != canonical(service._adapter._learner):
                raise AssertionError(f"Full state parity lost at {index+1}")
            print("READINESS_PARITY_PROGRESS="+str(index+1),flush=True)
    final = canonical(direct)
    if service.submit_receipt(receipt)["model_revision"] != 32000:
        raise AssertionError("Duplicate learned again")
    if final != canonical(service._adapter._learner):
        raise AssertionError("Duplicate changed core")
    return {"episodes":32000,"symbols":64,"contexts":16,"exact_forecasts_and_checkpoints":True,
            "quota":128,"ticks":ticks,"work_units":total_units,"max_tick_seconds":peak,
            "seconds":time.perf_counter()-started,"restored_phase_keys":sorted(map(str,resumed)),
            "work_phases":phases,"final_steps":direct.steps,"neural_updates":direct.neural_updates,
            "admissions":direct.admissions,"attempts":direct.attempts}


def full_fit():
    from first_piece.cooperative import ReceiptWork, canonical
    from first_piece.plastic_revision import PlasticRevisionLearner
    from first_piece.scale_world import ScaleWorld
    from first_piece.tests.test_shared import train
    core = train(PlasticRevisionLearner(5,max_tasks=16,max_symbols=64),
                 ScaleWorld(400,n_contexts=16),6000)
    if core.trial is not None:
        core._close_unfinished_trial("superseded")
    reports = []
    for confidence in (False,True):
        if confidence and core._protected is None:
            raise AssertionError("Fixture has no protected program")
        reference = copy.deepcopy(core)
        gain = .1 if confidence else None
        t = time.perf_counter()
        reference._start_trial(None,refinement_gain=gain)
        synchronous = time.perf_counter()-t
        receipt = {"schema_version":1,"receipt_id":"fit:one","request_id":"fit:one",
                   "source_id":"probe:executor","status":"observed",
                   "outcome":{"measure":"lab.success","unit":"binary","value":1}}
        work = ReceiptWork(copy.deepcopy(core),0,receipt)
        work.intent = {"kind":"start","scope":None,"gain":gain}
        work._begin_intent()
        resumes = set()
        peaks = []
        while work.phase != "done":
            key = (work.phase,work.fit["bank"] if work.phase == "replay" else
                   work.search.phase if work.phase == "search" else None)
            if key not in resumes:
                work = ReceiptWork.restore(json.loads(json.dumps(work.checkpoint())))
                resumes.add(key)
            t = time.perf_counter()
            used = 0
            while used < 128 and work.phase != "done":
                work.advance()
                used += 1
            peaks.append(time.perf_counter()-t)
        if canonical(reference) != canonical(work.core):
            raise AssertionError("Full replay parity lost")
        reports.append({"mode":"confidence" if confidence else "structure",
                        "fit_records":len(work.rows),"gradients":work.fit["gradients"],
                        "work_units":work.units,"exact_checkpoint":True,
                        "max_tick_seconds":max(peaks),"ticks":len(peaks),
                        "synchronous_fit_seconds":synchronous,
                        "restored_phases":sorted(map(str,resumes))})
    return reports


def episodes(seed,n,*,long=False,context=None):
    rng = random.Random(seed)
    a,b = "opaque.alpha","opaque.beta"
    extras = [f"opaque.distractor.{i:02}" for i in range(16)]
    for pair in range((n+1)//2):
        prefix = [a,b]+rng.sample(extras,rng.randint(9,12) if long else rng.randint(2,7))
        context_id = pair%4 if context is None else context
        order = [0,1]
        rng.shuffle(order)
        for target in order:
            tokens = prefix+([a,a,b] if target == 0 else [a,b,b])
            yield [{"kind":"token","token":token,"task":context_id} for token in tokens]+[
                {"kind":"surface","surface":"sealed","task":context_id}],target


def policy(core,seed,*,long=False,context=None):
    correct = 0
    brier = []
    for events,target in episodes(seed,512,long=long,context=context):
        for event in events:
            p = core.receive(event)
        correct += max(range(2),key=p.__getitem__) == target
        brier.extend((p[a]-int(a == target))**2 for a in range(2))
        core.finish_evaluation()
    return {"episodes":512,"policy_accuracy":correct/512,"brier":math.fsum(brier)/1024}


def representation(seed):
    from first_piece.adaptive_trace import AdaptiveTraceLearner
    from first_piece.plastic_revision import PlasticRevisionLearner
    from first_piece.cooperative import canonical
    learners = {"format8":PlasticRevisionLearner(seed,n_actions=2,max_tasks=8,max_symbols=32),
                "fixed_trace":AdaptiveTraceLearner(seed,adaptive=False),
                "adaptive_trace":AdaptiveTraceLearner(seed)}
    action_rng = random.Random(7300000+seed)
    noise_rng = random.Random(7400000+seed)
    phase_reports = []
    observed_resume = False
    max_points = max_records = max_bytes = 0
    peak_learn = 0.0
    started = time.perf_counter()
    total = 0
    paired_features = None
    for phase,n,signal in (("initial_noise",2048,False),("signal",16384,True),
                           ("interruption_noise",8192,False),("recovery",4096,True)):
        curves = []
        observed_losses = {name:[] for name in learners}
        before = learners["adaptive_trace"].admissions
        for index,(events,target) in enumerate(episodes(7500000+seed+total,n),1):
            probabilities = {}
            for name,core in learners.items():
                for event in events:
                    p = core.receive(event)
                probabilities[name] = p
            old = learners["format8"]
            signature = (old.episode["task"],old.episode["mask"],old.episode["before"],len(events))
            if index%2:
                paired_features = signature
            elif signature != paired_features:
                raise AssertionError("Control sees unmatched observation structure")
            action = action_rng.randrange(2)
            outcome = int(action == target) if signal else int(noise_rng.random() < .5)
            for name,probability in probabilities.items():
                observed_losses[name].append((probability[action]-outcome)**2)
            adaptive = learners["adaptive_trace"]
            # Checkpoint pending prediction and a live frozen trial; neither acts again.
            if adaptive.trial is not None and adaptive.trial["n"] >= 19 and not observed_resume:
                clone = AdaptiveTraceLearner.restore(json.loads(json.dumps(adaptive.checkpoint())))
                if clone.pending_probabilities() != adaptive.pending_probabilities():
                    raise AssertionError("Resume changed forecast")
                clone.learn(action,outcome)
                adaptive.learn(action,outcome)
                if clone.checkpoint() != adaptive.checkpoint():
                    raise AssertionError("Resume changed future state")
                learners["adaptive_trace"] = clone
                observed_resume = True
                skip = True
            else:
                skip = False
            for name,core in learners.items():
                if name == "adaptive_trace" and skip:
                    continue
                t = time.perf_counter()
                core.learn(action,outcome)
                if name == "adaptive_trace":
                    peak_learn = max(peak_learn,time.perf_counter()-t)
            adaptive = learners["adaptive_trace"]
            if index%128 == 0:
                m = adaptive.metrics()
                max_points = max(max_points,m["allocated_s2_points"])
                max_records = max(max_records,m["retained_records"])
                max_bytes = max(max_bytes,len(json.dumps(adaptive.checkpoint()).encode()))
                if max_points > 160 or max_records > 2048:
                    raise AssertionError("Adaptive memory budget exceeded")
            if phase == "signal" and index in (512,2048,8192,16384):
                curve = {"signal_exposure":index,
                         "variants":{name:policy(copy.deepcopy(core),8000000+seed)
                                     for name,core in learners.items()}}
                curves.append(curve)
                print("READINESS_CURVE="+json.dumps({"seed":seed,**curve}),flush=True)
        total += n
        tests = {name:{"ordinary":policy(copy.deepcopy(core),8100000+seed),
                      "long_prefix":policy(copy.deepcopy(core),8200000+seed,long=True),
                      "new_context":policy(copy.deepcopy(core),8300000+seed,context=4)}
                 for name,core in learners.items()}
        phase_reports.append({"phase":phase,"exposure":n,"admissions_added":learners["adaptive_trace"].admissions-before,
                              "curves":curves,"evaluation":tests,
                              "prequential_brier":{name:math.fsum(values)/n for name,values in observed_losses.items()},
                              "adaptive_metrics":learners["adaptive_trace"].metrics()})
        print("READINESS_PHASE="+json.dumps({"seed":seed,"phase":phase,"evaluation":tests,
              "metrics":learners["adaptive_trace"].metrics()}),flush=True)
    by_phase = {entry["phase"]:entry for entry in phase_reports}
    criteria = {"no_admission_initial_noise":by_phase["initial_noise"]["admissions_added"] == 0,
                "no_admission_interruption_noise":by_phase["interruption_noise"]["admissions_added"] == 0,
                "json_resume_exact":observed_resume}
    for phase in ("signal","interruption_noise","recovery"):
        for setting in ("ordinary","long_prefix","new_context"):
            criteria[phase+"_"+setting+"_at_least_95"] = (
                by_phase[phase]["evaluation"]["adaptive_trace"][setting]["policy_accuracy"] >= .95)
    return {"seed":seed,"episodes":total,"phases":phase_reports,"criteria":criteria,
            "all_research_criteria_pass":all(criteria.values()),"json_resume_exact":observed_resume,
            "max_allocated_s2_points":max_points,"max_retained_records":max_records,
            "max_checkpoint_bytes":max_bytes,"max_adaptive_learn_seconds":peak_learn,
            "seconds":time.perf_counter()-started,
            "adaptive_final":learners["adaptive_trace"].metrics(),
            "format8_final":{"steps":learners["format8"].steps,"admissions":learners["format8"].admissions,
                             "attempts":learners["format8"].attempts,
                             "neural_updates":learners["format8"].neural_updates}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.apply:
        apply_bundle(args.apply)
        return
    report = {"protocol":1,"base":BASE,"os":platform.system(),"python":platform.python_version(),
              "candidate_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
              "cases":{},"errors":{}}
    for name,fn in [("long_parity",long_parity),("full_fit",full_fit)]+[
            (f"representation_seed_{seed}",lambda s=seed:representation(s)) for seed in range(3)]:
        try:
            report["cases"][name] = fn()
            print("READINESS_CASE="+json.dumps({name:report["cases"][name]},sort_keys=True),flush=True)
        except Exception:
            report["errors"][name] = traceback.format_exc()
            print("READINESS_ERROR="+json.dumps({name:report["errors"][name]}),flush=True)
    # Negative research outcomes are evidence; engineering failures fail CI.
    report["engineering_pass"] = not report["errors"]
    report["research_pass"] = all(report["cases"].get(f"representation_seed_{seed}",{}).get(
        "all_research_criteria_pass",False) for seed in range(3))
    Path(args.out).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("READINESS_FULL_JSON="+json.dumps(report,sort_keys=True),flush=True)
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
