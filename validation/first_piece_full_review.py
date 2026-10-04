"""Reproduce active first-piece defects without changing the learner.

This diagnostic expects the frozen review source. Its success means that
observations and positive controls were reproduced, not that defects are fixed.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import time

from first_piece.shared import SharedLearner, SharedSpherePredictor
from first_piece.shared_adapter import SharedAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.scale_run import check_bounds
from first_piece.spherical import SpherePredictor, dot, exp_map, log_map, unit
from first_piece.temporal import TemporalLearner, feature_route
from first_piece.temporal_world import TemporalWorld
from first_piece.temporal_run import episode as temporal_episode
from first_piece.tests.test_shared import wire_symbol

REVIEWED_SOURCE = "0b19465aa6be9aacf291b077cdc69f1b4e44580f"


def feed(model, events, action, target):
    probabilities = None
    for event in events:
        probabilities = model.receive(event)
    returned = model.learn(action, int(action == target))
    return probabilities, returned


def train(model, world, n, *, seed=801, changed=False, noise=False):
    rng = random.Random(seed)
    for i in range(n):
        events, target = world.episode(i % world.n_contexts, changed=changed)
        if noise:
            target = rng.randrange(world.n_actions)
        feed(model, events, rng.randrange(world.n_actions), target)


def policy(model, world, *, slot=0, changed=False, n=512):
    clone = SharedLearner.restore(model.checkpoint())
    # Keep symbol identities/rule, reserve a new input RNG for evaluation.
    world.rng = random.Random(71000000 + world.seed)
    correct = 0
    for _ in range(n):
        events, target = world.episode(slot, changed=changed)
        for event in events:
            p = clone.receive(event)
        correct += max(range(len(p)), key=p.__getitem__) == target
        clone.finish_evaluation()
    return correct / n


def single_context():
    original = SharedLearner(91)
    control = SharedLearner(91, min_records=256)
    world = ScaleWorld(31, n_contexts=1)
    rng = random.Random(801)
    for _ in range(20000):
        events, target = world.episode(0)
        action = rng.randrange(4)
        for model in (original, control):
            feed(model, events, action, target)
    p_original = policy(original, ScaleWorld(31, n_contexts=1))
    p_control = policy(control, ScaleWorld(31, n_contexts=1))
    assert original.attempts == 0 and not original.program
    assert len(original.tasks[0]["records"]) == 256
    assert control.admissions > 0 and p_control >= .95
    return {"training_labels_per_model": 20000, "default_fit_records": 256,
            "default_min_records": 512, "default_attempts": original.attempts,
            "default_status": original.metrics()["status"],
            "default_policy_success": p_original, "control_policy_success": p_control,
            "control_attempts": control.attempts, "control_admissions": control.admissions,
            "control_only_change": "min_records=256", "evaluation_episodes_per_model": 512}


def disappearing_scope():
    model = SharedLearner(91, max_tasks=2, n_actions=2)
    world = ScaleWorld(31, n_contexts=2, n_actions=2)
    train(model, world, 10000)
    assert model.program and model.trial is None
    rng = random.Random(951)
    for changed_labels in range(1, 4097):
        events, target = world.episode(0, changed=True)
        feed(model, events, rng.randrange(2), target)
        if model.trial is not None:
            break
    assert model.trial is not None and model.trial["scope"] == 0
    before = copy.deepcopy(model.trial)
    attempts, steps = model.attempts, model.steps
    frozen = model.candidate.checkpoint()
    old_active = model.active.checkpoint()
    # Only context 1 now returns; its own rule is also inverted.
    for _ in range(5000):
        events, target = world.episode(1)
        feed(model, events, rng.randrange(2), 1 - target)
    assert model.trial["n"] == before["n"]
    assert model.trial["other_n"] == before["other_n"] + 5000
    assert model.attempts == attempts and model.steps == steps + 5000
    assert model.candidate.checkpoint() == frozen
    assert model.active.checkpoint() != old_active
    return {"acquisition_labels": 10000, "changed_scope_labels_until_trial": changed_labels,
            "scope": 0, "principal_n_before": before["n"],
            "principal_n_after": model.trial["n"], "other_labels_added": 5000,
            "attempts_before": attempts, "attempts_after": model.attempts,
            "status": model.metrics()["status"], "candidate_still_frozen": True,
            "live_weights_still_update": True,
            "other_context_recent_brier": sum(model.tasks[1]["losses"]) / len(model.tasks[1]["losses"])}


def shared_ablation():
    model = SharedLearner(91, max_tasks=2, n_actions=2, use_structure=False)
    world = ScaleWorld(31, n_contexts=2, n_actions=2)
    train(model, world, 10000)
    assert model.program
    gaps, loss_gaps, rows = [], [], []
    for i in range(32):
        events, target = world.episode(i % 2)
        for event in events:
            served = model.receive(event)
        action, y = i % 2, int(i % 2 == target)
        slot = model.episode["task"]
        returned = model.learn(action, y)
        recorded = model.tasks[slot]["losses"][-1]
        gaps.append(abs(returned - served[action]))
        loss_gaps.append(abs(recorded - (served[action] - y) ** 2))
        if i < 4:
            rows.append({"served_p": served[action], "learn_return_p": returned,
                         "recorded_brier": recorded, "served_brier": (served[action] - y) ** 2})
    assert max(gaps) > .1 and max(loss_gaps) > .1
    return {"training_labels": 10000, "admitted_program": model.program,
            "comparison_episodes": 32, "maximum_probability_gap": max(gaps),
            "maximum_brier_gap": max(loss_gaps), "examples": rows}


def temporal_ablation():
    model, world = TemporalLearner(105, use_structure=False), TemporalWorld(72)
    rng = random.Random(8101)
    for _ in range(6000):
        temporal_episode(world, [model], rng.randrange(2))
    state = model.tasks[0]
    assert state["feature"] is not None
    gaps = []
    for i in range(32):
        while True:
            event = world.next_event()
            served = model.receive(event)
            if served is not None:
                break
        action = i % 2
        y = world.act(action)
        active_route = feature_route(model.episode["mask"], model.episode["before"], state["feature"])
        active_p = state["active"].probability(action, active_route)
        model.learn(action, y)
        loss = state["losses"][-1]
        assert abs(loss - (active_p - y) ** 2) < 1e-12
        gaps.append(abs(loss - (served[action] - y) ** 2))
    assert max(gaps) > .1
    return {"training_labels": 6000, "feature": state["feature"],
            "comparison_episodes": 32, "maximum_recorded_vs_served_brier_gap": max(gaps)}


def accepted_antipode():
    adapter = SharedAdapter()
    snapshot = adapter.checkpoint()
    for row in snapshot["learner"]["active"]["points"]:
        row[0] = [-1.0, 0.0, 0.0]
    restored = SharedAdapter.restore(json.loads(json.dumps(snapshot)))
    restored.submit_observation(wire_symbol(0, "opaque:a"))
    prediction = restored.submit_observation(wire_symbol(1, "sealed", end=True))
    from first_piece.integration_probe import agent_proposal, observed_receipt
    request = restored.register_action(agent_proposal(prediction, 0), executor_id="executor")
    before = restored.checkpoint()
    error = None
    try:
        restored.submit_receipt(observed_receipt(request, 0))
    except ValueError as exc:
        error = str(exc)
    assert error == "Antipodal logarithm is not unique"
    assert before == restored.checkpoint()
    return {"snapshot_manually_mutated": True, "restore_accepted": True,
            "prediction_finite": math.isfinite(prediction["forecasts"][0]["distribution"]["parameters"]["p"]),
            "learning_error": error, "adapter_transaction_rolled_back": True,
            "normal_training_reaches_this_point_proven": False}


def inconsistent_restore():
    model, world = SharedLearner(5, max_tasks=4), ScaleWorld(1, n_contexts=4)
    train(model, world, 512)
    assert model.trial
    pristine = model.checkpoint()
    bad_counts = copy.deepcopy(pristine)
    bad_counts["active"]["counts"][0][0] += 1
    accepted = SharedLearner.restore(bad_counts)
    bound_failed = False
    try:
        check_bounds(accepted)
    except AssertionError:
        bound_failed = True
    assert bound_failed
    bad_history = copy.deepcopy(pristine)
    bad_history["searches"][0] = {"attempt": 999999, "scope": "not-a-slot"}
    accepted_history = SharedLearner.restore(bad_history)
    assert accepted_history.searches == bad_history["searches"]
    adapter = SharedAdapter()
    adapter.submit_observation(wire_symbol(0, "opaque:a"))
    bad_event = adapter.checkpoint()
    bad_event["last_observation"]["payload"]["value"] = "opaque:b"
    accepted_event = SharedAdapter.restore(bad_event)
    assert accepted_event.checkpoint()["learner"]["symbols"] == ["opaque:a"]
    assert accepted_event.checkpoint()["last_observation"]["payload"]["value"] == "opaque:b"
    return {"snapshots_manually_mutated": True, "unequal_live_counts_restore_accepted": True,
            "existing_scale_bounds_then_fail": True,
            "impossible_search_lineage_restore_accepted": True,
            "last_token_absent_from_restored_memory_accepted": True,
            "pristine_snapshot_roundtrip": SharedLearner.restore(pristine).checkpoint() == pristine}


def oversized_seed():
    model = SharedLearner(2**53 + 1)
    snapshot = json.loads(json.dumps(model.checkpoint()))
    error = None
    try:
        SharedLearner.restore(snapshot)
    except ValueError as exc:
        error = str(exc)
    assert error is not None
    return {"constructor_accepted_seed": str(2**53 + 1), "json_restore_error": error,
            "ordinary_seed_roundtrip": SharedLearner.restore(SharedLearner(91).checkpoint()).config["seed"] == 91}


def exhausted_budget():
    model = SharedLearner(17, max_tasks=2, max_symbols=8, n_actions=2)
    world = ScaleWorld(61, n_symbols=8, n_contexts=2, n_actions=2)
    train(model, world, 20000, seed=8101, noise=True)
    assert model.attempts == 16 and model.trial is None and not model.program
    attempts = model.attempts
    updates = model.neural_updates
    fresh = SharedLearner(17, max_tasks=2, max_symbols=8, n_actions=2)
    rng = random.Random(4001)
    for i in range(20000):
        events, target = world.episode(i % 2)
        action = rng.randrange(2)
        for m in (model, fresh):
            feed(m, events, action, target)
    success = policy(model, ScaleWorld(61, n_symbols=8, n_contexts=2, n_actions=2))
    control_success = policy(fresh, ScaleWorld(61, n_symbols=8, n_contexts=2, n_actions=2))
    assert model.attempts == attempts and not model.program
    assert fresh.admissions and control_success >= .95
    return {"noise_labels": 20000, "subsequent_structured_labels_per_model": 20000,
            "attempts_after_noise": attempts, "attempts_after_structure": model.attempts,
            "additional_gradient_updates": model.neural_updates - updates,
            "exhausted_policy_success": success, "fresh_policy_success": control_success,
            "fresh_attempts": fresh.attempts, "fresh_admissions": fresh.admissions,
            "evaluation_episodes_per_model": 512}


def aging():
    results = []
    for exposure in (1000, 100000):
        model = SpherePredictor()
        for _ in range(exposure):
            model.update(0, 1, 0)
        before_p = model.probability(0, 0)
        steps = 0
        while model.probability(0, 0) >= .5 and steps < 10000:
            model.update(0, 0, 0)
            steps += 1
        results.append({"previous_identical_labels": exposure, "p_before_inversion": before_p,
                        "inverted_labels_to_p_below_half": steps,
                        "p_after": model.probability(0, 0),
                        "effective_rate_before": .03 / math.sqrt(1 + exposure / 100)})
    assert results[1]["inverted_labels_to_p_below_half"] > results[0]["inverted_labels_to_p_below_half"]
    return {"direct_neuron_updates_without_structure_reset": True, "conditions": results}


def geometric_control():
    model = SpherePredictor()
    q, y = unit([.4, .7, .6]), 1
    tangent = [q[1], -q[0], 0.0]
    h = 1e-6

    def loss(at):
        model.points[0][0] = at
        p = model.probability(0, 0)
        return -math.log(p if y else 1 - p)

    numeric = (loss(exp_map(q, [h * v for v in tangent])) -
               loss(exp_map(q, [-h * v for v in tangent]))) / (2 * h)
    model.points[0][0] = q
    p = model.probability(0, 0)
    a, b = (log_map(q, c) for c in model.anchors)
    gradient = [2 * (p - y) * (v - u) / model.temperature for u, v in zip(a, b)]
    analytic = dot(gradient, tangent)
    assert abs(numeric - analytic) < 1e-6
    before = loss(q)
    model.update(0, y, 0)
    after = loss(model.points[0][0])
    assert after < before
    return {"finite_difference_derivative": numeric, "analytic_derivative": analytic,
            "absolute_error": abs(numeric - analytic), "single_update_decreases_nll": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    paths = sorted([*Path("first_piece").glob("*.py"), *Path("first_piece/tests").glob("*.py"),
                    *Path("setharkk").glob("*.py")])
    source_hashes = {p.as_posix(): hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest() for p in paths}
    changed = subprocess.run(["git", "diff", "--name-only", REVIEWED_SOURCE, "--",
                              "first_piece", "setharkk"], check=True, capture_output=True,
                             text=True).stdout.strip()
    assert not changed, "Diagnostic must run against unchanged reviewed engine"
    report = {"protocol": 1, "reviewed_source": REVIEWED_SOURCE,
              "diagnostic_commit": os.environ.get("GITHUB_SHA"),
              "python": platform.python_version(), "platform": platform.system(),
              "engine_files_unchanged_from_reviewed_source": True, "source_sha256": source_hashes,
              "source_hash_policy": "UTF-8 text with universal newline normalization",
              "policy_evaluation_input_seed": "71000000 + fixture seed; not training RNG",
              "meaning": "Reproductions of known defects and limits, not a correction or novelty benchmark",
              "cases": {}}
    scenarios = (single_context, disappearing_scope, shared_ablation, temporal_ablation,
                 accepted_antipode, inconsistent_restore, oversized_seed, exhausted_budget,
                 aging, geometric_control)
    failures = []
    start = time.perf_counter()
    for fn in scenarios:
        try:
            case = fn()
            case["reproduced_or_positive_control_passed"] = True
        except Exception as exc:
            case = {"reproduced_or_positive_control_passed": False,
                    "exception": type(exc).__name__, "message": str(exc)}
            import traceback
            case["traceback"] = traceback.format_exc()
            failures.append(fn.__name__)
        report["cases"][fn.__name__] = case
        print("REVIEW_PROGRESS=" + json.dumps({"case": fn.__name__, "result": case}), flush=True)
    report["elapsed_seconds"] = time.perf_counter() - start
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("FULL_REVIEW_JSON=" + json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    if failures:
        raise SystemExit("Review reproduction/positive-control failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
