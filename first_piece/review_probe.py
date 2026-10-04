"""Reproduce the first review findings before and after correction.

Needs git history containing the reviewed commit. The CI checkout fetches it.
This evaluates laboratory code, not a trained model.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

from . import audit, criterion, world


BASE_COMMIT = "c929d0d0ea534c6d7f4d37cd5b432c450128c9ed"


def _snapshot(ref):
    package_name = "_first_piece_review_before"
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
    modules = {}
    for name in ("world", "criterion", "audit"):
        path = f"first_piece/{name}.py"
        source = subprocess.run(
            ["git", "show", f"{ref}:{path}"], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout
        module = types.ModuleType(f"{package_name}.{name}")
        module.__package__ = package_name
        module.__file__ = f"{ref}:{path}"
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        modules[name] = module
    return types.SimpleNamespace(**modules)


def _printable(number):
    return number if math.isfinite(number) else str(number)


def _checks(modules):
    evaluate = modules.criterion.evaluate_distinction
    outcomes = [i % 2 for i in range(100)]
    args = ([.5] * 100, [.5] * 100, outcomes, outcomes)
    findings = {}

    result = evaluate(*args)
    width = math.log(100)
    risk_bound = 2 * 1000 * math.exp(-100 * result["uncertainty_bound"]**2 / (2 * width**2))
    findings["both_tails_share_alpha"] = {
        "passed": risk_bound <= .05 * (1 + 1e-12),
        "family_hoeffding_error_bound": risk_bound, "required_maximum": .05,
    }
    for name, settings in (
        ("tiny_alpha_finite_bound", {"alpha": 1e-310}),
        ("tiny_epsilon_finite_bound", {"epsilon": 1e-310}),
        ("large_comparison_budget_finite_bound", {"comparison_limit": 10**400}),
    ):
        try:
            result = evaluate(*args, **settings)
            findings[name] = {
                "passed": math.isfinite(result["uncertainty_bound"]),
                "uncertainty_bound": _printable(result["uncertainty_bound"]),
            }
        except Exception as exc:
            findings[name] = {"passed": False, "exception": type(exc).__name__}

    try:
        result = evaluate([.5] * 100, [1 - y for y in outcomes], outcomes, outcomes, epsilon=1e-20)
        findings["wrong_endpoints_have_finite_score"] = {
            "passed": math.isfinite(result["mean_log_score_gain"]),
            "mean_log_score_gain": _printable(result["mean_log_score_gain"]),
        }
    except Exception as exc:
        findings["wrong_endpoints_have_finite_score"] = {
            "passed": False, "exception": type(exc).__name__,
        }

    try:
        result = evaluate(*args, penalty=1e308, extra_units=2)
        findings["overflowing_cost_is_rejected"] = {
            "passed": False, "complexity_cost": _printable(result["complexity_cost"]),
        }
    except ValueError:
        findings["overflowing_cost_is_rejected"] = {"passed": True, "exception": "ValueError"}

    class InterruptedWorld(modules.world.HistoryWorld):
        def act(self, action):
            if self.completed == 125:
                raise RuntimeError("Injected interruption after interaction 125")
            return super().act(action)

    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        with patch.object(modules.audit, "HistoryWorld", InterruptedWorld):
            try:
                modules.audit.audit_condition(0, "acquisition", False, [100, 200], directory)
            except RuntimeError:
                pass
        progress_path = directory / "progress.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
        findings["interruption_preserves_horizon_100"] = {
            "passed": (
                progress.get("status") == "interrupted"
                and progress.get("checkpoint_interactions") == 100
                and [c["interactions"] for c in progress.get("checkpoints", [])] == [100]
                and progress.get("world_checkpoint", {}).get("completed") == 100
            ),
            "progress_file_exists": progress_path.exists(),
            "preserved_horizons": [c["interactions"] for c in progress.get("checkpoints", [])],
            "observations_written": len((directory / "observations.jsonl").read_text().splitlines()),
        }
    return findings


def _distinction_limit():
    # The outcome is determined by the action. The balanced grouping is
    # independent of it: each group contains equal numbers of both outcomes.
    outcomes = [i % 2 for i in range(10000)]
    groups = [(i // 2) % 2 for i in range(10000)]
    predictions = [.99 if y else .01 for y in outcomes]
    result = criterion.evaluate_distinction([.5] * 10000, predictions, outcomes, groups)
    return {
        "decision_with_irrelevant_groups": result["decision"],
        "meaning": "Predictive gain alone does not prove that the proposed grouping is necessary",
        "resolution": "Requires a fitted no-distinction control with the same inputs and training budget",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE_COMMIT)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    before = _checks(_snapshot(args.base))
    after = _checks(types.SimpleNamespace(audit=audit, criterion=criterion, world=world))
    result = {
        "reviewed_commit": args.base, "corrected_commit": os.environ.get("GITHUB_SHA"),
        "before": before, "after": after,
        "remaining_methodological_limit": _distinction_limit(),
    }
    Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("FIRST_PIECE_REVIEW_JSON=" + json.dumps(result, allow_nan=False), flush=True)
    if any(case["passed"] for case in before.values()):
        raise SystemExit("A previously identified defect was not reproduced")
    if not all(case["passed"] for case in after.values()):
        raise SystemExit("A corrected case still fails")


if __name__ == "__main__":
    main()
