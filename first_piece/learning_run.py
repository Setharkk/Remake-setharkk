"""Measured learning, ablation, transfer, retention and exact resume checks."""
import argparse
import copy
import json
import math
import random
import time
from pathlib import Path

from .audit import _write_json
from .learner import DistinctionLearner
from .streaming import StreamingWorld


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


def evaluate(learner, ablated, *, seed, rule, phase, mode, task=0, n=256):
    full = DistinctionLearner.restore(learner.checkpoint())
    without = DistinctionLearner.restore(ablated.checkpoint())
    amnesia_state = learner.checkpoint()
    amnesia_state["config"]["retain_memory"] = False
    amnesia = DistinctionLearner.restore(amnesia_state)
    models = {"full": full, "without_distinction": without, "without_memory": amnesia}
    before = {name: copy.deepcopy(m.tasks) for name, m in models.items()}
    world = StreamingWorld(seed, rule, phase, mode, task)
    actions = random.Random(seed + 9000003)
    metrics = {name: {"brier": 0.0, "nll": 0.0, "policy_success": 0.0} for name in models}
    for _ in range(n):
        while True:
            event = world.next_event()
            probabilities = {name: m.receive(event) for name, m in models.items()}
            if event["kind"] == "surface":
                break
        state = world.checkpoint()
        action = actions.randrange(2)
        outcome = world.act(action)
        for name, m in models.items():
            p = probabilities[name][action]
            metrics[name]["brier"] += (p - outcome)**2
            observed = max(1e-12, p if outcome else 1 - p)
            metrics[name]["nll"] -= math.log(observed)
            greedy = int(probabilities[name][1] > probabilities[name][0])
            metrics[name]["policy_success"] += StreamingWorld.restore(state).act(greedy)
            m.finish_evaluation()
    # Evaluate only clones; training counters and all learned models are unchanged.
    for name, m in models.items():
        for task_id, old in before[name].items():
            if m.tasks[task_id]["steps"] != old["steps"]:
                raise AssertionError("Evaluation changed training exposure")
            for key in ("active", "candidate", "control"):
                prior, after = old[key], m.tasks[task_id][key]
                if prior is not None and prior.checkpoint() != after.checkpoint():
                    raise AssertionError("Evaluation changed learned parameters")
    return {
        "episodes": n, "phase": phase, "mode": mode, "task": task,
        "random_action_results": n, "simulated_policy_actions": 3 * n,
        "models": {name: {key: value / n for key, value in scores.items()}
                   for name, scores in metrics.items()},
    }


def _paired_train(full, ablated, world, rng, n):
    for _ in range(n):
        episode(world, (full, ablated), rng.randrange(2))
    if full.metrics()["neural_updates"] != ablated.metrics()["neural_updates"]:
        raise AssertionError("Ablation training update budgets differ")


def resume_probe():
    full = DistinctionLearner(37)
    world = StreamingWorld(39, rule=1, mode="noise")
    actions = random.Random(41)
    _paired = [full]
    for _ in range(400):
        episode(world, _paired, actions.randrange(2))
    for _ in range(2):
        full.receive(world.next_event())
    stored = json.loads(json.dumps({"learner": full.checkpoint(), "world": world.checkpoint()}))
    restored = DistinctionLearner.restore(stored["learner"])
    recovered_world = StreamingWorld.restore(stored["world"])
    for i in range(64):
        while True:
            original_event, restored_event = world.next_event(), recovered_world.next_event()
            if original_event != restored_event:
                raise AssertionError("Restored environment diverged")
            if full.receive(original_event) != restored.receive(restored_event):
                raise AssertionError("Restored prediction diverged")
            if original_event["kind"] == "surface":
                break
        action = i % 2
        outcome = world.act(action)
        if outcome != recovered_world.act(action):
            raise AssertionError("Restored outcome diverged")
        full.learn(action, outcome)
        restored.learn(action, outcome)
    if full.checkpoint() != restored.checkpoint() or world.checkpoint() != recovered_world.checkpoint():
        raise AssertionError("Restored learning state diverged")
    return {"exact_json_resume": True, "phase": "frozen_validation_with_pending_events",
            "continued_interactions": 64, "learner_rng_and_world_rng_restored": True}


