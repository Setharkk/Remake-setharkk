"""Reproducible shared-model scale experiment; standard library only."""
import argparse
import copy
import json
import math
from pathlib import Path
import random
import time

from .shared import SharedLearner
from .shared_adapter import SharedAdapter
from .scale_world import ScaleWorld
from .integration_probe import agent_proposal, observed_receipt

SCALES = {"small": (8, 2, 2), "medium": (32, 8, 4), "large": (64, 16, 4)}
HORIZONS = (100, 1000, 10000)


def observe(learner, events):
    for event in events:
        p = learner.receive(event)
    return p


def evaluation(learner, template, *, seed, changed, n=512, slots=None):
    model = SharedLearner.restore(learner.checkpoint())
    world = copy.deepcopy(template)
    world.rng = random.Random(seed)
    slots = list(range(world.n_contexts)) if slots is None else list(slots)
    values = {group: {name: {"episodes": 0, "correct": 0, "brier_sum": 0.0}
                      for name in ("full", "matched_control", "order_erased")}
              for group in ("context_zero", "other_contexts", "new_context")}
    before = (model.active.checkpoint(), model.baseline.checkpoint(), model.steps, model.neural_updates)
    for i in range(n):
        slot = slots[i % len(slots)]
        events, target = world.episode(slot, changed=changed)
        full = observe(model, events)
        e = model.episode
        control = [model.baseline.probability(a, e["coin"]) for a in range(world.n_actions)]
        erased_route = model._route(model.program, slot, e["mask"], 0) if model.program else e["coin"]
        erased = [model.active.probability(a, erased_route) for a in range(world.n_actions)]
        group = "new_context" if slot == world.n_contexts else ("context_zero" if slot == 0 else "other_contexts")
        for name, p in (("full", full), ("matched_control", control), ("order_erased", erased)):
            record = values[group][name]
            record["episodes"] += 1
            record["correct"] += max(range(len(p)), key=p.__getitem__) == target
            record["brier_sum"] += math.fsum((v - int(a == target)) ** 2 for a, v in enumerate(p)) / len(p)
        model.finish_evaluation()
    if before != (model.active.checkpoint(), model.baseline.checkpoint(), model.steps, model.neural_updates):
        raise AssertionError("Evaluation changed trainable state")
    result = {}
    for group, models in values.items():
        if not models["full"]["episodes"]:
            continue
        result[group] = {}
        for name, v in models.items():
            result[group][name] = {"episodes": v["episodes"], "policy_success": v["correct"] / v["episodes"],
                                   "brier": v["brier_sum"] / v["episodes"]}
    return result


def check_bounds(model):
    metrics = model.metrics()
    n_actions = model.config["n_actions"]
    assert metrics["intrinsic_live_dof"] == 2 * 2 ** model.config["max_features"] * n_actions * 2
    assert metrics["fit_records"] <= len(model.tasks) * model.config["fit_per_context"]
    assert metrics["allocated_points_including_trial"] <= 4 * 2 ** model.config["max_features"] * n_actions
    assert len(model.program) <= model.config["max_features"]
    assert model.attempts <= model.config["max_attempts"]
    assert sum(map(sum, model.active.counts)) == sum(map(sum, model.baseline.counts))
    assert metrics["max_sphere_residual"] <= 1e-10


def adapter_probe(source, world, *, n=64):
    # Measure actual transactional bridge separately from the direct-core loop.
    seed = source.config["seed"]
    actions = tuple(f"lab.action.{i}" for i in range(world.n_actions))
    options = {k: v for k, v in source.config.items() if k not in ("seed", "n_actions")}
    adapter = SharedAdapter(seed=seed, actions=actions, learner_options=options)
    adapter._learner = SharedLearner.restore(source.checkpoint())
    adapter._revision = source.steps
    adapter._slots = {f"ctx:{slot}": slot for slot in sorted(source.tasks)}
    # A fresh wire stream can start from a cortex with historical exposure.
    direct = SharedLearner.restore(source.checkpoint())
    inputs = copy.deepcopy(world)
    inputs.rng = random.Random(77100 + seed)
    actions_rng = random.Random(82100 + seed)
    sequence = 0
    elapsed = 0.0
    for i in range(n):
        slot = i % world.n_contexts
        events, target = inputs.episode(slot, changed=True)
        action = actions_rng.randrange(world.n_actions)
        direct_p = observe(direct, events)
        start = time.perf_counter()
        for event in events:
            end = event["kind"] == "surface"
            prediction = adapter.submit_observation({
                "schema_version": 1, "event_id": f"adapter:{sequence}", "stream_id": "scale:probe",
                "sequence": sequence, "context_id": f"ctx:{slot}", "source_id": "scale:sensor",
                "kind": "stream.end" if end else "stream.symbol",
                "payload": {"value": "sealed" if end else event["token"]}})
            sequence += 1
        for p, forecast in zip(direct_p, prediction["forecasts"]):
            if abs(p - forecast["distribution"]["parameters"]["p"]) > 1e-10:
                raise AssertionError("Wire and direct predictions differ")
        request = adapter.register_action(agent_proposal(prediction, action), executor_id="scale:executor")
        receipt = observed_receipt(request, int(action == target))
        adapter.submit_receipt(receipt)
        elapsed += time.perf_counter() - start
        direct.learn(action, int(action == target))
    one, two = direct.checkpoint(), adapter.checkpoint()["learner"]
    for state in (one, two):
        for search in state["searches"]:
            search.pop("elapsed_seconds")
    if one != two:
        raise AssertionError("Wire and direct predictive state differ")
    snapshot = json.loads(json.dumps(adapter.checkpoint()))
    resumed = SharedAdapter.restore(snapshot)
    if resumed.checkpoint() != snapshot:
        raise AssertionError("Adapter checkpoint failed after scale probe")
    return {"episodes": n, "wire_events": sequence, "elapsed_seconds": elapsed,
            "milliseconds_per_episode": elapsed * 1000 / n,
            "direct_and_wire_predictive_state_identical": True,
            "json_resume": True, "snapshot_bytes": len(json.dumps(snapshot, separators=(",", ":")).encode())}


