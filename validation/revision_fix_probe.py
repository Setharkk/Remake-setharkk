"""Apply a review candidate and compare defects, exact state and CPU costs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
import types

BASE_COMMIT = "3bc75f676b3b93244e099f10db948d1a6be71f85"

def apply_bundle(path):
    files = json.loads(Path(path).read_text(encoding="utf-8"))["files"]
    blobs = {}
    for name, content in files.items():
        if not (name.startswith("first_piece/") or name == "validation/plastic_revision_probe.py"):
            raise ValueError("Candidate path outside audited engine")
        target = Path(name)
        if ".." in target.parts or target.is_absolute():
            raise ValueError("Invalid candidate path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        raw = content.encode("utf-8")
        blobs[name] = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    print("CANDIDATE_BLOBS_JSON=" + json.dumps(blobs, sort_keys=True), flush=True)

def baseline():
    package = types.ModuleType("_review_baseline")
    package.__path__ = []
    sys.modules[package.__name__] = package
    order = ("world", "criterion", "spherical", "shared", "shared_state", "renewable",
             "consolidated", "consolidated_state", "calibrated", "plastic_revision",
             "plastic_revision_state", "learner", "adapter", "shared_adapter",
             "renewable_adapter", "consolidated_adapter", "calibrated_adapter",
             "plastic_revision_adapter")
    modules = {}
    for name in order:
        source = subprocess.run(["git", "show", f"{BASE_COMMIT}:first_piece/{name}.py"],
                                check=True, capture_output=True, text=True, encoding="utf-8").stdout
        module = types.ModuleType(f"{package.__name__}.{name}")
        module.__package__, module.__file__ = package.__name__, f"{BASE_COMMIT}:first_piece/{name}.py"
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        modules[name] = module
    return modules

def canonical(core):
    data = core.checkpoint()
    data.pop("format")
    data.pop("implementation")
    for search in data["searches"]:
        search["elapsed_seconds"] = 0
        if search.get("validation", {}).get("purpose") == "confidence":
            for field in ("eligible_features", "pooled_features", "hypotheses_examined"):
                search[field] = 0
    return data

def feed(core, events, action, outcome):
    for event in events:
        probabilities = core.receive(event)
    return probabilities, core.learn(action, outcome)

def paired_continuation(old):
    from first_piece.plastic_revision import PlasticRevisionLearner
    from first_piece.scale_world import ScaleWorld
    before = old["plastic_revision"].PlasticRevisionLearner(100, max_tasks=17, max_symbols=64)
    after = PlasticRevisionLearner(100, max_tasks=17, max_symbols=64)
    world = ScaleWorld(400, n_symbols=64, n_contexts=16)
    actions, labels = random.Random(8200000), random.Random(8300000)
    max_gap, pending_import = 0.0, False
    for i in range(32000):
        events, target = world.episode(i % 16)
        action = actions.randrange(4)
        outcome = int(labels.random() < .25) if i < 16000 else int(action == target)
        p, served = feed(before, events, action, outcome)
        q, result = feed(after, events, action, outcome)
        max_gap = max(max_gap, max(abs(a-b) for a,b in zip(p,q)), abs(served-result))
        if not pending_import and before.trial is not None and before.trial["n"] == 32:
            imported = PlasticRevisionLearner.restore(
                PlasticRevisionLearner.from_plastic_revision_checkpoint(before.checkpoint()))
            if canonical(imported) != canonical(before):
                raise AssertionError("Format-7 import changed predictive state")
            pending_import = True
        if (i+1) % 4000 == 0 and canonical(before) != canonical(after):
            raise AssertionError("Predictive state diverged at " + str(i+1))
    if max_gap != 0 or not pending_import:
        raise AssertionError("Forecast parity or pending import failed")
    refinements = [s for s in after.searches if s["validation"]["purpose"] == "confidence"]
    for search in refinements:
        if any(search[key] for key in ("eligible_features", "pooled_features", "hypotheses_examined")):
            raise AssertionError("Fixed-program refinement still searches alternatives")
    return {"labels": 32000, "max_forecast_difference": max_gap,
            "identical_predictive_state_except_declared_journal_work": canonical(before) == canonical(after),
            "pending_format7_import_exact": pending_import,
            "confidence_refinements_with_zero_alternative_search": len(refinements)}

def bridge_benchmark(old):
    from first_piece.plastic_revision import PlasticRevisionLearner
    from first_piece.plastic_revision_adapter import PlasticRevisionAdapter
    from first_piece.scale_world import ScaleWorld
    from first_piece.tests.test_shared import train, wire_symbol
    from first_piece.integration_probe import agent_proposal, observed_receipt
    classes = {"before": (old["plastic_revision"].PlasticRevisionLearner,
                          old["plastic_revision_adapter"].PlasticRevisionAdapter),
               "after": (PlasticRevisionLearner, PlasticRevisionAdapter)}
    sources = {name: train(core(100, max_tasks=17, max_symbols=64),
                           ScaleWorld(400, n_symbols=64, n_contexts=16), 6000)
               for name, (core, adapter) in classes.items()}
    world, actions = ScaleWorld(400, n_symbols=64, n_contexts=16), random.Random(281)
    world.rng = random.Random(195)
    inputs = []
    for i in range(96):
        events, target = world.episode(i % 16)
        action = actions.randrange(4)
        inputs.append((events, action, int(action == target)))
    samples, parity = [], []
    for sample in range(3):
        times, final = {}, {}
        for name in (("before", "after") if sample % 2 == 0 else ("after", "before")):
            cls, adapter_cls = classes[name]
            checkpoint = sources[name].checkpoint()
            direct = cls.restore(checkpoint)
            adapter = adapter_cls(learner_options={"max_tasks": 17, "max_symbols": 64})
            adapter._learner = cls.restore(checkpoint)
            adapter._revision = sources[name].steps
            adapter._slots = {f"ctx:{slot}": slot for slot in sources[name].tasks}
            start = time.perf_counter()
            sequence = 0
            for events, action, outcome in inputs:
                for event in events:
                    prediction = adapter.submit_observation(wire_symbol(
                        sequence, "sealed" if event["kind"] == "surface" else event["token"],
                        context=f"ctx:{event['task']}", end=event["kind"] == "surface"))
                    sequence += 1
                request = adapter.register_action(agent_proposal(prediction, action), executor_id="executor")
                adapter.submit_receipt(observed_receipt(request, outcome))
            times[name] = time.perf_counter()-start
            for events, action, outcome in inputs:
                feed(direct, events, action, outcome)
            parity.append(canonical(direct) == canonical(adapter._learner))
            final[name] = canonical(adapter._learner)
        parity.append(final["before"] == final["after"])
        samples.append(times)
    medians = {name: statistics.median(s[name] for s in samples) for name in classes}
    if not all(parity):
        raise AssertionError("Wire benchmark changed predictive state")
    fit_times = {}
    for name, core in sources.items():
        fit_times[name] = []
        for _ in range(3):
            child = core._transaction_copy()
            start = time.perf_counter()
            child._start_trial(None)
            fit_times[name].append(time.perf_counter()-start)
            type(core).restore(child.checkpoint())
    return {"episodes": len(inputs), "samples": samples, "median_seconds": medians,
            "median_ms_per_episode": {name: value*1000/len(inputs) for name,value in medians.items()},
            "wire_speedup": medians["before"]/medians["after"], "all_predictive_states_equal": all(parity),
            "full_fit_rows": sum(len(t["records"]) for t in sources["after"].tasks.values()),
            "fit_gradients_per_attempt": 2*4*sum(len(t["records"]) for t in sources["after"].tasks.values()),
            "full_fit_seconds": fit_times}

def dense_benchmark(old):
    from first_piece.shared import SharedLearner
    from first_piece.scale_world import ScaleWorld
    rng = random.Random(293)
    rows = []
    core = SharedLearner(max_tasks=17, max_symbols=64, min_records=64)
    for i in range(512):
        tokens = [f"dense:{j}" for j in range(64)]
        rng.shuffle(tokens)
        for token in tokens:
            core.receive({"kind": "token", "token": token, "task": i % 16})
        episode = core.episode
        rows.append((i % 16, episode["mask"], episode["before"], episode["coin"], i % 4, i % 2))
        core.receive({"kind": "surface", "surface": "sealed", "task": i % 16})
        core.finish_evaluation()
    engines = {"before": old["shared"].SharedLearner(max_tasks=17, max_symbols=64),
               "after": SharedLearner(max_tasks=17, max_symbols=64)}
    samples, programs = [], {}
    for sample in range(5):
        times = {}
        for name in (("before", "after") if sample % 2 == 0 else ("after", "before")):
            engine = engines[name]
            start = time.perf_counter()
            program = engine._search(rows)
            times[name] = time.perf_counter()-start
            programs[name] = program
            engine.searches.clear()
        samples.append(times)
    if programs["before"] != programs["after"]:
        raise AssertionError("Dense search changed program")
    median = {name: statistics.median(s[name] for s in samples) for name in engines}
    return {"rows":512, "distinct_symbols_per_episode":64, "samples":samples,
            "median_seconds":median, "speedup":median["before"]/median["after"],
            "selected_programs":programs}

def corrected_reproductions():
    from validation.plastic_revision_review import fork_isolation, mean_cut_locus, historical_restore, confirmed_deadline
    results = {"transaction_isolation": fork_isolation(), "mean_optimizer_domain": mean_cut_locus(),
               "historical_restore": historical_restore(), "confirmed_deadline": confirmed_deadline()}
    isolated = results["transaction_isolation"]
    if (isolated["original_checkpoint_changed_after_unpublished_child_learn"] or
            isolated["adapter_checkpoint_changed_after_failed_receipt"] or
            not isolated["adapter_still_restorable"]):
        raise AssertionError("Transaction defect persists")
    if not results["mean_optimizer_domain"]["replay_update_succeeds"]:
        raise AssertionError("Mean defect persists")
    if any(r["forged_neural_update_total_accepted"] for r in results["historical_restore"].values()):
        raise AssertionError("Historical restore defect persists")
    if not results["confirmed_deadline"]["criteria_failures"]:
        raise AssertionError("Deadline defect persists")
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.apply:
        apply_bundle(args.apply)
        return
    if args.out is None:
        parser.error("--out required for validation")
    old = baseline()
    result = {"baseline_commit": BASE_COMMIT,
              "execution_commit": subprocess.run(["git","rev-parse","HEAD"], check=True,
                                                 capture_output=True,text=True).stdout.strip(),
              "runner":platform.system(), "python":platform.python_version()}
    failures = []
    for name, fn in (("corrected_reproductions", corrected_reproductions),
                     ("paired_continuation", lambda: paired_continuation(old)),
                     ("bridge_benchmark", lambda: bridge_benchmark(old)),
                     ("dense_benchmark", lambda: dense_benchmark(old))):
        try:
            result[name] = fn()
        except Exception as error:
            import traceback
            result[name] = {"error":type(error).__name__+": "+str(error),
                            "traceback":traceback.format_exc()}
            failures.append(name)
        print("REVISION_FIX_CASE " + name + " " + json.dumps(result[name], sort_keys=True), flush=True)
    result["failures"] = failures
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REVISION_FIX_FULL_JSON=" + json.dumps(result, sort_keys=True), flush=True)
    if failures:
        raise SystemExit("Correction validation failed: " + ", ".join(failures))

if __name__ == "__main__":
    main()
