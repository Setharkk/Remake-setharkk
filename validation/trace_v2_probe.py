"""Prospective protocol v2; retain failed research criteria without hiding them."""
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

BASE = "ba8f8e642f4af19620f72aaa73e719d5da6f40dd"
FILES = {"first_piece/adaptive_trace_v2.py", "first_piece/trace_work.py",
         "first_piece/trace_service.py", "first_piece/cooperative.py",
         "first_piece/tests/test_trace_v2.py"}


def apply_bundle(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data["base_commit"] != BASE or set(data["files"]) != FILES:
        raise ValueError("Candidate source set/base differs")
    blobs = {}
    for name, source in data["files"].items():
        raw = source.encode("utf-8")
        target = Path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        blobs[name] = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    print("TRACE_V2_BLOBS_JSON="+json.dumps(blobs, sort_keys=True), flush=True)


def evaluate(core, seed, *, reverse=False, long=False, context=None):
    from validation.readiness_probe import episodes
    hits = 0
    losses = []
    for events, target in episodes(seed, 512, long=long, context=context):
        for event in events:
            p = core.receive(event)
        target = 1-target if reverse else target
        hits += max(range(2), key=p.__getitem__) == target
        losses.extend((p[a]-int(a == target))**2 for a in range(2))
        core.finish_evaluation()
    return {"policy_accuracy": hits/512, "brier": math.fsum(losses)/1024}


def representation(seed):
    from validation.readiness_probe import episodes
    from first_piece.adaptive_trace import AdaptiveTraceLearner
    from first_piece.adaptive_trace_v2 import AdaptiveTraceLearnerV2
    variants = {"v1": AdaptiveTraceLearner(seed), "v2": AdaptiveTraceLearnerV2(seed)}
    actions, noise = random.Random(7300000+seed), random.Random(7400000+seed)
    reports, total = [], 0
    started = time.perf_counter()
    peak_points = peak_memory = peak_records = 0
    for phase, n, signal in (("initial_noise", 2048, False), ("signal", 16384, True),
                             ("interruption_noise", 8192, False), ("recovery", 4096, True)):
        losses = {name: [] for name in variants}
        curves = []
        before = variants["v2"].admissions+variants["v2"].revisions
        for index, (events, target) in enumerate(episodes(7500000+seed+total, n), 1):
            action = actions.randrange(2)
            outcome = int(action == target) if signal else int(noise.random() < .5)
            for name, core in variants.items():
                for event in events:
                    p = core.receive(event)
                losses[name].append((p[action]-outcome)**2)
                core.learn(action, outcome)
            if index%1024 == 0:
                core = variants["v2"]
                restored = AdaptiveTraceLearnerV2.restore(json.loads(json.dumps(core.checkpoint())))
                if restored.checkpoint() != core.checkpoint():
                    raise AssertionError("Research resume lost exact state")
                variants["v2"] = restored
                m = core.metrics()
                peak_points = max(peak_points, m["allocated_s2_points"])
                peak_records = max(peak_records, m["retained_records"]+m["calibration_records"])
                peak_memory = max(peak_memory, len(json.dumps(core.checkpoint()).encode()))
            if phase == "signal" and index in (512, 2048, 8192, 16384):
                curves.append({"exposure": index, "variants": {
                    name: evaluate(copy.deepcopy(core), 8000000+seed)
                    for name, core in variants.items()}})
        total += n
        result = {"phase": phase, "episodes": n,
                  "admissions_added": variants["v2"].admissions+variants["v2"].revisions-before,
                  "prequential_brier": {name: math.fsum(v)/n for name, v in losses.items()},
                  "late_half_brier": {name: math.fsum(v[n//2:])/(n//2) for name, v in losses.items()},
                  "evaluation": {name: {
                      "ordinary": evaluate(copy.deepcopy(core), 8100000+seed),
                      "long_prefix": evaluate(copy.deepcopy(core), 8200000+seed, long=True),
                      "new_context": evaluate(copy.deepcopy(core), 8300000+seed, context=4)}
                      for name, core in variants.items()},
                  "curves": curves, "metrics": variants["v2"].metrics()}
        reports.append(result)
        print("TRACE_V2_PHASE="+json.dumps({"seed": seed, **result}, sort_keys=True), flush=True)
    reversals = []
    for reversal in range(1, 7):
        reverse = bool(reversal%2)
        n = 32768
        curves = []
        before = variants["v2"].revisions
        for index, (events, target) in enumerate(episodes(9000000+seed+total, n), 1):
            core = variants["v2"]
            for event in events:
                core.receive(event)
            action = actions.randrange(2)
            core.learn(action, int(action == (1-target if reverse else target)))
            if index in (2048, 8192, 16384, 32768):
                curves.append({"exposure": index, **evaluate(copy.deepcopy(core), 9500000+seed, reverse=reverse)})
        total += n
        result = {"index": reversal, "episodes": n, "curves": curves,
                  "revisions_added": variants["v2"].revisions-before,
                  "evaluation": evaluate(copy.deepcopy(variants["v2"]), 9600000+seed, reverse=reverse),
                  "metrics": variants["v2"].metrics()}
        reversals.append(result)
        print("TRACE_V2_REVERSAL="+json.dumps({"seed": seed, **result}, sort_keys=True), flush=True)
    by_phase = {r["phase"]: r for r in reports}
    criteria = {
        "no_initial_noise_admission": by_phase["initial_noise"]["admissions_added"] == 0,
        "no_interruption_noise_admission": by_phase["interruption_noise"]["admissions_added"] == 0,
        "noise_full_brier_le_028": by_phase["interruption_noise"]["prequential_brier"]["v2"] <= .28,
        "noise_late_brier_le_027": by_phase["interruption_noise"]["late_half_brier"]["v2"] <= .27,
        "protected_weights_can_be_revised": variants["v2"].revisions > 0}
    for phase in ("signal", "interruption_noise", "recovery"):
        for kind in ("ordinary", "long_prefix", "new_context"):
            score = by_phase[phase]["evaluation"]["v2"][kind]
            criteria[phase+"_"+kind+"_accuracy_ge_095"] = score["policy_accuracy"] >= .95
            if phase == "recovery":
                criteria[phase+"_"+kind+"_brier_le_002"] = score["brier"] <= .02
    for result in reversals:
        criteria[f"reversal_{result['index']}_accuracy_ge_095"] = result["evaluation"]["policy_accuracy"] >= .95
    return {"seed": seed, "episodes": total, "phases": reports, "reversals": reversals,
            "criteria": criteria, "research_pass": all(criteria.values()),
            "max_sampled_s2_points": peak_points, "max_sampled_retained_records": peak_records,
            "max_sampled_checkpoint_bytes": peak_memory, "seconds": time.perf_counter()-started}


def engineering():
    from first_piece.trace_service import AdaptiveTraceService
    from first_piece.adaptive_trace_v2 import AdaptiveTraceLearnerV2
    from first_piece.tests.test_trace_v2 import feed_wire
    from first_piece.integration_probe import agent_proposal, observed_receipt
    from validation.readiness_probe import episodes
    direct, service = AdaptiveTraceLearnerV2(21), AdaptiveTraceService(seed=21)
    actions = random.Random(12345)
    sequence = ticks = units = 0
    peak = 0.0
    resumed = set()
    started = time.perf_counter()
    for i, (events, target) in enumerate(episodes(100100, 8192), 1):
        for event in events:
            expected = direct.receive(event)
        p, sequence = feed_wire(service, events, sequence)
        if expected != [f["distribution"]["parameters"]["p"] for f in p["forecasts"]]:
            raise AssertionError(f"Service forecast differs at {i}")
        action = actions.randrange(2)
        outcome = int(action == target)
        direct.learn(action, outcome)
        request = service.register_action(agent_proposal(p, action), executor_id="probe:executor")
        receipt = observed_receipt(request, outcome)
        service.begin_receipt(receipt)
        while service._work is not None:
            w = service._work
            key = (w.phase, None if w.fit is None else (w.fit.phase, w.fit.mean_group, w.fit.epoch, w.fit.bank))
            if key not in resumed:
                service = AdaptiveTraceService.restore(json.loads(json.dumps(service.checkpoint())))
                resumed.add(key)
            t = time.perf_counter()
            result = service.advance(128)
            peak = max(peak, time.perf_counter()-t)
            ticks += 1
            units += result["consumed_units"]
            if result["consumed_units"] > 128:
                raise AssertionError("Quota exceeded")
        if i%1024 == 0:
            if direct.checkpoint() != service._adapter._learner.checkpoint():
                raise AssertionError(f"Service state differs at {i}")
            print("TRACE_V2_PARITY_PROGRESS="+str(i), flush=True)
    before = service.checkpoint()
    if service.submit_receipt(receipt)["model_revision"] != 8192 or before != service.checkpoint():
        raise AssertionError("Duplicate learned twice")
    return {"episodes": 8192, "exact_forecasts_and_checkpoints": True,
            "restored_phase_keys": sorted(map(str, resumed)), "quota": 128,
            "ticks": ticks, "work_units": units, "max_tick_seconds": peak,
            "seconds": time.perf_counter()-started, "metrics": direct.metrics()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply")
    parser.add_argument("--out", default="trace-v2.json")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if args.apply:
        apply_bundle(args.apply)
        return
    report = {"protocol": 2, "base": BASE, "os": platform.system(),
              "python": platform.python_version(),
              "candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "cases": {}, "errors": {}}
    cases = [("engineering", engineering)]
    if not args.quick:
        cases += [(f"representation_seed_{s}", lambda seed=s: representation(seed)) for s in range(3)]
    for name, fn in cases:
        try:
            report["cases"][name] = fn()
        except Exception:
            report["errors"][name] = traceback.format_exc()
            print("TRACE_V2_ERROR="+json.dumps({name: report["errors"][name]}), flush=True)
    report["engineering_pass"] = not report["errors"]
    report["research_pass"] = not args.quick and all(report["cases"].get(
        f"representation_seed_{s}", {}).get("research_pass", False) for s in range(3))
    Path(args.out).write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print("TRACE_V2_FULL_JSON="+json.dumps(report, sort_keys=True), flush=True)
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