def run(scale, seed, out, *, per_context=10000, eval_n=512):
    symbols, contexts, actions = SCALES[scale]
    world = ScaleWorld(1300 + seed, n_symbols=symbols, n_contexts=contexts, n_actions=actions)
    model = SharedLearner(7100 + seed, max_symbols=symbols, n_actions=actions,
                          max_tasks=max(contexts + 1, 2))
    policy = random.Random(4100 + seed)
    rows = []
    train_seconds = 0.0
    pre_snapshot = None
    for changed in (False, True):
        milestones = [h for h in HORIZONS if h <= per_context]
        if per_context not in milestones:
            milestones.append(per_context)
        previous = 0
        for horizon in milestones:
            start = time.perf_counter()
            for i in range(previous * contexts, horizon * contexts):
                events, target = world.episode(i % contexts, changed=changed)
                observe(model, events)
                action = policy.randrange(actions)
                model.learn(action, int(action == target))
            train_seconds += time.perf_counter() - start
            check_bounds(model)
            # Dedicated sample of changed context, and balanced other contexts.
            zero = evaluation(model, world, seed=500000 + seed * 1000 + horizon + int(changed) * 100000,
                              changed=changed, n=eval_n, slots=[0])
            others = evaluation(model, world, seed=600000 + seed * 1000 + horizon + int(changed) * 100000,
                                changed=changed, n=eval_n, slots=range(1, contexts))
            rows.append({"phase": "after_change" if changed else "before_change",
                         "interactions_per_context": horizon, "global_training_interactions": model.steps,
                         "scores": {**zero, **others}, "metrics": model.metrics()})
            previous = horizon
        if not changed:
            pre_snapshot = model.checkpoint()
            Path(out, f"{scale}-{seed}-before.json").write_text(json.dumps(pre_snapshot, separators=(",", ":")), encoding="utf-8")
    final = model.checkpoint()
    Path(out, f"{scale}-{seed}-after.json").write_text(json.dumps(final, separators=(",", ":")), encoding="utf-8")
    transfer = evaluation(SharedLearner.restore(pre_snapshot), world, seed=10000000 + seed,
                          changed=False, n=eval_n, slots=[contexts])
    report = {"scale": scale, "seed": seed, "symbols": symbols, "contexts": contexts, "actions": actions,
              "interactions_per_context_per_phase": per_context, "training_interactions": model.steps,
              "training_seconds": train_seconds, "checkpoint_bytes": len(json.dumps(final, separators=(",", ":")).encode()),
              "evaluations": rows, "new_context_before_change": transfer,
              "final_metrics": model.metrics(), "adapter_probe": adapter_probe(model, world)}
    return report


def final_probe(out, *, eval_n=1024, seeds=(0, 1, 2), scales=tuple(SCALES)):
    reports = []
    for scale in scales:
        symbols, contexts, actions = SCALES[scale]
        for seed in seeds:
            world = ScaleWorld(1300 + seed, n_symbols=symbols, n_contexts=contexts, n_actions=actions)
            for phase in ("before", "after"):
                model = SharedLearner.restore(json.loads(Path(out, f"{scale}-{seed}-{phase}.json").read_text(encoding="utf-8")))
                before = model.checkpoint()
                for group, slots in (("context_zero", [0]), ("other_contexts", range(1, contexts)), ("new_context", [contexts])):
                    scores = evaluation(model, world, seed=30000000 + seed * 10000 + (0 if phase == "before" else 1000) + len(reports),
                                        changed=phase == "after", n=eval_n, slots=slots)
                    reports.append({"scale": scale, "seed": seed, "phase": phase, "group": group, "scores": scores})
                assert model.checkpoint() == before
    result = {"evaluation_only": True, "training_updates": 0, "eval_episodes_per_group": eval_n, "reports": reports}
    Path(out, "final.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    print("SCALE_FINAL_JSON=" + json.dumps(result, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--scales", nargs="+", choices=list(SCALES), default=list(SCALES))
    parser.add_argument("--per-context", type=int, default=10000)
    parser.add_argument("--eval-n", type=int, default=512)
    parser.add_argument("--final-only", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.final_only:
        final_probe(out, eval_n=args.eval_n, seeds=args.seeds, scales=args.scales)
        return
    reports = []
    for scale in args.scales:
        for seed in args.seeds:
            report = run(scale, seed, out, per_context=args.per_context, eval_n=args.eval_n)
            reports.append(report)
            out.joinpath(f"{scale}-{seed}-report.json").write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            print("SCALE_REPORT_JSON=" + json.dumps(report, sort_keys=True), flush=True)
    aggregate = {"reports": reports, "total_training_interactions": sum(r["training_interactions"] for r in reports),
                 "total_neural_updates": sum(r["final_metrics"]["neural_updates"] for r in reports)}
    out.joinpath("aggregate.json").write_text(json.dumps(aggregate, sort_keys=True), encoding="utf-8")
    print("SCALE_TOTAL_JSON=" + json.dumps({k: v for k, v in aggregate.items() if k != "reports"}), flush=True)


if __name__ == "__main__":
    main()
