"""Fresh, read-only evaluations of the published temporal checkpoints."""
import argparse
import json
from pathlib import Path

from first_piece.learner import DistinctionLearner
from first_piece.temporal import TemporalLearner
from first_piece.temporal_run import evaluate, SCENARIOS

PRIMARY_SEED = 20000001
TRANSFER_SEED = 30000001
RETENTION_SEED = 40000001


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    states = Path(args.states)
    rows = []
    for seed in range(5):
        for index, scenario in enumerate(SCENARIOS):
            phase = "before" if scenario in ("noise", "action_only") else "after"
            path = states / f"{scenario}-seed-{seed}-{phase}-10000.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            if snapshot["seed"] != seed or snapshot["scenario"] != scenario or snapshot["phase_interactions"] != 10000:
                raise ValueError("Source checkpoint differs from declared condition")
            learner = TemporalLearner.restore(snapshot["learner"])
            presence = DistinctionLearner.restore(snapshot["presence_reference"])
            before = learner.checkpoint()
            source = snapshot["world"]
            offset = 100000 * index + 43 * seed
            options = {"rule": source["rule"], "pair": tuple(source["pair"]), "mode": source["mode"]}
            row = {"seed": seed, "scenario": scenario, "checkpoint": path.name,
                   "primary_seed": PRIMARY_SEED + offset,
                   "primary": evaluate(learner, presence, seed=PRIMARY_SEED + offset, n=1024, **options)}
            if scenario not in ("noise", "action_only"):
                row["transfer_seed"] = TRANSFER_SEED + offset
                row["transfer"] = evaluate(learner, presence, seed=TRANSFER_SEED + offset,
                                            n=1024, phase="transfer", **options)
            if scenario in ("inversion", "relation_switch"):
                row["retention_seed"] = RETENTION_SEED + offset
                row["retention"] = evaluate(learner, seed=RETENTION_SEED + offset,
                                             n=512, rule=1, task=1, phase="transfer")
            if learner.checkpoint() != before:
                raise AssertionError("Final evaluation changed its source learner")
            rows.append(row)
    report = {"protocol": 1, "source_workflow_run": 37208231509,
              "source_commit": "b9c38fe8a69f248b8665e6addc685cf84f6331be",
              "new_training_interactions": 0, "source_states_unchanged": True,
              "fresh_evaluation_seeds_declared_in_code": True,
              "conditions": rows}
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("FIRST_PIECE_TEMPORAL_FINAL_JSON=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
