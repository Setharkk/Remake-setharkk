"""Paired temporal learning, hidden changes, retention and checkpoint evidence."""
import argparse
import copy
import json
import math
from pathlib import Path
import random
import time

from .learner import DistinctionLearner
from .spherical import norm
from .temporal import TemporalLearner, feature_description
from .temporal_world import TemporalWorld

HORIZONS = (100, 1000, 10000)
SCENARIOS = ("stationary", "inversion", "relation_switch", "noise", "action_only")


def episode(world, learners, action):
    while True:
        event = world.next_event()
        predictions = [learner.receive(event) for learner in learners]
        if event["kind"] == "surface":
            break
    outcome = world.act(action)
    for learner in learners:
        learner.learn(action, outcome)
    return predictions, outcome


def evaluate(learner, presence=None, *, seed=0, rule=0, pair=(0, 1),
             phase="acquisition", mode="structured", task=0, n=256):
    full = TemporalLearner.restore(learner.checkpoint())
    baseline = TemporalLearner.restore(learner.checkpoint())
    baseline.config["use_structure"] = False
    erased = TemporalLearner.restore(learner.checkpoint())
    models = {"full": full, "without_order": baseline, "order_erased": erased}
    if presence is not None:
        models["presence_reference"] = DistinctionLearner.restore(presence.checkpoint())
    before = learner.checkpoint()
    world = TemporalWorld(seed, rule=rule, pair=pair, phase=phase, mode=mode, task=task)
    labels_rng = random.Random(seed + 400001)
    totals = {name: {"brier": 0., "nll": 0., "policy_success": 0.} for name in models}
    for _ in range(n):
        while True:
            event = world.next_event()
            probabilities = {name: model.receive(event) for name, model in models.items()}
            if event["kind"] == "surface":
                erased.episode["before"] = 0
                probabilities["order_erased"] = erased.pending_probabilities()
                break
        # Counterfactual policies share the same episode and outcome-noise draw.
        pending = world.checkpoint()
        for name, p in probabilities.items():
            action = int(p[1] > p[0])
            totals[name]["policy_success"] += TemporalWorld.restore(pending).act(action)
        action = labels_rng.randrange(2)
        outcome = world.act(action)
        for name, model in models.items():
            p = probabilities[name][action]
            totals[name]["brier"] += (p - outcome) ** 2
            totals[name]["nll"] -= math.log(max(1e-12, p if outcome else 1 - p))
            model.finish_evaluation()
    assert learner.checkpoint() == before
    return {"episodes": n, "phase": phase, "mode": mode, "task": task,
            "counterfactual_policy_actions": n * len(models),
            "models": {name: {metric: value / n for metric, value in totals[name].items()}
                       for name in models}}


def bounds(learner):
    metrics = learner.metrics()
    assert metrics["stored_neural_points"] <= 16 * learner.config["max_tasks"]
    assert metrics["record_rows"] <= learner.config["warmup"] * learner.config["max_tasks"]
    assert metrics["validation_rows"] < 4096 * learner.config["max_tasks"]
    for state in learner.tasks.values():
        assert state["attempts"] <= learner.config["max_attempts"]
        assert len(state["decisions"]) <= 3 * learner.config["max_attempts"]
        for name in ("active", "baseline", "candidate", "control"):
            model = state[name]
            if model is not None:
                for row in model.points:
                    assert all(abs(norm(p) - 1) < 1e-10 for p in row)
    return metrics


