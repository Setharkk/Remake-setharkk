"""Audit a completed comparative run without feeding scores back to training."""
import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path

import torch

from .core import Ensemble
from .file_lab import ACTION_NAMES
from .run import write_json

CONDITIONS = ("hyperbolic_active", "hyperbolic_random", "euclidean_active", "euclidean_random")
CHECKPOINTS = (0, 50, 100, 200)


def describe(values):
    values = list(values)
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError("Expected non-empty finite measurements")
    return {
        "n": len(values), "mean": statistics.mean(values),
        "sample_std": statistics.stdev(values) if len(values) > 1 else None,
        "median": statistics.median(values), "min": min(values), "max": max(values),
    }


def bootstrap_mean_interval(values, samples=10000):
    """Descriptive percentile interval over seed-level measurements."""
    values = list(values)
    if not values or samples < 2:
        raise ValueError("Invalid bootstrap inputs")
    rng = random.Random(39017)
    means = sorted(
        statistics.mean(rng.choices(values, k=len(values))) for _ in range(samples)
    )
    return [means[int(.025 * (samples - 1))], means[int(.975 * (samples - 1))]]


def paired_comparison(left, right):
    """Compare the same seeds; negative left-minus-right favors left."""
    if not left or set(left) != set(right):
        raise ValueError("Paired comparison requires identical non-empty seed sets")
    differences = [left[seed] - right[seed] for seed in sorted(left)]
    return {
        "left_minus_right": describe(differences),
        "bootstrap95_mean_difference": bootstrap_mean_interval(differences),
        "left_better_seeds": sum(d < 0 for d in differences),
        "right_better_seeds": sum(d > 0 for d in differences),
        "tied_seeds": sum(d == 0 for d in differences),
    }


def find_root(path):
    path = Path(path)
    if (path / "summary.json").is_file():
        return path
    roots = [p for p in path.iterdir() if p.is_dir() and (p / "summary.json").is_file()]
    if len(roots) != 1:
        raise ValueError("Provide one completed run directory, or its parent with one run")
    return roots[0]


def baseline(case):
    return sum(
        (probability - target) ** 2
        for probability, target in zip(case["state"] + [.5], case["result"])
    ) / 4


