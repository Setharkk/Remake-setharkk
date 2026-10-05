"""Read-only engine audit: reproducible defects and bounded CPU profiles."""
import argparse
import copy
import cProfile
import json
import math
from pathlib import Path
import platform
import pstats
import random
import statistics
import subprocess
import time
import tracemalloc
from unittest.mock import patch

from first_piece.adapter import FirstPieceAdapter
from first_piece.integration_probe import agent_proposal, observed_receipt
from first_piece.plastic_revision import PlasticRevisionLearner
from first_piece.plastic_revision_adapter import PlasticRevisionAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.shared import SharedLearner
from first_piece.spherical import learnable_point, unit
from first_piece.tests.test_shared import train, wire_symbol
from setharkk import contracts as wire

AUDITED_COMMIT = "f6a1ea4f74ac546bed79eef562894320c358790e"


def canonical(core):
    data = core.checkpoint()
    for search in data.get("searches", []):
        search["elapsed_seconds"] = 0
    return data


def advance(core, events, action, outcome):
    for event in events:
        core.receive(event)
    return core.learn(action, outcome)


def collect_boundary():
    core = PlasticRevisionLearner(5, max_tasks=4, max_symbols=16)
    world = ScaleWorld(400, n_symbols=16, n_contexts=4)
    actions = random.Random(801)
    for index in range(2000):
        events, target = world.episode(index % 4)
        action = actions.randrange(4)
        advance(core, events, action, int(action == target))
        if core.trial is not None and core.trial["n"] == 127:
            events, target = world.episode((index + 1) % 4)
            action = actions.randrange(4)
            return core, events, action, int(action == target)
    raise AssertionError("No real validation boundary found")


def fork_isolation():
    core, events, action, outcome = collect_boundary()
    for event in events:
        core.receive(event)
    before = canonical(core)
    child = core._transaction_copy()
    shared_validation = child.searches[-1]["validation"] is core.searches[-1]["validation"]
    child.learn(action, outcome)
    after = canonical(core)
    result = {
        "shared_validation_object": shared_validation,
        "original_checkpoint_changed_after_unpublished_child_learn": before != after,
        "original_steps_before": before["steps"], "original_steps_after": after["steps"],
        "variance_keys_before": {k: sorted(v) for k, v in before["searches"][-1]["validation"]["variance_checks"].items()},
        "variance_keys_after": {k: sorted(v) for k, v in after["searches"][-1]["validation"]["variance_checks"].items()},
    }
    try:
        type(core).restore(core.checkpoint())
        result["original_still_restorable"] = True
    except Exception as error:
        result.update(original_still_restorable=False, restore_error=str(error))

    source, events, action, outcome = collect_boundary()
    adapter = PlasticRevisionAdapter(learner_options={"max_tasks": 4, "max_symbols": 16})
    adapter._learner = source
    adapter._revision = source.steps
    adapter._slots = {f"ctx:{slot}": slot for slot in sorted(source.tasks)}
    for sequence, event in enumerate(events):
        prediction = adapter.submit_observation(wire_symbol(
            sequence, "sealed" if event["kind"] == "surface" else event["token"],
            context=f"ctx:{event['task']}", end=event["kind"] == "surface"))
    request = adapter.register_action(agent_proposal(prediction, action), executor_id="audit:executor")
    checkpoint = adapter.checkpoint()
    real_counter = wire.counter

    def fail_commit(value, name, minimum=0):
        if name == "model revision":
            raise RuntimeError("injected failure after candidate.learn")
        return real_counter(value, name, minimum)

    with patch("first_piece.adapter.wire.counter", side_effect=fail_commit):
        try:
            adapter.submit_receipt(observed_receipt(request, outcome))
        except RuntimeError as error:
            result["injected_error"] = str(error)
    result["adapter_checkpoint_changed_after_failed_receipt"] = checkpoint != adapter.checkpoint()
    result["adapter_revision_unchanged"] = checkpoint["model_revision"] == adapter.checkpoint()["model_revision"]
    try:
        PlasticRevisionAdapter.restore(adapter.checkpoint())
        result["adapter_still_restorable"] = True
    except Exception as error:
        result.update(adapter_still_restorable=False, adapter_restore_error=str(error))
    return result


