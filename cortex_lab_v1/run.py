"""Run the intrinsic network on the same disposable filesystem laboratory."""
import argparse
import csv
import datetime
import json
import math
import random
import uuid
from pathlib import Path

import torch

from cortex_lab_v0.file_lab import ACTION_NAMES, FileLab, collect_cases
from cortex_lab_v0.run import make_warmup, split_cases, write_json
from .learner import IntrinsicEnsemble, information_gain


def run_condition(root, seed, strategy, train, test, args):
    directory = root / f"seed_{seed}" / strategy
    directory.mkdir(parents=True, exist_ok=False)
    lab = FileLab(directory / "files")
    learner = IntrinsicEnsemble(seed + 12000, lr=args.lr, device=args.device)
    rng = random.Random(seed + 776)
    warmup = make_warmup(train, seed)
    initial = learner.evaluate(test)
    final = initial
    with (
        (directory / "metrics.csv").open("w", encoding="utf-8", newline="") as metrics,
        (directory / "experiences.jsonl").open("w", encoding="utf-8") as experiences,
    ):
        writer = csv.DictWriter(metrics, fieldnames=["step", *initial.keys()])
        writer.writeheader()
        writer.writerow({"step": 0, **initial})
        metrics.flush()
        for step in range(1, args.steps + 1):
            predictions = learner.predict(train)
            gains = information_gain(predictions).cpu().tolist()
            if step <= len(warmup):
                index, selection = warmup[step - 1], "shared_warmup"
            elif strategy == "random" or rng.random() < .12:
                index, selection = rng.randrange(len(train)), "random"
            else:
                maximum = max(gains)
                tied = [i for i, gain in enumerate(gains) if maximum - gain <= 1e-10]
                index, selection = rng.choice(tied), "information_gain"
            candidate = train[index]
            result, record = lab.execute(candidate["state"], candidate["action"])
            record.update({
                "step": step, "selection": selection,
                "learning_target": "learn_effects_of_" + ACTION_NAMES[candidate["action"]],
                "expected_information_gain": gains[index],
                "predicted_before": predictions[:, index].mean(0).cpu().tolist(),
            })
            experiences.write(json.dumps(record) + "\n")
            experiences.flush()
            learner.observe(candidate["state"], candidate["action"], result)
            learner.learn(updates=args.updates, batch_size=32)
            if step % 50 == 0 or step == args.steps:
                final = learner.evaluate(test)
                writer.writerow({"step": step, **final})
                metrics.flush()
                print(
                    f"seed={seed} strategy={strategy} step={step} "
                    f"Brier={final['brier']:.6f} "
                    f"constraint={final['max_manifold_constraint_error']:.2e}",
                    flush=True,
                )
    torch.save(learner.checkpoint(), directory / "weights.pt")
    write_json(directory / "replay.json", list(learner.memory))
    return {"seed": seed, "strategy": strategy, "initial": initial, "final": final}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--updates", type=int, default=3)
    parser.add_argument("--lr", type=float, default=.03)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "cortex_runs"))
    args = parser.parse_args()
    if (
        min(args.steps, args.updates, args.lr) <= 0 or not math.isfinite(args.lr)
        or len(set(args.seeds)) != len(args.seeds)
    ):
        parser.error("Positive counts/lr and distinct seeds required")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA unavailable")
    torch.set_num_threads(1)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(args.out).resolve() / f"{stamp}_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "config.json", {
        **vars(args), "architecture": "intrinsic_lorentz_prototypes",
        "curvature": -1, "dimension": 4,
        "points_per_model": 34, "stored_scalars_per_model": 170,
        "intrinsic_degrees_of_freedom_per_model": 136,
        "ensemble_size": 3, "torch": str(torch.__version__),
        "scope": "Same three-bit file fixtures; new network and optimizer",
    })
    cases = collect_cases(FileLab(root / "evaluation_fixtures"))
    splits = {seed: split_cases(cases, seed) for seed in args.seeds}
    write_json(root / "splits.json", {
        str(seed): {"training_candidates": train, "held_out_cases": test}
        for seed, (train, test) in splits.items()
    })
    results = [
        run_condition(root, seed, strategy, *splits[seed], args)
        for seed in args.seeds for strategy in ("active", "random")
    ]
    write_json(root / "summary.json", {
        "runs": results,
        "scope": "Geometry and a small learning diagnostic; no autonomy or superiority claim",
    })
    print("INTRINSIC_RESULTS_JSON=" + json.dumps(results, allow_nan=False), flush=True)
    print(f"Results: {root}", flush=True)


if __name__ == "__main__":
    main()
