"""Read-only diagnostic probes for the V1 review.

These probes report observed behavior of the reviewed implementation.
They are not regression tests declaring that the defective behavior is desired.
All filesystem operations use disposable TemporaryDirectory fixtures.
"""
import csv
import fnmatch
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from cortex_lab_v0.file_lab import FileLab, collect_cases
from cortex_lab_v0.run import split_cases
from cortex_lab_v1.learner import IntrinsicEnsemble
from cortex_lab_v1.run import run_condition

REVIEWED_COMMIT = "af6022eb8f60e8e6113329880b107e0f60267bf2"
torch.set_num_threads(1)


def input_validation():
    learner = IntrinsicEnsemble(seed=3, members=1)

    def check_alias(invalid, reference):
        try:
            actual = learner.predict([invalid])
            expected = learner.predict([reference])
            return {
                "accepted": True,
                "identical_prediction_to_reference": bool(torch.equal(actual, expected)),
                "maximum_prediction_difference": float((actual - expected).abs().max()),
            }
        except (ValueError, IndexError, TypeError) as exc:
            return {"accepted": False, "exception": type(exc).__name__}

    aliases = {
        "negative_state_bit": check_alias(
            {"state": [-1, 0, 0], "action": 0},
            {"state": [1, 0, 0], "action": 0},
        ),
        "negative_action": check_alias(
            {"state": [0, 0, 0], "action": -1},
            {"state": [0, 0, 0], "action": 3},
        ),
        "fractional_state_bit": check_alias(
            {"state": [.9, 0, 0], "action": 0},
            {"state": [0, 0, 0], "action": 0},
        ),
        "fractional_action": check_alias(
            {"state": [0, 0, 0], "action": 1.9},
            {"state": [0, 0, 0], "action": 1},
        ),
    }
    bad_target = IntrinsicEnsemble(seed=3, members=1)
    try:
        bad_target.observe([0, 0, 0], 0, [1, 0, 0, 2])
        bad_target.learn(updates=1)
        aliases["target_outside_binary_range"] = {
            "accepted_and_trained": True, "optimizer_updates": bad_target.updates,
            "stored_result": bad_target.memory[0]["result"],
            "loss": bad_target.last_loss,
        }
    except (ValueError, IndexError, TypeError) as exc:
        aliases["target_outside_binary_range"] = {
            "accepted_and_trained": False, "exception": type(exc).__name__,
            "memory_entries_after_rejection": len(bad_target.memory),
        }
    return aliases


def interruption(root, cases):
    train, test = split_cases(cases, seed=0)
    args = SimpleNamespace(steps=20, updates=1, lr=.03, device="cpu")
    original = FileLab.execute
    calls = 0

    def fail_after_four(lab, state, action):
        nonlocal calls
        calls += 1
        if calls == 5:
            raise RuntimeError("Review probe: injected interruption")
        return original(lab, state, action)

    caught = False
    with patch.object(FileLab, "execute", fail_after_four):
        try:
            run_condition(root, 0, "random", train, test, args)
        except RuntimeError as exc:
            if str(exc) != "Review probe: injected interruption":
                raise
            caught = True
    directory = root / "seed_0" / "random"
    with (directory / "experiences.jsonl").open(encoding="utf-8") as stream:
        experiences = [json.loads(line) for line in stream]
    with (directory / "metrics.csv").open(encoding="utf-8", newline="") as stream:
        metrics = list(csv.DictReader(stream))
    return {
        "injected_interruption_observed": caught,
        "completed_interactions": len(experiences),
        "weights_file_exists": (directory / "weights.pt").exists(),
        "replay_file_exists": (directory / "replay.json").exists(),
        "metrics_rows_preserved": len(metrics),
    }


def continuation(cases):
    original = IntrinsicEnsemble(seed=7, members=1)
    for case in cases:
        original.observe(case["state"], case["action"], case["result"])
    original.learn(updates=40)
    saved = original.checkpoint()
    restored = IntrinsicEnsemble(seed=7, members=1)
    restored.load_weights(saved)
    same_before = bool(torch.equal(original.predict(cases), restored.predict(cases)))
    # Even reconstructing the replay manually does not reconstruct moments/RNG.
    for case in cases:
        restored.observe(case["state"], case["action"], case["result"])
    original.learn(updates=1)
    restored.learn(updates=1)
    a, b = original.predict(cases), restored.predict(cases)
    return {
        "checkpoint_keys": list(saved),
        "predictions_identical_before_continuation": same_before,
        "same_constructor_seed": True,
        "replay_manually_reconstructed": True,
        "predictions_identical_after_one_update": bool(torch.equal(a, b)),
        "maximum_prediction_difference_after_one_update": float((a - b).abs().max()),
        "original_update_count": original.updates,
        "restored_update_count": restored.updates,
    }


def dependency_trigger_coverage():
    # Exact path filters in the reviewed workflow.
    intrinsic_paths = ["cortex_lab_v1/**", ".github/workflows/cortex-intrinsic.yml"]
    dependencies = ["cortex_lab_v0/core.py", "cortex_lab_v0/run.py", "cortex_lab_v0/file_lab.py"]
    return {
        "intrinsic_push_filters": intrinsic_paths,
        "shared_dependencies": [
            {"path": path, "triggers_intrinsic_workflow":
             any(fnmatch.fnmatchcase(path, pattern) for pattern in intrinsic_paths)}
            for path in dependencies
        ],
        "legacy_workflow_test_command": "python -m unittest discover -s cortex_lab_v0/tests -v",
    }


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        cases = collect_cases(FileLab(root / "cases"))
        output = {
            "reviewed_commit": REVIEWED_COMMIT,
            "input_validation": input_validation(),
            "interruption": interruption(root / "interrupted", cases),
            "weight_only_continuation": continuation(cases),
            "dependency_trigger_coverage": dependency_trigger_coverage(),
        }
    print("V1_REVIEW_PROBES_JSON=" + json.dumps(output, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