def mean_cut_locus():
    core = PlasticRevisionLearner(max_tasks=4, max_symbols=16)
    sources = [unit([-1, 0, .1]), unit([-1, 0, -.1])]
    for route, point in enumerate(sources):
        learnable_point(point, core.active.anchors)
        core.active.points[route][0] = point
    rows = [(0, 1, 0, coin, 0, 1) for _ in range(8) for coin in (0, 1)]
    candidate, control, report = core._initialize_banks([0], rows)
    result = {"sources_in_optimizer_domain": True, "initialization": report,
              "transferred_point": candidate.points[1][0],
              "probability": candidate.probability(0, 1)}
    try:
        candidate.update(0, 1, 1)
        result["replay_update_succeeds"] = True
    except Exception as error:
        result.update(replay_update_succeeds=False, error=str(error))
    try:
        type(candidate).restore(candidate.checkpoint())
        result["candidate_restorable"] = True
    except Exception as error:
        result.update(candidate_restorable=False, restore_error=str(error))
    return result


def historical_restore():
    from first_piece.learner import DistinctionLearner
    from first_piece.temporal import TemporalLearner
    results = {}
    for cls in (DistinctionLearner, TemporalLearner):
        core = cls()
        core.receive({"kind": "token", "token": 0, "task": 0})
        core.receive({"kind": "surface", "surface": "sealed", "task": 0})
        core.learn(0, 1)
        data = core.checkpoint()
        data["tasks"][0]["neural_updates"] += 100
        try:
            restored = cls.restore(data)
            results[cls.__name__] = {"forged_neural_update_total_accepted": True,
                                     "neural_updates": restored.metrics()["neural_updates"]}
        except Exception as error:
            results[cls.__name__] = {"forged_neural_update_total_accepted": False, "error": str(error)}
    return results