def audit_run(root, run, split, config):
    geometry, exploration, seed = run["geometry"], run["exploration"], run["seed"]
    directory = root / f"seed_{seed}" / f"{geometry}_{exploration}"
    with (directory / "metrics.csv").open(encoding="utf-8", newline="") as stream:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(stream)]
    steps = [int(row["step"]) for row in rows]
    if len(set(steps)) != len(steps) or steps != sorted(steps):
        raise ValueError("Duplicate or unordered evaluations")
    by_step = {int(row["step"]): row for row in rows}
    if not set(CHECKPOINTS).issubset(by_step):
        raise ValueError("Missing required evaluations")
    if not all(math.isfinite(v) for row in rows for v in row.values()):
        raise ValueError("Non-finite metric")
    if steps[-1] != 200 or config["steps"] != 200:
        raise ValueError("This benchmark requires 200 experiences per condition")
    if run["parameters_per_model"] != 72 or run["ensemble_size"] != 3:
        raise ValueError("Unexpected model budget")
    for step, row in by_step.items():
        if row["optimizer_updates"] != step * config["updates"] * run["ensemble_size"]:
            raise ValueError("Optimizer budget mismatch")
        if not 0 <= row["brier"] <= 1:
            raise ValueError("Invalid Brier score")
    for key, value in run["final"].items():
        if not math.isclose(by_step[200][key], value, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("CSV and summary disagree")

    train = {(tuple(c["state"]), c["action"]) for c in split["training_candidates"]}
    test = split["held_out_cases"]
    heldout = {(tuple(c["state"]), c["action"]) for c in test}
    if len(train) != 24 or len(heldout) != 8 or train & heldout:
        raise ValueError("Invalid train/heldout split")
    records = [
        json.loads(line) for line in (directory / "experiences.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    if [r["step"] for r in records] != list(range(1, 201)):
        raise ValueError("Experience budget mismatch")
    counts, action_counts, outcomes = Counter(), Counter(), {}
    for record in records:
        action = ACTION_NAMES.index(record["action"])
        pair = (tuple(record["state"]), action)
        if pair not in train or pair in heldout:
            raise ValueError("Heldout leakage or unknown training candidate")
        gain = record["expected_information_gain"]
        if not math.isfinite(gain) or not 0 <= gain <= math.log(3) + 1e-10:
            raise ValueError("Invalid information gain")
        prediction = record["predicted_before"]
        if len(prediction) != 4 or not all(math.isfinite(p) and 0 <= p <= 1 for p in prediction):
            raise ValueError("Invalid recorded prediction")
        result = tuple(record["result"])
        if len(result) != 4 or any(bit not in (0, 1) for bit in result):
            raise ValueError("Invalid observed result")
        if pair in outcomes and outcomes[pair] != result:
            raise ValueError("Stationary fixture produced conflicting outcomes")
        outcomes[pair] = result
        counts[pair] += 1
        action_counts[record["action"]] += 1
    warmup = [(tuple(r["state"]), r["action"]) for r in records[:8]]
    if len(set(warmup)) != 8 or any(r["selection"] != "shared_warmup" for r in records[:8]):
        raise ValueError("Invalid distinct warmup")
    if exploration == "random" and any(r["selection"] != "random" for r in records[8:]):
        raise ValueError("Random baseline used an active selector")
    if exploration == "active" and any(
        r["selection"] not in ("random", "information_gain") for r in records[8:]
    ):
        raise ValueError("Unknown active selection")

    saved = torch.load(directory / "weights.pt", map_location="cpu", weights_only=True)
    learner = Ensemble(geometry, seed + 12000, members=run["ensemble_size"])
    if len(saved) != len(learner.models):
        raise ValueError("Checkpoint ensemble size mismatch")
    for model, state in zip(learner.models, saved):
        model.load_state_dict(state)
    prediction = learner.predict(test).mean(0).cpu().tolist()
    case_scores = [
        sum((p - y) ** 2 for p, y in zip(pred, case["result"])) / 4
        for pred, case in zip(prediction, test)
    ]
    if not math.isclose(
        statistics.mean(case_scores), run["final"]["brier"], rel_tol=1e-10, abs_tol=1e-12
    ):
        raise ValueError("Restored weights do not reproduce the final Brier")
    worst_cases = sorted([
        {
            "state": case["state"], "action": ACTION_NAMES[case["action"]],
            "result": case["result"], "prediction": pred, "brier": score,
            "unchanged_state_brier": baseline(case),
        }
        for case, pred, score in zip(test, prediction, case_scores)
    ], key=lambda c: c["brier"], reverse=True)[:3]
    most_pair, most_count = counts.most_common(1)[0]
    result = {
        "seed": seed, "condition": f"{geometry}_{exploration}",
        "brier_by_step": {str(s): by_step[s]["brier"] for s in CHECKPOINTS},
        "initial_to_final_improvement": by_step[0]["brier"] - by_step[200]["brier"],
        "final_nll": by_step[200]["nll"],
        "final_exact_accuracy": by_step[200]["exact_accuracy"],
        "final_action_brier": {
            name: by_step[200][f"brier_action_{i}"] for i, name in enumerate(ACTION_NAMES)
        },
        "unchanged_state_brier": statistics.mean(baseline(case) for case in test),
        "unique_training_pairs": len(counts),
        "repeated_pair_fraction": 1 - len(counts) / len(records),
        "most_sampled_pair_share": most_count / len(records),
        "most_sampled_pair": {
            "state": list(most_pair[0]), "action": ACTION_NAMES[most_pair[1]],
            "experiences": most_count,
        },
        "action_counts": {name: action_counts[name] for name in ACTION_NAMES},
        "selection_counts": dict(Counter(r["selection"] for r in records)),
        "training_sequence_sha256": hashlib.sha256(json.dumps([
            [r["state"], r["action"], r["result"]] for r in records
        ], separators=(",", ":")).encode("utf-8")).hexdigest(),
        "worst_heldout_cases": worst_cases,
    }
    csv_rows = [
        {"seed": seed, "condition": result["condition"], **by_step[s]} for s in steps
    ]
    return result, warmup, csv_rows


def analyze(root, expected_seeds):
    root = find_root(root)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    splits = json.loads((root / "splits.json").read_text(encoding="utf-8"))
    if config["protocol_version"] != 2 or summary["protocol_version"] != 2:
        raise ValueError("Unexpected protocol")
    expected = {(s, c) for s in expected_seeds for c in CONDITIONS}
    actual = [(r["seed"], f'{r["geometry"]}_{r["exploration"]}') for r in summary["runs"]]
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError("Missing, duplicate or unexpected seeds/conditions")
    if set(config["seeds"]) != set(expected_seeds):
        raise ValueError("Configuration seeds disagree")
    runs, all_csv_rows, warmups = [], [], {}
    for entry in summary["runs"]:
        run, warmup, csv_rows = audit_run(root, entry, splits[str(entry["seed"])], config)
        if entry["seed"] in warmups and warmups[entry["seed"]] != warmup:
            raise ValueError("Warmup differs between conditions")
        warmups[entry["seed"]] = warmup
        runs.append(run)
        all_csv_rows.extend(csv_rows)
    for seed in expected_seeds:
        random_sequences = {
            r["training_sequence_sha256"] for r in runs
            if r["seed"] == seed and r["condition"].endswith("_random")
        }
        if len(random_sequences) != 1:
            raise ValueError("Random geometries saw different training experiences")
    conditions = {}
    for condition in CONDITIONS:
        group = [r for r in runs if r["condition"] == condition]
        improvements = [r["initial_to_final_improvement"] for r in group]
        conditions[condition] = {
            "brier_by_step": {
                str(step): describe(r["brier_by_step"][str(step)] for r in group)
                for step in CHECKPOINTS
            },
            "initial_to_final_improvement": describe(improvements),
            "bootstrap95_mean_improvement": bootstrap_mean_interval(improvements),
            "seeds_improved_from_initial": sum(v > 0 for v in improvements),
            "seeds_beat_uniform": sum(r["brier_by_step"]["200"] < .25 for r in group),
            "seeds_beat_unchanged_state": sum(
                r["brier_by_step"]["200"] < r["unchanged_state_brier"] for r in group
            ),
            "seeds_worse_at_200_than_50": sum(
                r["brier_by_step"]["200"] > r["brier_by_step"]["50"] for r in group
            ),
            "seeds_worse_at_200_than_100": sum(
                r["brier_by_step"]["200"] > r["brier_by_step"]["100"] for r in group
            ),
            "final_nll": describe(r["final_nll"] for r in group),
            "final_exact_accuracy": describe(r["final_exact_accuracy"] for r in group),
            "final_action_brier": {
                name: describe(r["final_action_brier"][name] for r in group)
                for name in ACTION_NAMES
            },
            "unique_training_pairs": describe(r["unique_training_pairs"] for r in group),
            "repeated_pair_fraction": describe(r["repeated_pair_fraction"] for r in group),
            "most_sampled_pair_share": describe(r["most_sampled_pair_share"] for r in group),
            "action_counts": {
                name: describe(r["action_counts"][name] for r in group) for name in ACTION_NAMES
            },
            "worst_final_seeds": [
                {"seed": r["seed"], "brier": r["brier_by_step"]["200"]}
                for r in sorted(group, key=lambda r: r["brier_by_step"]["200"], reverse=True)[:3]
            ],
        }
    final = {
        c: {r["seed"]: r["brier_by_step"]["200"] for r in runs if r["condition"] == c}
        for c in CONDITIONS
    }
    comparisons = {}
    for left, right in (
        ("hyperbolic_active", "hyperbolic_random"),
        ("euclidean_active", "euclidean_random"),
        ("hyperbolic_active", "euclidean_active"),
        ("hyperbolic_random", "euclidean_random"),
    ):
        comparisons[f"{left}_minus_{right}"] = paired_comparison(final[left], final[right])
    result = {
        "protocol_version": 2, "seeds": sorted(expected_seeds),
        "experiences_per_condition": 200, "conditions_run": len(runs),
        "total_training_experiences": len(runs) * 200,
        "checkpoints": list(CHECKPOINTS),
        "conditions": conditions, "paired_comparisons": comparisons,
        "scope": "Seed variation within the same 32-pair filesystem world; not new worlds",
        "bootstrap": {
            "samples": 10000, "seed": 39017, "method": "percentile mean over seed-level samples",
            "meaning": "Descriptive seed variability; heldout cases overlap between seeds",
        },
        "runs": runs,
    }
    write_json(root / "analysis.json", result)
    with (root / "benchmark-rows.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_csv_rows[0]))
        writer.writeheader()
        writer.writerows(all_csv_rows)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--expected-seeds", nargs="+", type=int, default=list(range(20)))
    args = parser.parse_args()
    if len(set(args.expected_seeds)) != len(args.expected_seeds):
        parser.error("Seeds must be distinct")
    torch.set_num_threads(1)
    report = analyze(args.results, args.expected_seeds)
    for run in report["runs"]:
        print("CORTEX_RUN_JSON=" + json.dumps(run, allow_nan=False), flush=True)
    print("CORTEX_ANALYSIS_JSON=" + json.dumps(
        {key: value for key, value in report.items() if key != "runs"}, allow_nan=False
    ), flush=True)


if __name__ == "__main__":
    main()
