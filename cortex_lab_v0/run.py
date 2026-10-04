"""Compare active/random exploration and curved/flat dynamics."""
import argparse
import csv
import datetime
import json
import platform
import random
import statistics
import sys
import uuid
from pathlib import Path

import torch

from .core import Ensemble, information_gain
from .file_lab import ACTION_NAMES, FileLab, collect_cases


def split_cases(cases, seed):
    rng = random.Random(seed)
    test_indices = set()
    for action in range(4):
        for success in (0, 1):
            choices = [
                index for index, case in enumerate(cases)
                if case["action"] == action and case["result"][-1] == success
            ]
            if not choices:
                raise RuntimeError("Cannot create a balanced held-out split")
            test_indices.add(rng.choice(choices))
    # The selector receives no targets, including for training candidates.
    train = [
        {"state": case["state"], "action": case["action"]}
        for index, case in enumerate(cases) if index not in test_indices
    ]
    test = [case for index, case in enumerate(cases) if index in test_indices]
    return train, test


def make_warmup(train, seed):
    """Two distinct pairs per action, shared by all four conditions."""
    rng = random.Random(seed + 555)
    by_action = [
        rng.sample([
            index for index, case in enumerate(train) if case["action"] == action
        ], 2)
        for action in range(len(ACTION_NAMES))
    ]
    return [indices[round_index] for round_index in range(2) for indices in by_action]


def write_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_condition(root, geometry, exploration, seed, train, test, args):
    directory = root / f"seed_{seed}" / f"{geometry}_{exploration}"
    directory.mkdir(parents=True, exist_ok=False)
    lab = FileLab(directory / "files")
    learner = Ensemble(geometry, seed + 12000, args.device)
    rng = random.Random(seed + 776)
    warmup = make_warmup(train, seed)
    initial = learner.evaluate(test)
    rows = [{"step": 0, **initial}]
    with (
        (directory / "metrics.csv").open(
            "w", encoding="utf-8", newline=""
        ) as metrics_stream,
        (directory / "experiences.jsonl").open("w", encoding="utf-8") as stream,
    ):
        writer = csv.DictWriter(metrics_stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerow(rows[0])
        metrics_stream.flush()
        for step in range(1, args.steps + 1):
            probabilities = learner.predict(train)
            gains = information_gain(probabilities).cpu().tolist()
            if step <= len(warmup):
                index = warmup[step - 1]
                selection = "shared_warmup"
            elif exploration == "random" or rng.random() < 0.12:
                index = rng.randrange(len(train))
                selection = "random"
            else:
                highest = max(gains)
                tied = [
                    index for index, value in enumerate(gains)
                    if highest - value <= 1e-10
                ]
                index = rng.choice(tied)
                selection = "information_gain"
            chosen = train[index]
            result, record = lab.execute(chosen["state"], chosen["action"])
            record.update({
                "step": step,
                "selection": selection,
                "learning_target": "learn_effects_of_" + ACTION_NAMES[chosen["action"]],
                "expected_information_gain": gains[index],
                "predicted_before": probabilities[:, index].mean(0).cpu().tolist(),
            })
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            learner.observe(chosen["state"], chosen["action"], result)
            learner.learn(updates=args.updates, batch_size=args.batch_size)
            if step % args.evaluate_every == 0 or step == args.steps:
                metrics = learner.evaluate(test)
                rows.append({"step": step, **metrics})
                writer.writerow(rows[-1])
                metrics_stream.flush()
                print(
                    f"{seed} {geometry:10s} {exploration:6s} "
                    f"step={step:4d} Brier={metrics['brier']:.4f} "
                    f"exact={metrics['exact_accuracy']:.0%} "
                    f"delta_weights={metrics['weights_changed_l2']:.3f}",
                    flush=True
                )
    torch.save(learner.checkpoint(), directory / "weights.pt")
    write_json(directory / "replay.json", list(learner.memory))
    final = rows[-1]
    return {
        "seed": seed, "geometry": geometry, "exploration": exploration,
        "initial": initial, "final": final,
        "brier_improvement": initial["brier"] - final["brier"],
        "parameters_per_model": sum(
            value.numel() for value in learner.models[0].parameters()
        ),
        "ensemble_size": len(learner.models),
        "training_experiments": args.steps,
        "held_out_cases": len(test),
        "held_out_baselines": {
            "uniform_brier": 0.25,
            "unchanged_state_brier": statistics.mean([
                sum((float(bit) - truth) ** 2 for bit, truth in zip(
                    case["state"] + [0.5], case["result"]
                )) / 4 for case in test
            ]),
        },
        "directory": str(directory),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--out", default=str(Path(__file__).resolve().parent / "cortex_runs")
    )
    parser.add_argument("--updates", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--evaluate-every", type=int, default=20)
    args = parser.parse_args()
    if min(args.steps, args.updates, args.batch_size, args.evaluate_every) < 1:
        parser.error("Counts must be positive")
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Seeds must be distinct")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA unavailable; use --device cpu or install a CUDA build")
    torch.set_num_threads(1)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(args.out).resolve() / f"{stamp}_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "config.json", {
        **vars(args), "protocol_version": 2,
        "python": sys.version, "torch": str(torch.__version__),
        "platform": platform.platform(),
        "hyperbolic_curvature": -1, "euclidean_curvature": 0,
        "latent_dimension": 4,
        "scope": "Three existence bits, four predefined operations, fresh fixtures",
    })
    cases = collect_cases(FileLab(root / "evaluation_fixtures"))
    results = []
    splits = {}
    prepared_splits = {}
    for seed in args.seeds:
        train, test = split_cases(cases, seed)
        prepared_splits[seed] = (train, test)
        splits[str(seed)] = {"training_candidates": train, "held_out_cases": test}
    # Persist the protocol before training, including if a later run fails.
    write_json(root / "splits.json", splits)
    for seed in args.seeds:
        train, test = prepared_splits[seed]
        for geometry in ("hyperbolic", "euclidean"):
            for exploration in ("active", "random"):
                results.append(run_condition(
                    root, geometry, exploration, seed, train, test, args
                ))
    aggregate = {}
    for geometry in ("hyperbolic", "euclidean"):
        for exploration in ("active", "random"):
            values = [
                item["final"]["brier"] for item in results
                if item["geometry"] == geometry
                and item["exploration"] == exploration
            ]
            aggregate[f"{geometry}_{exploration}"] = {
                "mean_final_brier": statistics.mean(values),
                "sample_std": statistics.stdev(values) if len(values) > 1 else None,
                "seeds": len(values),
            }
    unchanged = [
        sum((float(bit) - truth) ** 2 for bit, truth in zip(
            case["state"] + [0.5], case["result"]
        )) / 4
        for case in cases
    ]
    write_json(root / "summary.json", {
        "protocol_version": 2, "runs": results, "aggregate": aggregate,
        "reference_all_32_cases": {
            "unchanged_state_brier": statistics.mean(unchanged),
            "uniform_predictions_brier": 0.25,
        },
        "interpretation": (
            "Eight held-out pairs per seed form a tiny diagnostic. "
            "They do not establish general desktop autonomy or a curvature advantage."
        ),
    })
    print(f"\nResultats : {root}", flush=True)
    print(json.dumps(aggregate, indent=2), flush=True)


if __name__ == "__main__":
    main()
