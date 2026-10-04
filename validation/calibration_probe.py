"""Calibration, raw competence invariants and return of reliable probabilities."""
import argparse
import copy
import json
from pathlib import Path
import platform
import random
import subprocess
import time

from first_piece.calibrated import CalibratedLearner
from first_piece.consolidated import ConsolidatedLearner
from first_piece.shared import log_probability
from .renewable_probe import ShiftWorld, evaluate, canonical, OPTIONS

MODES = {"consolidated": ConsolidatedLearner, "calibrated": CalibratedLearner}


def run_case(kind, seed):
    start = time.perf_counter()
    cores = {name: cls(100 + seed, **OPTIONS) for name, cls in MODES.items()}
    world = ShiftWorld(400 + seed, n_symbols=16, n_contexts=4)
    actions, labels = random.Random(8000000 + seed), random.Random(8100000 + seed)
    if kind == "noise_then_signal":
        phases = [("initial_noise", 40000, True, 0, 20000),
                  ("signal", 40000, False, 0, 4000)]
    elif kind == "retention":
        phases = [("initial_signal", 20000, False, 0, 20000),
                  ("prolonged_noise", 80000, True, 0, 20000),
                  ("recovery", 40000, False, 0, 2000)]
    elif kind == "variable_noise":
        phases = [("initial_signal", 20000, False, 0, 20000),
                  ("mixed_noise", 12000, True, 0, 2000),
                  ("recovery", 8000, False, 0, 2000)]
    else:
        phases = [("rule_" + str(i), 40000, False, shift, 4000)
                  for i, shift in enumerate((0, 1, 2, 3, 0, 2, 1))]
    curves = {name: [] for name in cores}
    journals = {name: {"searches": [], "decisions": []} for name in cores}
    bounds = {name: {"max_search_history": 0, "max_decision_history": 0,
                     "max_fit_records": 0, "max_allocated_points": 0,
                     "max_sampled_checkpoint_bytes": 0} for name in cores}
    phases_result, resumes = [], []
    evaluation_index = 0
    shadow = None
    remaining = 0
    resume_kinds = set()
    for phase_name, length, noise, shift, interval in phases:
        before = {name: (m.attempts, m.admissions) for name, m in cores.items()}
        scores = {name: {"brier": 0.0, "log_loss": 0.0, "observed_success": 0} for name in cores}
        tail_scores = {name: {"brier": 0.0, "log_loss": 0.0, "observed_success": 0} for name in cores}
        frozen = {name: copy.deepcopy(m.checkpoint()["protected"]) for name, m in cores.items()}
        phase_start = cores["calibrated"].steps
        for local in range(1, length + 1):
            slot = (phase_start + local - 1) % 4
            events, target = world.episode(slot, shift=shift)
            action = actions.randrange(4)
            rate = (.1 if slot < 2 else .6) if kind == "variable_noise" else .25
            y = int(labels.random() < rate) if noise else int(action == target)
            for name, core in cores.items():
                for event in events:
                    p = core.receive(event)
                scores[name]["brier"] += (p[action] - y) ** 2
                scores[name]["log_loss"] -= log_probability(p[action], y)
                scores[name]["observed_success"] += y
                if local > length - min(8000, length):
                    tail_scores[name]["brier"] += (p[action] - y) ** 2
                    tail_scores[name]["log_loss"] -= log_probability(p[action], y)
                    tail_scores[name]["observed_success"] += y
                served = core.learn(action, y)
                assert served == p[action]
                if core.searches and core.searches[-1]["at"] == core.steps:
                    journals[name]["searches"].append(copy.deepcopy(core.searches[-1]))
                if core.decisions and core.decisions[-1]["at"] == core.steps:
                    d = copy.deepcopy(core.decisions[-1])
                    d.update(phase=phase_name, phase_global_labels=local,
                             phase_context_labels=(local + 3) // 4)
                    journals[name]["decisions"].append(d)
                b = bounds[name]
                b["max_search_history"] = max(b["max_search_history"], len(core.searches))
                b["max_decision_history"] = max(b["max_decision_history"], len(core.decisions))
                b["max_fit_records"] = max(b["max_fit_records"], sum(len(t["records"]) for t in core.tasks.values()))
                protected = int(core._protected is not None)
                b["max_allocated_points"] = max(b["max_allocated_points"],
                    (2 + protected + 2 * int(core.trial is not None)) * 8 * 4)
            if shadow is not None:
                for event in events:
                    shadow.receive(event)
                shadow.learn(action, y)
                remaining -= 1
                if remaining == 0:
                    assert canonical(shadow) == canonical(cores["calibrated"])
                    resumes[-1]["verified_future_labels"] = 1024
                    shadow = None
            core = cores["calibrated"]
            if shadow is None and core.trial is not None and core.trial["n"] == 32:
                resume_kind = "targeted" if core.trial["scope"] is not None else None
                if core.attempts > 16 and "renewal" not in resume_kinds:
                    resume_kind = "renewal"
                if resume_kind is not None and resume_kind not in resume_kinds:
                    shadow = CalibratedLearner.restore(json.loads(json.dumps(core.checkpoint())))
                    remaining = 1024
                    resume_kinds.add(resume_kind)
                    resumes.append({"kind": resume_kind, "at": core.steps, "attempt": core.attempts,
                                    "scope": core.trial["scope"], "principal_labels": core.trial["n"],
                                    "verified_future_labels": 0})
            if local % interval == 0:
                evaluation_index += 1
                for name, core in cores.items():
                    result = evaluate(core, seed, shift, evaluation_index)
                    result.update(phase=phase_name, phase_global_labels=local, phase_context_labels=local // 4)
                    if name == "calibrated":
                        result["calibration_by_context"] = {
                            str(slot): core.calibration_parameters(slot) for slot in range(4)}
                    curves[name].append(result)
                    bounds[name]["max_sampled_checkpoint_bytes"] = max(
                        bounds[name]["max_sampled_checkpoint_bytes"],
                        len(json.dumps(core.checkpoint(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
                if phase_name == "recovery" and local == 2000:
                    assert max(x["brier"] for x in curves["calibrated"][-1]["contexts"]) <= .025, "Confidence failed to recover"
                if phase_name in ("prolonged_noise", "mixed_noise"):
                    assert min(x["policy_success"] for x in curves["calibrated"][-1]["contexts"]) >= .95
        modes = {}
        for name, m in cores.items():
            modes[name] = {"attempts_before": before[name][0], "attempts_after": m.attempts,
                           "admissions_before": before[name][1], "admissions_after": m.admissions,
                           "actual_training_scores": {k: v / length for k, v in scores[name].items()},
                           "tail_training_scores": {k: v / min(8000, length) for k, v in tail_scores[name].items()},
                           "final_contexts": curves[name][-1]["contexts"]}
        phases_result.append({"phase": phase_name, "global_labels": length, "labels_per_context": length // 4,
                              "noise": noise, "context_0_shift": shift, "modes": modes})
        a, b = canonical(cores["calibrated"]), canonical(cores["consolidated"])
        a.pop("calibration")
        a["format"], a["implementation"] = b["format"], b["implementation"]
        assert a == b, "Calibration altered competence/search/learning state"
        if noise:
            for name, m in cores.items():
                assert m.checkpoint()["protected"] == frozen[name], "Calibration erased or replaced a competence"
            if phase_name == "prolonged_noise":
                c, r = modes["calibrated"]["actual_training_scores"], modes["consolidated"]["actual_training_scores"]
                assert c["brier"] <= .205 and c["log_loss"] <= .62
                assert c["brier"] < r["brier"] and c["log_loss"] < r["log_loss"]
            if phase_name == "mixed_noise":
                c, r = modes["calibrated"]["tail_training_scores"], modes["consolidated"]["tail_training_scores"]
                assert c["brier"] <= .26 and c["log_loss"] <= .58
                assert c["brier"] < r["brier"] and c["log_loss"] < r["log_loss"]
                for slot in range(4):
                    params = cores["calibrated"].calibration_parameters(slot)
                    assert abs(params["background_rate"] - (.1 if slot < 2 else .6)) <= .10
            assert modes["calibrated"]["admissions_before"] == modes["calibrated"]["admissions_after"], "Admission under independent noise"
        if not noise:
            assert min(x["policy_success"] for x in modes["calibrated"]["final_contexts"]) >= .95, "Competence or minority-context adaptation failed"
    if shadow is not None:
        assert canonical(shadow) == canonical(cores["calibrated"])
        resumes[-1]["verified_future_labels"] = 1024 - remaining
    if kind in ("noise_then_signal", "retention"):
        assert "renewal" in resume_kinds
    elif kind == "successive_changes":
        assert "targeted" in resume_kinds
    for name, b in bounds.items():
        assert b["max_search_history"] <= 16 and b["max_fit_records"] <= 1024
        assert b["max_decision_history"] <= 80
        assert b["max_allocated_points"] <= 160
    assert cores["calibrated"].metrics()["calibration_probability_cache"] <= 1024
    return {"case": kind, "seed": seed, "training_labels": cores["calibrated"].steps,
            "evaluation_episodes_per_point": 2048, "elapsed_seconds": time.perf_counter() - start,
            "phases": phases_result, "curves": curves, "journals": journals, "bounds": bounds,
            "resumes": resumes, "final_metrics": {name: m.metrics() for name, m in cores.items()}}


def summarize(c):
    return {"case": c["case"], "seed": c["seed"],
            "phases": [{"phase": p["phase"], "noise": p["noise"], "modes": {
                name: {"attempts": m["attempts_after"], "admissions": m["admissions_after"],
                       "policy_by_context": [x["policy_success"] for x in m["final_contexts"]],
                       "actual_training_scores": m["actual_training_scores"],
                       "tail_training_scores": m["tail_training_scores"]}
                for name, m in p["modes"].items()}} for p in c["phases"]],
            "bounds": c["bounds"], "resumes": c["resumes"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    cases = []
    for kind in ("noise_then_signal", "retention", "successive_changes", "variable_noise"):
        for seed in (0, 1, 2):
            case = run_case(kind, seed)
            cases.append(case)
            print("CALIBRATION_CASE " + json.dumps(summarize(case), sort_keys=True), flush=True)
    report = {"protocol": "CALIBRATION_PROTOCOL.md", "protocol_version": 1,
              "engine_commit": subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                               capture_output=True, text=True).stdout.strip(),
              "runner": platform.system(), "python": platform.python_version(), "options": OPTIONS,
              "cases": cases, "summary": [summarize(c) for c in cases]}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CALIBRATION_FULL_JSON " + json.dumps(report, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