def run_condition(seed, scenario, out=None):
    mode = scenario if scenario in ("noise", "action_only") else "structured"
    world = TemporalWorld(seed, mode=mode)
    learner = TemporalLearner(seed + 100003)
    presence = DistinctionLearner(seed + 100003)
    actions = random.Random(seed + 200003)
    checkpoints = []
    peak = {"stored_neural_points": 0, "record_rows": 0, "validation_rows": 0, "checkpoint_bytes": 0}
    start = time.perf_counter()
    phases = ("before",) if mode != "structured" else ("before", "after")
    retention = None
    recovery = None
    paired_budget_equal = True
    for phase_name in phases:
        if phase_name == "after":
            if scenario in ("inversion", "relation_switch"):
                before_other = learner.checkpoint()
                other = TemporalWorld(seed + 300007, rule=1, task=1)
                for _ in range(2000):
                    episode(other, [learner], actions.randrange(2))
                assert learner.checkpoint()["tasks"][0] == before_other["tasks"][0]
                retention = copy.deepcopy(learner.checkpoint()["tasks"][1])
            if scenario == "inversion":
                world.change(rule=1)
            elif scenario == "relation_switch":
                world.change(pair=(2, 3))
        for exposure in range(1, 10001):
            episode(world, [learner, presence], actions.randrange(2))
            state = learner.tasks[0]
            paired_budget_equal = paired_budget_equal and sum(map(sum, state["active"].counts)) == sum(map(sum, state["baseline"].counts))
            if exposure % 256 == 0 or exposure in HORIZONS:
                metrics = bounds(learner)
                for key in ("stored_neural_points", "record_rows", "validation_rows"):
                    peak[key] = max(peak[key], metrics[key])
                peak["checkpoint_bytes"] = max(peak["checkpoint_bytes"], len(json.dumps(learner.checkpoint()).encode("utf-8")))
            if phase_name == "after" and scenario != "stationary" and recovery is None and exposure % 256 == 0:
                probe = evaluate(learner, seed=seed + 700003 + exposure, rule=world.rule,
                                 pair=world.pair, n=128)
                score = probe["models"]["full"]
                if score["policy_success"] >= .95 and score["brier"] <= .02:
                    recovery = {"first_sampled_exposure": exposure, "sampling_interval": 256,
                                "evaluation": probe, "definition": "success >= .95 and Brier <= .02"}
            if exposure in HORIZONS:
                result = {
                    "phase": phase_name, "phase_interactions": exposure,
                    "world_interactions": world.completed,
                    "elapsed_seconds": time.perf_counter() - start,
                    "learner": bounds(learner), "presence_reference": presence.metrics(),
                    "evaluation": evaluate(learner, presence, seed=seed + 900007 + exposure + int(phase_name == "after") * 100000,
                                           rule=world.rule, pair=world.pair, mode=mode, n=512),
                }
                checkpoints.append(result)
                if out is not None:
                    snapshot = {"format": 1, "scenario": scenario, "seed": seed,
                                "phase": phase_name, "phase_interactions": exposure,
                                "learner": learner.checkpoint(), "presence_reference": presence.checkpoint(),
                                "world": world.checkpoint(), "actions_rng": actions.getstate(),
                                "measurements": checkpoints}
                    (out / f"{scenario}-seed-{seed}-{phase_name}-{exposure}.json").write_text(
                        json.dumps(snapshot, sort_keys=True) + "\n", encoding="utf-8")
        if retention is not None:
            assert learner.checkpoint()["tasks"][1] == retention
    final = bounds(learner)
    result = {"seed": seed, "scenario": scenario, "checkpoints": checkpoints,
              "training_world_interactions": world.completed,
              "other_context_training": 2000 if retention is not None else 0,
              "same_context_during_change": True,
              "matched_live_predictor_update_counts_equal": paired_budget_equal,
              "recovery": recovery, "peak_sampled_resources": peak, "final": final}
    assert paired_budget_equal
    if retention is not None:
        result["retention"] = {
            "other_context_neural_state_unchanged": True,
            "evaluation": evaluate(learner, seed=seed + 990007, rule=1, task=1,
                                   phase="transfer", n=512),
        }
    if mode == "structured":
        result["transfer"] = evaluate(learner, presence, seed=seed + 980007,
                                      rule=world.rule, pair=world.pair,
                                      phase="transfer", n=1024)
    return result


def resume_probe():
    learner, world = TemporalLearner(42), TemporalWorld(19)
    actions = random.Random(777)
    for _ in range(400):
        episode(world, [learner], actions.randrange(2))
    assert learner.tasks[0]["status"] == "validating"
    for _ in range(3):
        learner.receive(world.next_event())
    restored = TemporalLearner.restore(json.loads(json.dumps(learner.checkpoint())))
    recovered = TemporalWorld.restore(json.loads(json.dumps(world.checkpoint())))
    rng = random.Random()
    from .world import _tuples
    rng.setstate(_tuples(json.loads(json.dumps(actions.getstate()))))
    for _ in range(64):
        while True:
            event = world.next_event()
            assert event == recovered.next_event()
            assert learner.receive(event) == restored.receive(event)
            if event["kind"] == "surface":
                break
        action = actions.randrange(2)
        assert action == rng.randrange(2)
        outcome = world.act(action)
        assert outcome == recovered.act(action)
        learner.learn(action, outcome)
        restored.learn(action, outcome)
    assert learner.checkpoint() == restored.checkpoint()
    assert world.checkpoint() == recovered.checkpoint()
    return {"exact_json_resume": True, "continued_interactions": 64,
            "includes_order_memory_frozen_trial_and_action_rng": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    report = {"protocol": 1, "horizons": list(HORIZONS),
              "geometry": "product of S2", "conditions": [],
              "resume": resume_probe(),
              "unbounded_autonomy_proven": False}
    progress = out / "results.json"
    for seed in args.seeds:
        for scenario in SCENARIOS:
            report["conditions"].append(run_condition(seed, scenario, out))
            progress.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"TEMPORAL_PROGRESS seed={seed} scenario={scenario}", flush=True)
    print("FIRST_PIECE_TEMPORAL_JSON=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
