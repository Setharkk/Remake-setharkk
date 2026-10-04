"""Before/after evidence for current defects, including authentic v1 migration."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import types

from first_piece.shared import SharedLearner
from first_piece.shared_adapter import SharedAdapter
from first_piece.temporal import TemporalLearner
from first_piece.temporal_world import TemporalWorld
from first_piece.temporal_run import episode as temporal_episode
from first_piece.scale_world import ScaleWorld
from first_piece.tests.test_shared import wire_symbol, episode, train
from first_piece.integration_probe import agent_proposal, observed_receipt

ENGINE_BEFORE = "0b19465aa6be9aacf291b077cdc69f1b4e44580f"
DIAGNOSTIC_BEFORE = "9f010f673425645c22edacdcd6189761555d49a7"


def source_at(ref, path):
    return subprocess.run(["git", "show", ref + ":" + path], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def legacy_modules():
    name = "_current_fix_before"
    pkg = types.ModuleType(name)
    pkg.__path__ = []
    sys.modules[name] = pkg
    modules = {}
    for short in ("world", "criterion", "spherical", "learner", "temporal",
                  "shared", "adapter", "shared_adapter"):
        module = types.ModuleType(name + "." + short)
        module.__package__ = name
        sys.modules[module.__name__] = module
        exec(compile(source_at(ENGINE_BEFORE, "first_piece/" + short + ".py"),
                     ENGINE_BEFORE + ":" + short, "exec"), module.__dict__)
        modules[short] = module
    return modules


def before_probe(modules):
    module = types.ModuleType("_current_fix_old_diagnostic")
    exec(compile(source_at(DIAGNOSTIC_BEFORE, "validation/first_piece_full_review.py"),
                 DIAGNOSTIC_BEFORE + ":diagnostic", "exec"), module.__dict__)
    module.SharedLearner = modules["shared"].SharedLearner
    module.SharedSpherePredictor = modules["shared"].SharedSpherePredictor
    module.SharedAdapter = modules["shared_adapter"].SharedAdapter
    module.TemporalLearner = modules["temporal"].TemporalLearner
    module.SpherePredictor = modules["spherical"].SpherePredictor
    names = ("single_context", "disappearing_scope", "shared_ablation",
             "temporal_ablation", "accepted_antipode", "inconsistent_restore",
             "oversized_seed")
    return {name: getattr(module, name)() for name in names}


def fresh_policy(core, world, n=512):
    clone = SharedLearner.restore(core.checkpoint())
    world.rng = random.Random(71000000 + world.seed)
    correct = 0
    for _ in range(n):
        events, target = world.episode(0)
        for event in events:
            p = clone.receive(event)
        correct += max(range(len(p)), key=p.__getitem__) == target
        clone.finish_evaluation()
    return correct / n


def rejected_restore(snapshot, cls=SharedLearner):
    try:
        cls.restore(snapshot)
    except ValueError:
        return True
    raise AssertionError("Inconsistent snapshot accepted")


def after_probe():
    one = train(SharedLearner(91), ScaleWorld(31, n_contexts=1), 20000)
    score = fresh_policy(one, ScaleWorld(31, n_contexts=1))
    assert one.admissions and score >= .95
    single = {"training_labels": 20000, "attempts": one.attempts,
              "admissions": one.admissions, "required_fit_records": one.required_fit_records(),
              "configured_fit_target": one.config["min_records"],
              "policy_success": score, "evaluation_episodes": 512}

    core = train(SharedLearner(91, max_tasks=2, n_actions=2),
                 ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
    world = ScaleWorld(31, n_contexts=2, n_actions=2)
    rng = random.Random(951)
    for change in range(1, 4097):
        episode(core, world, 0, changed=True, rng=rng)
        if core.trial is not None:
            break
    assert core.trial is not None and core.trial["scope"] == 0
    attempts = core.attempts
    resumed_at = 3000
    recovered = None
    for index in range(5000):
        events, target = world.episode(1)
        action = rng.randrange(2)
        for model in (core, recovered):
            if model is None:
                continue
            for event in events:
                model.receive(event)
            model.learn(action, int(action == 1 - target))
        if index + 1 == resumed_at:
            recovered = SharedLearner.restore(json.loads(json.dumps(core.checkpoint())))
    expired = [d for d in core.decisions if d["decision"] == "expired"]
    assert len(expired) == 1 and expired[0]["validation_interactions"] == 0
    assert core.attempts == attempts and core.trial is None
    assert core.checkpoint() == recovered.checkpoint()
    stall = {"changed_labels_until_trial": change, "complement_labels": 5000,
             "expired_at_global_step": expired[0]["at"],
             "global_labels_to_expiration": core.config["trial_stall_limit"],
             "attempt_budget_refunded": False, "attempts_before": attempts,
             "attempts_after": core.attempts, "principal_horizon_at_closure": 0,
             "resume_at_complement_label": resumed_at, "resume_state_identical": True,
             "new_statistical_look_on_expiration": False}

    ablated = train(SharedLearner(91, max_tasks=2, n_actions=2, use_structure=False),
                    ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
    world = ScaleWorld(31, n_contexts=2, n_actions=2)
    gaps, losses = [], []
    for i in range(32):
        events, target = world.episode(i % 2)
        for event in events:
            p = ablated.receive(event)
        y = int(i % 2 == target)
        returned = ablated.learn(i % 2, y)
        gaps.append(abs(returned - p[i % 2]))
        losses.append(abs(ablated.tasks[i % 2]["losses"][-1] - (p[i % 2] - y) ** 2))
    assert max(gaps) == 0 and max(losses) == 0
    SharedLearner.restore(ablated.checkpoint())

    temporal, world = TemporalLearner(105, use_structure=False), TemporalWorld(72)
    rng = random.Random(8101)
    for _ in range(6000):
        temporal_episode(world, [temporal], rng.randrange(2))
    temporal_gaps = []
    for i in range(32):
        while True:
            p = temporal.receive(world.next_event())
            if p is not None:
                break
        y = world.act(i % 2)
        temporal.learn(i % 2, y)
        temporal_gaps.append(abs(temporal.tasks[0]["losses"][-1] - (p[i % 2] - y) ** 2))
    assert max(temporal_gaps) == 0

    base = train(SharedLearner(5, max_tasks=4), ScaleWorld(1, n_contexts=4), 512).checkpoint()
    counters = copy.deepcopy(base)
    counters["active"]["counts"][0][0] += 1
    lineage = copy.deepcopy(base)
    lineage["searches"][0] = {"attempt": 999999, "scope": "not-a-slot"}
    adapter = SharedAdapter()
    adapter.submit_observation(wire_symbol(0, "opaque:a"))
    event = adapter.checkpoint()
    event["last_observation"]["payload"]["value"] = "opaque:b"
    inconsistent = {"unequal_live_counts_rejected": rejected_restore(counters),
                    "impossible_search_rejected": rejected_restore(lineage),
                    "unbound_last_symbol_rejected": rejected_restore(event, SharedAdapter),
                    "authentic_roundtrip": SharedLearner.restore(base).checkpoint() == base}
    antipodal = SharedAdapter().checkpoint()
    for row in antipodal["learner"]["active"]["points"]:
        row[0] = [-1, 0, 0]
    singular = {"antipode_rejected_at_restore": rejected_restore(antipodal, SharedAdapter)}
    seed_error = None
    try:
        SharedLearner(2**53 + 1)
    except ValueError as exc:
        seed_error = str(exc)
    assert seed_error is not None
    maximum = SharedLearner(2**53 - 1)
    seed = {"oversized_seed_rejected_at_constructor": True,
            "largest_supported_seed": str(2**53 - 1),
            "largest_supported_seed_roundtrip": SharedLearner.restore(json.loads(json.dumps(maximum.checkpoint()))).checkpoint() == maximum.checkpoint()}
    return {"single_context": single, "disappearing_scope": stall,
            "shared_ablation": {"probability_gap": max(gaps), "brier_gap": max(losses), "comparison_episodes": 32},
            "temporal_ablation": {"brier_gap": max(temporal_gaps), "comparison_episodes": 32},
            "inconsistent_restore": inconsistent, "accepted_antipode": singular,
            "oversized_seed": seed}


def migration_probe(modules):
    old = modules["shared"].SharedLearner
    old_adapter = modules["shared_adapter"].SharedAdapter
    pending = train(old(5, max_tasks=4), ScaleWorld(1, n_contexts=4), 600)
    snapshot = json.loads(json.dumps(pending.checkpoint()))
    assert pending.trial is not None
    assert rejected_restore(snapshot)
    converted = SharedLearner.migrate_checkpoint_v1(snapshot)
    recovered = SharedLearner.restore(converted)
    for name in ("active", "baseline"):
        assert recovered.checkpoint()[name] == snapshot[name]
    for name in ("steps", "attempts", "admissions", "neural_updates", "rng", "symbols"):
        assert recovered.checkpoint()[name] == snapshot[name]
    assert recovered.trial is None and recovered.decisions[-1]["decision"] == "migrated"
    assert converted["format"] == 2

    # A completed legacy trial preserves all admitted weights and counters.
    complete = train(old(91, max_tasks=2, n_actions=2),
                     ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
    assert complete.trial is None and complete.admissions > 0
    complete_copy = SharedLearner.restore(SharedLearner.migrate_checkpoint_v1(complete.checkpoint()))
    assert complete_copy.active.checkpoint() == complete.active.checkpoint()

    # Preserve an actually issued wire request, its prediction and replay cache.
    adapter = old_adapter(seed=5, learner_options={"max_tasks": 4})
    adapter.submit_observation(wire_symbol(0, "a"))
    prediction = adapter.submit_observation(wire_symbol(1, "sealed", end=True))
    request = adapter.register_action(agent_proposal(prediction, 0), executor_id="executor")
    new = SharedAdapter.restore(SharedAdapter.migrate_checkpoint_v1(json.loads(json.dumps(adapter.checkpoint()))))
    assert new.current_prediction() == prediction
    assert new.register_action(agent_proposal(prediction, 0), executor_id="executor") == request
    receipt = observed_receipt(request, 1)
    ack = new.submit_receipt(receipt)
    assert new.submit_receipt(receipt) == ack
    return {"authentic_source": ENGINE_BEFORE, "explicit_migration_required": True,
            "shared_format_after": 2, "unfinished_legacy_trial_closed_without_admission": True,
            "attempts_and_total_updates_preserved": True, "live_weights_and_rng_preserved": True,
            "completed_legacy_admission_preserved": True,
            "pending_wire_request_and_prediction_preserved": True,
            "duplicate_receipt_learns_once": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    modules = legacy_modules()
    report = {"protocol": 1, "before_engine": ENGINE_BEFORE,
              "after_commit": os.environ.get("GITHUB_SHA"), "python": platform.python_version(),
              "platform": platform.system(), "before": before_probe(modules)}
    print("FIX_PROGRESS=before_reproduced", flush=True)
    report["after"] = after_probe()
    print("FIX_PROGRESS=after_verified", flush=True)
    report["migration"] = migration_probe(modules)
    report["elapsed_seconds"] = time.perf_counter() - start
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("CURRENT_FIXES_JSON=" + json.dumps(report, sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
