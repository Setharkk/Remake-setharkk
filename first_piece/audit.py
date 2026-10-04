"""Audit the laboratory and evidence gate, without training a learner."""
import argparse
import json
import math
import platform
import random
import tempfile
import time
from pathlib import Path

from .world import HistoryWorld
from .criterion import evaluate_distinction


def _write_json(path, data):
    """Replace one JSON file atomically; retain the previous file on failure."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def audit_condition(seed, phase, noise, horizons, directory):
    world = HistoryWorld(seed, rule=seed % 2, phase=phase, noise=noise)
    actions = random.Random(seed + 2000003)
    outcomes, groups, proposals = [], [], []
    histories = set()
    oracle_correct = 0
    snapshots = []
    started = time.perf_counter()
    progress = {
        "seed": seed, "phase": phase, "noise": noise, "status": "running",
        "checkpoint_interactions": 0, "checkpoints": [],
        "world_checkpoint": world.checkpoint(),
        "scope": "Audit diagnostics; not a resumable audit or learner checkpoint",
    }
    _write_json(directory / "progress.json", progress)
    try:
        with (directory / "observations.jsonl").open("w", encoding="utf-8") as stream:
            for step in range(1, max(horizons) + 1):
                view = world.observe()
                action = actions.randrange(2)
                # Positive control knows the rule. It is not a trained model.
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
                    stream.flush()
                    # Keep the state and metrics of one confirmed boundary in
                    # one file. This is separate from the public observations.
                    progress = {
                        **progress, "checkpoint_interactions": step,
                        "checkpoints": list(snapshots),
                        "world_checkpoint": world.checkpoint(),
                    }
                    _write_json(directory / "progress.json", progress)
        _write_json(directory / "world_checkpoint.json", world.checkpoint())
        progress["status"] = "completed"
        _write_json(directory / "progress.json", progress)
    except BaseException as exc:
        # A handled interruption preserves the last evaluated boundary.
        # After an abrupt process kill, status may remain running: it must
        # still be treated as incomplete. This does not resume the audit.
        progress = {**progress, "status": "interrupted", "error_type": type(exc).__name__}
        try:
            _write_json(directory / "progress.json", progress)
        except OSError:
            pass
        raise
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
    _write_json(root / "config.json", {
        **vars(args), "audit_format": 2,
        "scope": "Laboratory and frozen-oracle evidence gate; no learner trained",
        "comparison_limit": 1000, "alpha": .05, "two_sided": True,
        "epsilon": .01, "penalty": .01, "minimum_per_group": 32,
        "python_version": platform.python_version(), "platform": platform.platform(),
    })
    rows = []
    for seed in args.seeds:
        for phase in ("acquisition", "transfer"):
            for noise in (False, True):
                directory = root / f"seed_{seed}" / phase / ("noise" if noise else "structured")
                directory.mkdir(parents=True)
                rows.append(audit_condition(seed, phase, noise, args.horizons, directory))
    summary = {
        "audit_format": 2,
        "scope": "Environment validation; oracle and constant predictors are controls, not learned results",
        "learner_implemented": False, "conditions": rows,
    }
    _write_json(root / "summary.json", summary)
    print("FIRST_PIECE_AUDIT_JSON=" + json.dumps(summary, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
