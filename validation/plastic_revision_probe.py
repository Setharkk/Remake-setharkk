"""Predeclared plastic transfer, latency ablations and scale measurements."""
import argparse
import copy
import json
from pathlib import Path
import platform
import random
import subprocess
import time

from first_piece.calibrated import CalibratedLearner
from first_piece.plastic_revision import PlasticRevisionLearner
from first_piece.shared import log_probability
from .renewable_probe import ShiftWorld, evaluate, canonical, OPTIONS

MODES = {"calibrated": CalibratedLearner, "plastic_revision": PlasticRevisionLearner}
ABLATIONS = {"range_only": lambda *a, **k: PlasticRevisionLearner(*a, reuse_plastic_weights=False, **k),
             "warm_only": lambda *a, **k: PlasticRevisionLearner(*a, bounded_validation_ranges=False, **k)}


def run_case(kind, seed, modes=None):
    modes = MODES if modes is None else modes
    revised = next(name for name in modes if name != "calibrated")
    failures = []
    def check(condition, message):
        if not condition:
            failures.append(message)
    start = time.perf_counter()
    cores = {name: cls(100 + seed, **OPTIONS) for name, cls in modes.items()}
    world = ShiftWorld(400 + seed, n_symbols=16, n_contexts=4)
    actions, labels = random.Random(8000000 + seed), random.Random(8100000 + seed)
    if kind == "noise_then_signal":
        phases = [("initial_noise", 40000, True, 0, 20000),
                  ("signal", 40000, False, 0, 1000)]
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
        phase_start = cores[revised].steps
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
                for entry in reversed(core.decisions):
                    if entry["at"] != core.steps:
                        break
                    d = copy.deepcopy(entry)
                    d.update(phase=phase_name, phase_global_labels=local,
                             phase_context_labels=(local + 3) // 4)
                    journals[name]["decisions"].append(d)
                if core.decisions and core.decisions[-1]["at"] == core.steps:
                    if journals[name]["searches"] and core.searches:
                        journals[name]["searches"][-1] = copy.deepcopy(core.searches[-1])
                b = bounds[name]
                b["max_search_history"] = max(b["max_search_history"], len(core.searches))
                b["max_decision_history"] = max(b["max_decision_history"], len(core.decisions))
                b["max_fit_records"] = max(b["max_fit_records"], sum(len(t["records"]) for t in core.tasks.values()))
                protected = int(core._protected is not None)
                b["max_allocated_points"] = max(b["max_allocated_points"],
                    (2 + protected + int(getattr(core, "_frozen_reference", None) is not None) + 2 * int(core.trial is not None)) * 8 * 4)
            if shadow is not None:
                for event in events:
                    shadow.receive(event)
                shadow.learn(action, y)
                remaining -= 1
                if remaining == 0:
                    assert canonical(shadow) == canonical(cores[revised])
                    resumes[-1]["verified_future_labels"] = 1024
                    shadow = None
            core = cores[revised]
            if shadow is None and core.trial is not None and core.trial["n"] == 32:
                resume_kind = "targeted" if core.trial["scope"] is not None else None
                if core.attempts > 16 and "renewal" not in resume_kinds:
                    resume_kind = "renewal"
                if resume_kind is not None and resume_kind not in resume_kinds:
                    shadow = type(core).restore(json.loads(json.dumps(core.checkpoint())))
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
                    if isinstance(core, CalibratedLearner):
                        result["calibration_by_context"] = {
                            str(slot): core.calibration_parameters(slot) for slot in range(4)}
                    curves[name].append(result)
                    bounds[name]["max_sampled_checkpoint_bytes"] = max(
                        bounds[name]["max_sampled_checkpoint_bytes"],
                        len(json.dumps(core.checkpoint(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
                if phase_name == "recovery" and local == 2000:
                    check(max(x["brier"] for x in curves[revised][-1]["contexts"]) <= .025, "Confidence failed to recover")
                if phase_name in ("prolonged_noise", "mixed_noise"):
                    check(min(x["policy_success"] for x in curves[revised][-1]["contexts"]) >= .95, "Noise policy below 95% at " + str(core.steps))
        modes = {}
        for name, m in cores.items():
            modes[name] = {"attempts_before": before[name][0], "attempts_after": m.attempts,
                           "admissions_before": before[name][1], "admissions_after": m.admissions,
                           "actual_training_scores": {k: v / length for k, v in scores[name].items()},
                           "tail_training_scores": {k: v / min(8000, length) for k, v in tail_scores[name].items()},
                           "final_contexts": curves[name][-1]["contexts"]}
        phases_result.append({"phase": phase_name, "global_labels": length, "labels_per_context": length // 4,
                              "noise": noise, "context_0_shift": shift, "modes": modes})
        if noise:
            for name, m in cores.items():
                check(m.checkpoint()["protected"] == frozen[name], name + ": competence changed during " + phase_name)
            if phase_name == "prolonged_noise":
                c = modes[revised]["actual_training_scores"]
                check(c["brier"] <= .205 and c["log_loss"] <= .62, "Retention noise scores exceed limits")
            if phase_name == "mixed_noise":
                c = modes[revised]["tail_training_scores"]
                check(c["brier"] <= .26 and c["log_loss"] <= .58, "Variable noise scores exceed limits")
                for slot in range(4):
                    params = cores[revised].calibration_parameters(slot)
                    check(abs(params["background_rate"] - (.1 if slot < 2 else .6)) <= .10, "Incorrect background rate")
            check(modes[revised]["admissions_before"] == modes[revised]["admissions_after"], "Admission under independent noise")
        if not noise:
            check(min(x["policy_success"] for x in modes[revised]["final_contexts"]) >= .95, "Final competence below 95% in " + phase_name)
    if shadow is not None:
        assert canonical(shadow) == canonical(cores[revised])
        resumes[-1]["verified_future_labels"] = 1024 - remaining
    if kind == "successive_changes":
        assert "targeted" in resume_kinds
    for name, b in bounds.items():
        assert b["max_search_history"] <= 16 and b["max_fit_records"] <= 1024
        assert b["max_decision_history"] <= (96 if isinstance(cores[name], PlasticRevisionLearner) else 80)
        assert b["max_allocated_points"] <= 160
    assert cores[revised].metrics()["calibration_probability_cache"] <= 1024
    delays = {}
    if kind == "noise_then_signal":
        for name in cores:
            signal = [point for point in curves[name] if point["phase"] == "signal"]
            qualified = [min(x["policy_success"] for x in point["contexts"]) >= .95 for point in signal]
            first = next((signal[i]["phase_global_labels"] for i in range(len(signal)-1)
                          if qualified[i] and qualified[i+1]), None)
            confirmation = None if first is None else first + 1000
            admissions = [d for d in journals[name]["decisions"]
                          if d["phase"] == "signal" and d["decision"] == "accept"]
            delays[name] = {"first_admission_global_labels": admissions[0]["phase_global_labels"] if admissions else None,
                            "full_competence_global_labels": first, "confirmation_global_labels": confirmation}
        if "plastic_revision" in cores:
            first = delays["plastic_revision"]["full_competence_global_labels"]
            check(first is not None and first <= 12000, "Cold full competence exceeds 12000: " + str(first))
    return {"case": kind, "seed": seed, "criteria_failures": failures, "delays": delays, "training_labels": cores[revised].steps,
            "evaluation_episodes_per_point": 2048, "elapsed_seconds": time.perf_counter() - start,
            "phases": phases_result, "curves": curves, "journals": journals, "bounds": bounds,
            "resumes": resumes, "final_metrics": {name: m.metrics() for name, m in cores.items()}}


def summarize(c):
    return {"case": c["case"], "seed": c["seed"], "criteria_failures": c["criteria_failures"],
            "phases": [{"phase": p["phase"], "noise": p["noise"], "modes": {
                name: {"attempts": m["attempts_after"], "admissions": m["admissions_after"],
                       "policy_by_context": [x["policy_success"] for x in m["final_contexts"]],
                       "actual_training_scores": m["actual_training_scores"],
                       "tail_training_scores": m["tail_training_scores"]}
                for name, m in p["modes"].items()}} for p in c["phases"]],
            "bounds": c["bounds"], "resumes": c["resumes"], "delays": c["delays"]}



SCALE_OPTIONS = dict(max_tasks=17, max_symbols=64, n_actions=4)


def evaluate_scale(core, seed, shift, index, *, fresh=False):
    clone = type(core).restore(core.checkpoint())
    world = ShiftWorld(400 + seed, n_symbols=64, n_contexts=16)
    world.rng = random.Random(72000000 + seed*100000 + index)
    contexts = []
    for slot in ([16] if fresh else range(16)):
        count = 512 if fresh else 128
        correct, loss = 0, 0.0
        for _ in range(count):
            events, target = world.episode(slot, shift=shift)
            for event in events:
                p = clone.receive(event)
            correct += max(range(4), key=p.__getitem__) == target
            loss += sum((value-int(a == target))**2 for a, value in enumerate(p))/4
            clone.finish_evaluation()
        contexts.append({"context": slot, "episodes": count,
                         "policy_success": correct/count, "brier": loss/count})
    return {"global_labels": core.steps, "contexts": contexts,
            "attempts": core.attempts, "admissions": core.admissions}


def run_scale(seed):
    start = time.perf_counter()
    core = PlasticRevisionLearner(100+seed, **SCALE_OPTIONS)
    world = ShiftWorld(400+seed, n_symbols=64, n_contexts=16)
    actions, labels = random.Random(8200000+seed), random.Random(8300000+seed)
    phases = [("initial_noise", 16000, True, 0, (1000,)),
              ("initial_signal", 160000, False, 0, (100, 1000, 2500, 10000)),
              ("prolonged_noise", 64000, True, 0, (1000, 2000, 4000)),
              ("recovery", 32000, False, 0, (512, 1024, 2000)),
              ("change", 160000, False, 1, (100, 500, 1000, 2000, 4000, 6000, 10000))]
    curves, phase_results, searches, decisions, resumes = [], [], [], [], []
    bounds = {"max_search_history": 0, "max_decision_history": 0, "max_fit_records": 0,
              "max_allocated_points": 0, "max_sampled_checkpoint_bytes": 0,
              "max_probability_cache": 0}
    shadow, remaining, index = None, 0, 0
    for phase, length, noise, shift, looks in phases:
        before_admissions = core.admissions
        protected = copy.deepcopy(core.checkpoint()["protected"])
        score = {"brier": 0.0, "log_loss": 0.0, "observed_success": 0}
        phase_start = core.steps
        for local in range(1, length+1):
            slot = (phase_start+local-1)%16
            events, target = world.episode(slot, shift=shift)
            action = actions.randrange(4)
            outcome = int(labels.random() < .25) if noise else int(action == target)
            for event in events:
                p = core.receive(event)
            score["brier"] += (p[action]-outcome)**2
            score["log_loss"] -= log_probability(p[action], outcome)
            score["observed_success"] += outcome
            assert core.learn(action, outcome) == p[action]
            if core.searches and core.searches[-1]["at"] == core.steps:
                searches.append(copy.deepcopy(core.searches[-1]))
            for d in reversed(core.decisions):
                if d["at"] != core.steps:
                    break
                entry = copy.deepcopy(d)
                entry.update(phase=phase, phase_global_labels=local,
                             phase_context_labels=(local+15)//16)
                decisions.append(entry)
            if core.decisions and core.decisions[-1]["at"] == core.steps and searches:
                searches[-1] = copy.deepcopy(core.searches[-1])
            bounds["max_search_history"] = max(bounds["max_search_history"], len(core.searches))
            bounds["max_decision_history"] = max(bounds["max_decision_history"], len(core.decisions))
            bounds["max_fit_records"] = max(bounds["max_fit_records"],
                                            sum(len(t["records"]) for t in core.tasks.values()))
            points = (2+int(core._protected is not None)+int(core._frozen_reference is not None)
                      +2*int(core.trial is not None))*32
            bounds["max_allocated_points"] = max(bounds["max_allocated_points"], points)
            if shadow is not None:
                for event in events:
                    shadow.receive(event)
                shadow.learn(action, outcome)
                remaining -= 1
                if not remaining:
                    assert canonical(core) == canonical(shadow)
                    resumes[-1]["verified_future_labels"] = 1024
                    shadow = None
            if (not resumes and core.trial is not None and core.trial["scope"] is not None
                    and core.trial["n"] == 32):
                shadow = type(core).restore(json.loads(json.dumps(core.checkpoint())))
                remaining = 1024
                resumes.append({"at": core.steps, "scope": core.trial["scope"],
                                "attempt": core.attempts, "verified_future_labels": 0})
            if local in {16*n for n in looks}:
                index += 1
                result = evaluate_scale(core, seed, shift, index)
                result.update(phase=phase, phase_global_labels=local, phase_context_labels=local//16)
                curves.append(result)
                bounds["max_sampled_checkpoint_bytes"] = max(bounds["max_sampled_checkpoint_bytes"],
                    len(json.dumps(core.checkpoint(), separators=(",", ":")).encode("utf-8")))
                bounds["max_probability_cache"] = max(bounds["max_probability_cache"],
                                                       core.metrics()["calibration_probability_cache"])
                if phase in ("prolonged_noise", "recovery"):
                    assert min(x["policy_success"] for x in result["contexts"]) >= .95
                if phase == "change":
                    assert min(x["policy_success"] for x in result["contexts"][1:]) >= .95
                if phase == "recovery" and local == 512*16:
                    assert max(x["brier"] for x in result["contexts"]) <= .025
        score = {key: value/length for key, value in score.items()}
        phase_results.append({"phase": phase, "global_labels": length,
                              "labels_per_context": length//16, "noise": noise,
                              "admissions_before": before_admissions, "admissions_after": core.admissions,
                              "actual_training_scores": score, "final_contexts": curves[-1]["contexts"]})
        if noise:
            assert core.admissions == before_admissions
            assert core.checkpoint()["protected"] == protected
            if phase == "prolonged_noise":
                assert score["brier"] <= .205 and score["log_loss"] <= .62
        else:
            assert min(x["policy_success"] for x in curves[-1]["contexts"]) >= .95
    assert resumes and resumes[0]["verified_future_labels"] == 1024
    index += 1
    fresh = evaluate_scale(core, seed, 1, index, fresh=True)
    assert fresh["contexts"][0]["policy_success"] >= .95
    assert bounds["max_search_history"] <= 16 and bounds["max_decision_history"] <= 96
    assert bounds["max_fit_records"] <= 4096 and bounds["max_allocated_points"] <= 160
    assert bounds["max_probability_cache"] <= 4096
    return {"case": "scale_64_16", "seed": seed, "training_labels": core.steps,
            "elapsed_seconds": time.perf_counter()-start, "phases": phase_results,
            "curves": curves, "searches": searches, "decisions": decisions,
            "fresh_context": fresh, "bounds": bounds, "resumes": resumes,
            "final_metrics": core.metrics()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-cold", action="store_true")
    args = parser.parse_args()
    cases, scales = [], []
    kinds = ("noise_then_signal",) if args.quick else ("retention", "successive_changes", "variable_noise") if args.skip_cold else ("noise_then_signal", "retention", "successive_changes", "variable_noise")
    for kind in kinds:
        for seed in (0, 1, 2):
            case = run_case(kind, seed)
            cases.append(case)
            print("PLASTIC_REVISION_CASE " + json.dumps(summarize(case), sort_keys=True), flush=True)
    if not args.quick:
        for seed in (0, 1, 2):
            case = run_case("noise_then_signal", seed, ABLATIONS)
            case["case"] = "cold_ablations"
            cases.append(case)
            print("PLASTIC_REVISION_CASE " + json.dumps(summarize(case), sort_keys=True), flush=True)
        for seed in (0, 1, 2):
            case = run_scale(seed)
            scales.append(case)
            print("PLASTIC_REVISION_SCALE " + json.dumps({k: v for k,v in case.items()
                          if k not in ("curves", "searches", "decisions")}, sort_keys=True), flush=True)
    report = {"protocol": "PLASTIC_REVISION_PROTOCOL.md", "protocol_version": 1,
              "engine_commit": subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                               capture_output=True, text=True).stdout.strip(),
              "runner": platform.system(), "python": platform.python_version(),
              "options": OPTIONS, "scale_options": SCALE_OPTIONS,
              "cases": cases, "scale_cases": scales, "summary": [summarize(c) for c in cases]}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PLASTIC_REVISION_FULL_JSON " + json.dumps(report, separators=(",", ":")), flush=True)
    failures = [(c["case"], c["seed"], c["criteria_failures"]) for c in cases if c["criteria_failures"]]
    assert not failures, failures


if __name__ == "__main__":
    main()