def unobserved_route():
    core = PlasticRevisionLearner(11, max_tasks=1, max_symbols=4, n_actions=2,
                                 max_features=1, fit_per_context=64,
                                 min_records=64, replay_passes=8)
    for i in range(64):
        target, action = i % 2, (i // 2) % 2
        events = [{"kind": "token", "token": "cue" if target else "other", "task": 0},
                  {"kind": "surface", "surface": "sealed", "task": 0}]
        advance(core, events, action, int(action == target))
    first = core.checkpoint()
    for i in range(1024):
        events = [{"kind": "token", "token": "cue", "task": 0},
                  {"kind": "surface", "surface": "sealed", "task": 0}]
        action = i % 2
        advance(core, events, action, int(action == 1))
        if core.admissions:
            decision = next(d for d in reversed(core.decisions) if d["decision"] == "accept")
            return {"admitted": True, "route_support": decision["route_support"],
                    "program": decision["program"],
                    "initial_program": first["trial"]["program"] if first["trial"] else None,
                    "principal_labels": decision["relevance"]["n"],
                    "has_unobserved_boolean_route": any(
                        n == 0 for n in decision["route_support"][:2**len(decision["program"])])}
    return {"admitted": False, "decisions": core.decisions}


def profile_call(fn):
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    value = fn()
    profiler.disable()
    elapsed = time.perf_counter() - started
    stats = pstats.Stats(profiler)
    rows = sorted(stats.stats.items(), key=lambda entry: entry[1][3], reverse=True)[:15]
    return value, {"profiled_seconds": elapsed, "total_calls": stats.total_calls,
                   "top_cumulative": [{"function": f"{Path(k[0]).name}:{k[1]}:{k[2]}",
                                       "primitive_calls": v[0], "calls": v[1],
                                       "self_seconds": v[2], "cumulative_seconds": v[3]}
                                      for k, v in rows]}


def measured_repetitions(fn, n):
    times = []
    for _ in range(3):
        started = time.perf_counter()
        for i in range(n):
            fn()
        times.append((time.perf_counter()-started)/n)
    return {"repetitions_per_sample": n, "samples": times,
            "median_seconds_per_call": statistics.median(times)}


def dense_search(symbols, count):
    core = SharedLearner(max_tasks=17, max_symbols=symbols, min_records=64)
    rng = random.Random(293)
    rows = []
    for i in range(count):
        tokens = [f"dense:{j}" for j in range(symbols)]
        rng.shuffle(tokens)
        for token in tokens:
            core.receive({"kind": "token", "token": token, "task": i % 16})
        episode = core.episode
        rows.append((i % 16, episode["mask"], episode["before"], episode["coin"], i % 4, i % 2))
        core.receive({"kind": "surface", "surface": "sealed", "task": i % 16})
        core.finish_evaluation()
    _, profile = profile_call(lambda: core._search(rows))
    return {"symbols": symbols, "rows": count, "tokens_per_episode": symbols,
            "true_order_bits_total": sum(row[2].bit_count() for row in rows),
            "search": core.searches[-1], "profile": profile}


def bridge_profile():
    core = train(PlasticRevisionLearner(100, max_tasks=17, max_symbols=64),
                 ScaleWorld(400, n_symbols=64, n_contexts=16), 6000)
    if core.episode["phase"] != "idle":
        raise AssertionError("Profile source is not idle")
    world = ScaleWorld(400, n_symbols=64, n_contexts=16)
    world.rng = random.Random(195)
    inputs, actions = [], random.Random(281)
    for i in range(96):
        events, target = world.episode(i % 16)
        action = actions.randrange(4)
        inputs.append((events, action, int(action == target)))
    before = canonical(core)
    direct = type(core).restore(core.checkpoint())
    adapter = PlasticRevisionAdapter(learner_options={"max_tasks": 17, "max_symbols": 64})
    adapter._learner = type(core).restore(core.checkpoint())
    adapter._revision = core.steps
    adapter._slots = {f"ctx:{slot}": slot for slot in sorted(core.tasks)}

    def run_direct():
        for events, action, outcome in inputs:
            advance(direct, events, action, outcome)

    def run_wire():
        sequence = 0
        for events, action, outcome in inputs:
            for event in events:
                prediction = adapter.submit_observation(wire_symbol(
                    sequence, "sealed" if event["kind"] == "surface" else event["token"],
                    context=f"ctx:{event['task']}", end=event["kind"] == "surface"))
                sequence += 1
            request = adapter.register_action(agent_proposal(prediction, action), executor_id="audit:executor")
            adapter.submit_receipt(observed_receipt(request, outcome))

    _, direct_profile = profile_call(run_direct)
    _, wire_profile = profile_call(run_wire)
    return {"episodes": len(inputs), "source_steps": core.steps,
            "fit_rows": sum(len(t["records"]) for t in core.tasks.values()),
            "protected_bank": core._protected is not None,
            "calibration_cache": core.metrics()["calibration_probability_cache"],
            "direct": direct_profile, "adapter": wire_profile,
            "direct_wire_state_equal": canonical(direct) == canonical(adapter._learner),
            "source_unchanged": before == canonical(core),
            "fork": measured_repetitions(core._transaction_copy, 50),
            "checkpoint": measured_repetitions(core.checkpoint, 10),
            "restore": measured_repetitions(lambda: type(core).restore(core.checkpoint()), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = {"audited_commit": AUDITED_COMMIT,
              "probe_commit": subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                            capture_output=True, text=True).stdout.strip(),
              "runner": platform.system(), "python": platform.python_version(),
              "reproductions": {}, "profiles": {}}
    probes = {"transaction_isolation": fork_isolation, "mean_optimizer_domain": mean_cut_locus,
              "historical_restore": historical_restore, "unobserved_route": unobserved_route}
    for name, probe in probes.items():
        try:
            result["reproductions"][name] = probe()
        except Exception as error:
            result["reproductions"][name] = {"probe_error": type(error).__name__ + ": " + str(error)}
        print("REVIEW_PROBE " + name + " " + json.dumps(result["reproductions"][name], sort_keys=True), flush=True)
    for name, probe in {"bridge": bridge_profile,
                        "dense16": lambda: dense_search(16, 512),
                        "dense64": lambda: dense_search(64, 512)}.items():
        try:
            result["profiles"][name] = probe()
        except Exception as error:
            result["profiles"][name] = {"probe_error": type(error).__name__ + ": " + str(error)}
        print("REVIEW_PROFILE " + name + " " + json.dumps(result["profiles"][name], sort_keys=True), flush=True)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REVIEW_FULL_JSON=" + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
