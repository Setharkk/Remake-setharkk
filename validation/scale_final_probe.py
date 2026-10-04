"""Fresh evaluation and independent random-outcome control after source freeze."""
import argparse
import copy
import json
import math
from pathlib import Path
import random

from first_piece.scale_run import SCALES, evaluation, observe, check_bounds
from first_piece.scale_world import ScaleWorld
from first_piece.shared import SharedLearner


def noise_control(seed, *, n=20000, eval_n=1024):
    world = ScaleWorld(6100 + seed, n_symbols=32, n_contexts=4, n_actions=4)
    model = SharedLearner(8100 + seed, max_symbols=32, max_tasks=4)
    rng = random.Random(5100 + seed)
    for i in range(n):
        events, ignored = world.episode(i % 4)
        observe(model, events)
        action = rng.randrange(4)
        independent_target = rng.randrange(4)
        model.learn(action, int(action == independent_target))
    check_bounds(model)
    snapshot = model.checkpoint()
    inputs = copy.deepcopy(world)
    inputs.rng = random.Random(42000000 + seed)
    outcomes = random.Random(43000000 + seed)
    scores = {k: {"correct": 0, "brier_sum": 0.0} for k in ("full", "matched_control")}
    for i in range(eval_n):
        events, ignored = inputs.episode(i % 4)
        full = observe(model, events)
        e = model.episode
        control = [model.baseline.probability(a, e["coin"]) for a in range(4)]
        target = outcomes.randrange(4)
        for name, p in (("full", full), ("matched_control", control)):
            scores[name]["correct"] += max(range(4), key=p.__getitem__) == target
            scores[name]["brier_sum"] += math.fsum((v - int(a == target)) ** 2 for a, v in enumerate(p)) / 4
        model.finish_evaluation()
    # Input RNG and ephemeral episode state may advance, never neural state.
    if model.active.checkpoint() != snapshot["active"] or model.neural_updates != snapshot["neural_updates"]:
        raise AssertionError("Noise evaluation trained the model")
    result = {"seed": seed, "training_interactions": n, "chance_success": .25,
              "constant_predictor_brier": .1875, "metrics": model.metrics(),
              "scores": {k: {"episodes": eval_n, "policy_success": v["correct"] / eval_n,
                             "brier": v["brier_sum"] / eval_n} for k, v in scores.items()}}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    states = Path(args.states)
    rows = []
    for scale, (symbols, contexts, actions) in SCALES.items():
        for seed in (0, 1, 2):
            world = ScaleWorld(1300 + seed, n_symbols=symbols, n_contexts=contexts, n_actions=actions)
            for phase in ("before", "after"):
                model = SharedLearner.restore(json.loads(states.joinpath(f"{scale}-{seed}-{phase}.json").read_text(encoding="utf-8")))
                before = model.checkpoint()
                for name, slots in (("context_zero", [0]), ("other_contexts", range(1, contexts)), ("new_context", [contexts])):
                    value = evaluation(model, world, seed=40000000 + len(rows),
                                       changed=phase == "after", n=1024, slots=slots)
                    rows.append({"scale": scale, "seed": seed, "phase": phase, "group": name, "scores": value})
                if before != model.checkpoint():
                    raise AssertionError("Fresh holdout changed the input model")
    holdout = {"training_interactions": 0, "neural_updates": 0, "episodes_per_group": 1024,
               "total_evaluation_episodes": len(rows) * 1024, "seed_base": 40000000, "reports": rows}
    noise = [noise_control(seed) for seed in (0, 1, 2)]
    result = {"fresh_holdout": holdout, "independent_noise_control": noise,
              "noise_training_interactions": sum(r["training_interactions"] for r in noise)}
    Path(args.out).write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    print("SCALE_FRESH_JSON=" + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
