"""Predeclared long-session search renewal and retention measurements."""
import argparse
import copy
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import time

from first_piece.shared import SharedLearner
from first_piece.renewable import RenewableLearner
from first_piece.scale_world import ScaleWorld

OPTIONS = dict(max_tasks=8, max_symbols=16, n_actions=4)
MODES = {"finite": SharedLearner, "renewable": RenewableLearner}


class ShiftWorld(ScaleWorld):
    def episode(self, context, *, shift=0):
        events, target = super().episode(context)
        return events, (target + shift) % 4 if context == 0 else target


def evaluate(core, seed, shift, evaluation_index):
    # Restore validates the full resume ledger; the training state is untouched.
    clone = type(core).restore(core.checkpoint())
    world = ShiftWorld(400 + seed, n_symbols=16, n_contexts=4)
    world.rng = random.Random(70000000 + 100000 * seed + evaluation_index)
    contexts = []
    for slot in range(4):
        correct, loss = 0, 0.0
        for _ in range(512):
            events, target = world.episode(slot, shift=shift)
            for event in events:
                p = clone.receive(event)
            correct += max(range(4), key=p.__getitem__) == target
            loss += sum((v - int(a == target)) ** 2 for a, v in enumerate(p)) / 4
            clone.finish_evaluation()
        contexts.append({"context": slot, "episodes": 512,
                         "policy_success": correct / 512, "brier": loss / 512})
    return {"global_labels": core.steps, "labels_per_context": {
                str(k): v["steps"] for k, v in core.tasks.items()},
            "attempts": core.attempts, "admissions": core.admissions,
            "contexts": contexts}


