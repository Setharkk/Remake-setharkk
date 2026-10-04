"""Run one independent predeclared measurement case; preserve failure evidence."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import traceback

from .plastic_revision_probe import run_case, run_scale, summarize, ABLATIONS, OPTIONS, SCALE_OPTIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=("retention", "successive_changes", "variable_noise", "ablations", "scale"), required=True)
    parser.add_argument("--seed", type=int, choices=(0, 1, 2), required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = {"protocol": "PLASTIC_REVISION_PROTOCOL.md", "protocol_version": 1,
              "engine_commit": subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                               capture_output=True, text=True).stdout.strip(),
              "runner": platform.system(), "python": platform.python_version(),
              "options": OPTIONS, "scale_options": SCALE_OPTIONS,
              "group": args.group, "seed": args.seed, "cases": [], "scale_cases": []}
    error = None
    try:
        if args.group == "scale":
            report["scale_cases"] = [run_scale(args.seed)]
        else:
            case = run_case("noise_then_signal" if args.group == "ablations" else args.group,
                            args.seed, ABLATIONS if args.group == "ablations" else None)
            if args.group == "ablations":
                case["case"] = "cold_ablations"
            report["cases"] = [case]
            report["summary"] = [summarize(case)]
            if case["criteria_failures"]:
                raise AssertionError(case["criteria_failures"])
    except Exception as exc:
        error = exc
        report["error"] = {"type": type(exc).__name__, "message": str(exc),
                           "traceback": traceback.format_exc()}
        frame = exc.__traceback__
        while frame is not None:
            if frame.tb_frame.f_code.co_name == "run_scale":
                local = frame.tb_frame.f_locals
                report["partial_scale"] = {key: local.get(key) for key in
                    ("phase", "local", "curves", "phase_results", "searches",
                     "decisions", "resumes", "bounds", "score")}
                report["partial_scale"]["metrics"] = local["core"].metrics()
            frame = frame.tb_next
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PLASTIC_REVISION_GROUP_JSON " + json.dumps(report, separators=(",", ":")), flush=True)
    if error is not None:
        raise error


if __name__ == "__main__":
    main()