def run_condition(seed, mode, directory):
    full = DistinctionLearner(seed + 100003)
    ablated = DistinctionLearner(seed + 100003, allow_distinctions=False)
    rule = seed % 2
    world = StreamingWorld(seed, rule, mode=mode)
    actions = random.Random(seed + 200003)
    checkpoints = []
    previous = 0
    started = time.perf_counter()
    for horizon in (100, 1000, 10000):
        _paired_train(full, ablated, world, actions, horizon - previous)
        previous = horizon
        scores = evaluate(
            full, ablated, seed=10000000 + 100 * seed + horizon,
            rule=rule, phase="acquisition", mode=mode,
        )
        checkpoints.append({
            "training_interactions": horizon, "elapsed_seconds": time.perf_counter() - started,
            "learner": full.metrics(), "ablation": ablated.metrics(), "evaluation": scores,
        })
        # One atomic file keeps both learners, environment, action RNG and
        # evaluated checkpoints together. It is a full research-run state;
        # a automatic resume CLI is deliberately not claimed here.
        _write_json(directory / "checkpoint.json", {
            "format": 1, "seed": seed, "mode": mode, "phase": "task0",
            "training_interactions": horizon, "checkpoints": checkpoints,
            "learner": full.checkpoint(), "ablation": ablated.checkpoint(),
            "world": world.checkpoint(), "actions_rng": actions.getstate(),
            "status": "running",
        })
    extras = {}
    total = 10000
    if mode == "structured":
        extras["transfer_before_other_task"] = evaluate(
            full, ablated, seed=20000000 + seed, rule=rule,
            phase="transfer", mode="structured", n=1024,
        )
        other_world = StreamingWorld(seed + 500003, rule=1 - rule, mode="structured", task=1)
        _paired_train(full, ablated, other_world, actions, 10000)
        total += 10000
        extras["retention_after_other_task"] = evaluate(
            full, ablated, seed=30000000 + seed, rule=rule,
            phase="transfer", mode="structured", task=0, n=1024,
        )
        extras["new_task_transfer"] = evaluate(
            full, ablated, seed=40000000 + seed, rule=1 - rule,
            phase="transfer", mode="structured", task=1, n=1024,
        )
        world = other_world
    result = {"seed": seed, "mode": mode, "training_interactions": total,
              "checkpoints": checkpoints, "extra_evaluations": extras,
              "final_learner": full.metrics(), "final_ablation": ablated.metrics()}
    _write_json(directory / "checkpoint.json", {
        "format": 1, "seed": seed, "mode": mode, "status": "completed",
        "phase": "task1" if mode == "structured" else "task0",
        "training_interactions": total, "results": result,
        "learner": full.checkpoint(), "ablation": ablated.checkpoint(),
        "world": world.checkpoint(), "actions_rng": actions.getstate(),
    })
    _write_json(directory / "results.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if any(s < 0 for s in args.seeds) or len(set(args.seeds)) != len(args.seeds) or len(args.seeds) * 4 * 3 * 2 > 1000:
        parser.error("Distinct nonnegative seeds and at most 1000 planned gate comparisons required")
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=False)
    _write_json(root / "config.json", {
        "seeds": args.seeds, "training_horizons": [100, 1000, 10000],
        "modes": ["structured", "noise", "action_only"], "warmup": 256,
        "validation_horizons": [128, 1024, 4096], "comparison_limit": 1000,
        "max_tasks": 2, "max_units": 4, "planned_gate_comparisons": len(args.seeds) * 4 * 3 * 2,
        "geometry": "S^2, curvature +1, geodesic readout and Riemannian exponential update",
        "primary_task_evaluation_episodes": 256, "transfer_evaluation_episodes": 1024,
        "task1_training_interactions": 10000,
        "scope": "Bounded token-presence hypotheses and task-indexed memory; not general autonomous cognition",
    })
    rows = []
    for seed in args.seeds:
        for mode in ("structured", "noise", "action_only"):
            directory = root / f"seed_{seed}" / mode
            directory.mkdir(parents=True)
            rows.append(run_condition(seed, mode, directory))
    result = {"learner_implemented": True, "non_euclidean_parameter_manifold": "product of S^2",
              "conditions": rows, "resume": resume_probe()}
    _write_json(root / "summary.json", result)
    print("FIRST_PIECE_LEARNING_JSON=" + json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