def canonical(core):
    data = core.checkpoint()
    for s in data["searches"]:
        s["elapsed_seconds"] = 0
    return data


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
    else:
        phases = [("rule_" + str(i), 40000, False, shift, 4000)
                  for i, shift in enumerate((0, 1, 2, 3, 0, 2, 1))]
    curves = {name: [] for name in cores}
    journals = {name: {"searches": [], "decisions": []} for name in cores}
    limits = {name: {"max_search_history": 0, "max_decision_history": 0,
                     "max_fit_records": 0, "max_allocated_points": 0,
                     "max_checkpoint_bytes": 0} for name in cores}
    phases_result = []
    evaluation_index = 0
    resumed = None
    resume_origin = None
    resume_verified = 0
    for phase_name, length, noise, shift, interval in phases:
        before = {name: {"attempts": m.attempts, "admissions": m.admissions}
                  for name, m in cores.items()}
        phase_start = next(iter(cores.values())).steps
        for local in range(1, length + 1):
            slot = (phase_start + local - 1) % 4
            events, target = world.episode(slot, shift=shift)
            action = actions.randrange(4)
            y = int(labels.random() < .25) if noise else int(action == target)
            models = list(cores.items())
            if resumed is not None:
                models.append(("resume_shadow", resumed))
            for name, core in models:
                for event in events:
                    core.receive(event)
                core.learn(action, y)
                if name == "resume_shadow":
                    continue
                journal, bound = journals[name], limits[name]
                if core.searches and core.searches[-1]["at"] == core.steps:
                    journal["searches"].append(copy.deepcopy(core.searches[-1]))
                if core.decisions and core.decisions[-1]["at"] == core.steps:
                    entry = copy.deepcopy(core.decisions[-1])
                    entry["phase"] = phase_name
                    entry["phase_global_labels"] = local
                    entry["phase_context_labels"] = local // 4 + int(local % 4 > 0)
                    journal["decisions"].append(entry)
                bound["max_search_history"] = max(bound["max_search_history"], len(core.searches))
                bound["max_decision_history"] = max(bound["max_decision_history"], len(core.decisions))
                bound["max_fit_records"] = max(bound["max_fit_records"],
                                              sum(len(t["records"]) for t in core.tasks.values()))
                bound["max_allocated_points"] = max(bound["max_allocated_points"],
                    2 * core.active.n_routes * 4 * (2 if core.trial else 1))
            if resumed is not None:
                resume_verified += 1
                if resume_verified == 1024:
                    assert canonical(resumed) == canonical(cores["renewable"])
                    resumed = None
            model = cores["renewable"]
            if resume_origin is None and model.attempts > model.config["max_attempts"] and model.trial is not None and model.trial["n"] == 32:
                resumed = RenewableLearner.restore(json.loads(json.dumps(model.checkpoint())))
                resume_origin = {"global_label": model.steps, "attempt": model.attempts,
                                 "principal_labels": model.trial["n"],
                                 "search_block": model.metrics()["search_block"]}
            if local % interval == 0:
                evaluation_index += 1
                for name, core in cores.items():
                    result = evaluate(core, seed, shift, evaluation_index)
                    result.update(phase=phase_name, phase_global_labels=local,
                                  phase_context_labels=local // 4)
                    curves[name].append(result)
                    limits[name]["max_checkpoint_bytes"] = max(limits[name]["max_checkpoint_bytes"],
                        len(json.dumps(core.checkpoint(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
        phase_result = {"phase": phase_name, "global_labels": length,
                        "labels_per_context": length // 4, "noise": noise, "context_0_shift": shift,
                        "modes": {name: {"attempts_before": before[name]["attempts"],
                                         "attempts_after": m.attempts,
                                         "admissions_before": before[name]["admissions"],
                                         "admissions_after": m.admissions,
                                         "final_contexts": curves[name][-1]["contexts"]}
                                  for name, m in cores.items()}}
        phases_result.append(phase_result)
        if noise and phase_name == "initial_noise":
            assert cores["finite"].attempts == 16, "Control failed to exhaust its finite budget"
            assert cores["renewable"].attempts > 16, "Renewal did not occur"
            assert all(m.admissions == 0 for m in cores.values()), "Admission observed under independent noise"
    if resumed is not None:
        assert canonical(resumed) == canonical(cores["renewable"])
    if kind == "noise_then_signal":
        final = curves["renewable"][-1]["contexts"]
        assert min(r["policy_success"] for r in final) >= .95, "Renewal did not recover structured competence"
        assert cores["renewable"].admissions >= 1
        assert resume_origin is not None and resume_verified >= 1024
    for name in cores:
        assert limits[name]["max_search_history"] <= 16
        assert limits[name]["max_decision_history"] <= 48
        assert limits[name]["max_fit_records"] <= 4 * 256
        assert limits[name]["max_allocated_points"] <= 128
    return {"case": kind, "seed": seed, "training_labels": next(iter(cores.values())).steps,
            "training_actions": "uniform independent exploration",
            "evaluation_episodes_per_point": 2048,
            "elapsed_seconds": time.perf_counter() - start,
            "resume": {"origin": resume_origin, "verified_future_labels": resume_verified,
                       "identical_except_search_wall_time": resume_origin is not None},
            "phases": phases_result, "curves": curves, "journals": journals, "bounds": limits,
            "final_metrics": {name: m.metrics() for name, m in cores.items()}}


def summary(cases):
    result = []
    for c in cases:
        final = c["phases"][-1]["modes"]
        item = {"case": c["case"], "seed": c["seed"], "training_labels": c["training_labels"],
                "final_modes": {}, "resume": c["resume"]}
        for name, r in final.items():
            item["final_modes"][name] = {
                "attempts": r["attempts_after"], "admissions": r["admissions_after"],
                "policy_by_context": [v["policy_success"] for v in r["final_contexts"]],
                "brier_by_context": [v["brier"] for v in r["final_contexts"]],
                "bounds": c["bounds"][name]}
        if c["case"] == "retention":
            item["retention_boundaries"] = [
                {"phase": p["phase"], "modes": {name: [r["policy_success"] for r in q["final_contexts"]]
                                               for name, q in p["modes"].items()}}
                for p in c["phases"]]
        if c["case"] == "successive_changes":
            item["unchanged_context_minimum"] = {
                name: min(r["policy_success"] for p in points if p["phase"] != "rule_0"
                          for r in p["contexts"] if r["context"] != 0)
                for name, points in c["curves"].items()}
        result.append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    cases = []
    for kind in ("noise_then_signal", "retention", "successive_changes"):
        for seed in (0, 1, 2):
            case = run_case(kind, seed)
            cases.append(case)
            print("RENEWABLE_CASE " + json.dumps(summary([case])[0], sort_keys=True), flush=True)
    report = {"protocol": "RENEWABLE_SEARCH_PROTOCOL.md", "protocol_version": 1,
              "engine_commit": subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                               capture_output=True, text=True).stdout.strip(),
              "runner": platform.system(), "python": platform.python_version(),
              "options": OPTIONS, "finite_lifetime_alpha": .05, "fresh_renewable_lifetime_alpha": .05,
              "cases": cases, "summary": summary(cases)}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RENEWABLE_FULL_JSON " + json.dumps(report, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
