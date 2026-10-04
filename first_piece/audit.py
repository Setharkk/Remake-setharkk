"""Audit the laboratory and evidence gate, without training a learner."""
import argparse
import json
import math
import random
import time
from pathlib import Path

from .world import HistoryWorld
from .criterion import evaluate_distinction


def audit_condition(seed, phase, noise, horizons, directory):
    world = HistoryWorld(seed, rule=seed % 2, phase=phase, noise=noise)
    actions = random.Random(seed + 2000003)
    outcomes, groups, proposals = [], [], []
    histories = set()
    oracle_correct = 0
    snapshots = []
    started = time.perf_counter()
    with (directory / "observations.jsonl").open("w", encoding="utf-8") as stream:
        for step in range(1, max(horizons) + 1):
            view = world.observe()
            action = actions.randrange(2)
            # Positive control knows the rule. It is explicitly not a trained model.
            cue = next(token for token in view["history"] if token in (0, 1))
            expected = int(action == (cue ^ world.rule))
            proposal = .99 if expected else .01
            outcome = world.act(action)
            stream.write(json.dumps({**view, "action": action, "outcome": outcome}) + "\n")
            outcomes.append(outcome)
            groups.append(cue)
            proposals.append(proposal)
            histories.add(tuple(view["history"]))
            oracle_correct += expected == outcome
            if step in horizons:
                evidence = evaluate_distinction(
                    [.5] * step, proposals, outcomes, groups,
                    comparison_limit=1000,
                )
                snapshots.append({
                    "interactions": step, "distinct_histories": len(histories),
                    "elapsed_seconds": time.perf_counter() - started,
                    "constant_predictor_brier": .25,
                    "constant_predictor_nll": math.log(2),
                    "oracle_accuracy": oracle_correct / step, **evidence,
                })
    (directory / "world_checkpoint.json").write_text(
        json.dumps(world.checkpoint()), encoding="utf-8"
    )
    return {"seed": seed, "phase": phase, "noise": noise, "checkpoints": snapshots}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    parser.add_argument("--horizons", type=int, nargs="+", default=[100, 1000, 10000])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if (
        any(seed < 0 for seed in args.seeds) or len(set(args.seeds)) != len(args.seeds)
        or any(n < 1 for n in args.horizons) or args.horizons != sorted(set(args.horizons))
        or len(args.seeds) * 4 * len(args.horizons) > 1000
    ):
        parser.error("Distinct nonnegative seeds, increasing positive horizons and at most 1000 comparisons required")
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=False)
    (root / "config.json").write_text(json.dumps({
        **vars(args), "scope": "Laboratory and frozen-oracle evidence gate; no learner trained",
        "comparison_limit": 1000, "alpha": .05, "epsilon": .01, "penalty": .01,
        "minimum_per_group": 32,
    }, indent=2), encoding="utf-8")
    rows = []
    for seed in args.seeds:
        for phase in ("acquisition", "transfer"):
            for noise in (False, True):
                directory = root / f"seed_{seed}" / phase / ("noise" if noise else "structured")
                directory.mkdir(parents=True)
                rows.append(audit_condition(seed, phase, noise, args.horizons, directory))
    summary = {
        "scope": "Environment validation; oracle and constant predictors are controls, not learned results",
        "learner_implemented": False, "conditions": rows,
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("FIRST_PIECE_AUDIT_JSON=" + json.dumps(summary, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
