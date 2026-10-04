"""Behavioral and accounting tests for the scaling experiment."""
import copy
import json
import random
import unittest

from setharkk.contracts import json_value
from first_piece.shared import SharedLearner, SharedSpherePredictor, pair_index, LOSS_WINDOW
from first_piece.scale_world import ScaleWorld
from first_piece.shared_adapter import SharedAdapter
from first_piece.adapter import FirstPieceAdapter
from first_piece.integration_probe import agent_proposal, observed_receipt


def episode(learner, world, slot=0, *, changed=False, rng=None):
    events, target = world.episode(slot, changed=changed)
    probabilities = None
    for event in events:
        probabilities = learner.receive(event)
    action = (rng or world.rng).randrange(world.n_actions)
    learner.learn(action, int(action == target))
    return probabilities


def train(learner, world, n):
    actions = random.Random(801)
    for i in range(n):
        episode(learner, world, i % world.n_contexts, rng=actions)
    return learner


def evaluate(learner, world, n=256, slot=0, changed=False):
    correct = 0
    for _ in range(n):
        events, target = world.episode(slot, changed=changed)
        for event in events:
            p = learner.receive(event)
        correct += max(range(len(p)), key=p.__getitem__) == target
        learner.finish_evaluation()
    return correct / n


def wire_symbol(sequence, value, context="context:zero", *, end=False):
    return {"schema_version": 1, "event_id": f"event:{sequence}", "stream_id": "stream:one",
            "sequence": sequence, "context_id": context, "source_id": "sensor",
            "kind": "stream.end" if end else "stream.symbol", "payload": {"value": value}}


class SharedMemoryTests(unittest.TestCase):
    def test_dynamic_vocabulary_first_order_and_repetitions(self):
        learner = SharedLearner()
        for token in ("alpha", "beta", "alpha"):
            learner.receive({"kind": "token", "token": token, "task": 0})
        self.assertEqual(learner.symbols, ["alpha", "beta"])
        self.assertEqual(learner.episode["mask"], 3)
        self.assertEqual(learner.episode["before"], 1 << pair_index(0, 1, 64))
        self.assertEqual(learner.episode["events"], 3)

    def test_large_bit_masks_are_canonical_json_strings_and_resume_exactly(self):
        learner = SharedLearner(max_symbols=64)
        for i in range(64):
            learner.receive({"kind": "token", "token": f"opaque:{i}", "task": 0})
        snapshot = learner.checkpoint()
        json_value(snapshot)
        self.assertIsInstance(snapshot["episode"]["before"], str)
        self.assertGreater(int(snapshot["episode"]["before"], 16), 2 ** 53)
        restored = SharedLearner.restore(json.loads(json.dumps(snapshot)))
        self.assertEqual(restored.checkpoint(), snapshot)
        for model in (learner, restored):
            model.receive({"kind": "surface", "surface": "sealed", "task": 0})
            model.learn(3, 1)
        self.assertEqual(restored.checkpoint(), learner.checkpoint())

    def test_invalid_event_feedback_and_vocabulary_budget_are_transactional(self):
        learner = SharedLearner(max_symbols=4)
        before = learner.checkpoint()
        for event in ({"kind": "token", "token": True, "task": 0},
                      {"kind": "token", "token": "ok", "task": True},
                      {"kind": "surface", "surface": "sealed", "task": 0}):
            with self.assertRaises((ValueError, RuntimeError)):
                learner.receive(event)
            self.assertEqual(learner.checkpoint(), before)
        for token in ("a", "b", "c", "d"):
            learner.receive({"kind": "token", "token": token, "task": 0})
        before = learner.checkpoint()
        with self.assertRaises(ValueError):
            learner.receive({"kind": "token", "token": "e", "task": 0})
        self.assertEqual(learner.checkpoint(), before)
        learner.receive({"kind": "surface", "surface": "sealed", "task": 0})
        before = learner.checkpoint()
        for action, y in ((4, 1), (0, True), (True, 0)):
            with self.assertRaises(ValueError):
                learner.learn(action, y)
            self.assertEqual(learner.checkpoint(), before)

    def test_checkpoint_rejects_impossible_order_geometry_shape_and_counters(self):
        learner = SharedLearner()
        for token in ("a", "b", "c"):
            learner.receive({"kind": "token", "token": token, "task": 0})
        state = learner.checkpoint()
        bad = copy.deepcopy(state)
        # a<b, b<c, c<a is a nontransitive tournament.
        bad["episode"]["before"] = format((1 << pair_index(0, 1, 64)) | (1 << pair_index(1, 2, 64)), "x")
        with self.assertRaises(ValueError):
            SharedLearner.restore(bad)
        for mutate in (lambda s: s["active"]["points"][0].pop(),
                       lambda s: s["active"]["points"][0].__setitem__(0, [2, 0, 0]),
                       lambda s: s.__setitem__("steps", 1),
                       lambda s: s["episode"].__setitem__("mask", "03")):
            bad = copy.deepcopy(state)
            mutate(bad)
            with self.assertRaises(ValueError):
                SharedLearner.restore(bad)

    def test_more_contexts_do_not_allocate_private_neural_weights(self):
        learner = SharedLearner()
        initial = learner.metrics()["intrinsic_live_dof"]
        for slot in range(32):
            learner.receive({"kind": "token", "token": "same", "task": slot})
            learner.receive({"kind": "surface", "surface": "sealed", "task": slot})
            learner.finish_evaluation()
        self.assertEqual(learner.metrics()["intrinsic_live_dof"], initial)
        self.assertTrue(all(set(t) == {"steps", "records", "losses"} for t in learner.tasks.values()))
        self.assertEqual(initial, 128)

    def test_supported_shapes_use_geodesic_updates(self):
        for actions in (2, 4, 16):
            model = SharedSpherePredictor(n_actions=actions)
            old = model.probability(actions - 1, 7)
            for _ in range(32):
                result = model.update(actions - 1, 1, 7)
                self.assertLess(result["sphere_residual"], 1e-10)
                self.assertLess(result["tangent_residual"], 1e-10)
            self.assertGreater(model.probability(actions - 1, 7), old)
            self.assertEqual(SharedSpherePredictor.restore(model.checkpoint()).checkpoint(), model.checkpoint())


class SharedLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trained = train(SharedLearner(7, max_symbols=32), ScaleWorld(37, n_symbols=32, n_contexts=4), 24000)

    def test_combines_relations_and_transfers_without_private_context_weights(self):
        learner = SharedLearner.restore(self.trained.checkpoint())
        world = ScaleWorld(37, n_symbols=32, n_contexts=4)
        world.rng = random.Random(510001)
        self.assertGreaterEqual(len(learner.program), 2)
        before = learner.active.checkpoint()
        self.assertGreaterEqual(evaluate(learner, world, slot=4), .95)
        self.assertEqual(learner.active.checkpoint(), before)
        self.assertNotIn("active", learner.tasks[4])

    def test_validation_banks_freeze_while_live_banks_continue_learning(self):
        learner, world = SharedLearner(5, max_tasks=4), ScaleWorld(1, n_contexts=4)
        train(learner, world, 512)
        self.assertIsNotNone(learner.trial)
        before = {name: getattr(learner, name).checkpoint() for name in ("active", "baseline", "candidate", "control")}
        train(learner, world, 32)
        for name in ("candidate", "control"):
            self.assertEqual(getattr(learner, name).checkpoint(), before[name])
        self.assertNotEqual(learner.active.checkpoint(), before["active"])
        self.assertEqual(learner.trial["n"], 32)

    def test_trial_resume_exactly_reproduces_future_admission(self):
        learner, world = SharedLearner(17, max_tasks=4), ScaleWorld(72, n_contexts=4)
        train(learner, world, 512)
        resumed = SharedLearner.restore(json.loads(json.dumps(learner.checkpoint())))
        events_rng = random.Random(581)
        for i in range(1200):
            events, target = world.episode(i % 4)
            action = events_rng.randrange(4)
            for model in (learner, resumed):
                for event in events:
                    model.receive(event)
                model.learn(action, int(action == target))
        # Wall time is diagnostic only, not part of predictive state.
        one, two = learner.checkpoint(), resumed.checkpoint()
        for s in (one, two):
            for search in s["searches"]:
                search.pop("elapsed_seconds")
        self.assertEqual(one, two)

    def test_transaction_copy_isolates_core_operations_through_admission(self):
        source, world = SharedLearner(17, max_tasks=4), ScaleWorld(72, n_symbols=32, n_contexts=4)
        train(source, world, 512)
        self.assertIsNotNone(source.trial)
        before = source.checkpoint()
        child = source._transaction_copy()
        train(child, world, 5000)
        self.assertGreaterEqual(child.admissions, 1)
        self.assertEqual(source.checkpoint(), before)
        child.receive({"kind": "token", "task": 0, "token": "new:opaque"})
        self.assertNotIn("new:opaque", source.symbols)
        self.assertEqual(source.checkpoint(), before)

    def test_memory_neural_updates_and_attempts_are_bounded(self):
        learner = self.trained
        metrics = learner.metrics()
        self.assertLessEqual(metrics["fit_records"], 4 * learner.config["fit_per_context"])
        self.assertLessEqual(learner.attempts, learner.config["max_attempts"])
        self.assertLessEqual(len(learner.decisions), learner.config["max_attempts"] * 3)
        self.assertEqual(sum(map(sum, learner.active.counts)), sum(map(sum, learner.baseline.counts)))
        self.assertLessEqual(metrics["allocated_points_including_trial"], 128)
        self.assertEqual(metrics["intrinsic_peak_dof"], 256)

    def test_scoped_horizons_are_examined_once_despite_complement_returns(self):
        learner, world = SharedLearner(7, max_tasks=4), ScaleWorld(1, n_contexts=4)
        train(learner, world, 512)
        learner.trial["scope"] = 0
        # The data are deliberately unhelpful to the improvement comparison,
        # but 127 principal observations have not reached a declared look.
        for _ in range(127):
            episode(learner, world, 0)
        self.assertEqual(learner.trial["n"], 127)
        episode(learner, world, 0)
        count = len(learner.decisions)
        for _ in range(8):
            episode(learner, world, 1)
        self.assertEqual(len(learner.decisions), count)

    def test_single_observed_context_drift_does_not_wait_for_nonexistent_complement(self):
        learner = train(SharedLearner(91, max_tasks=2, min_records=256,
                                      max_symbols=8, n_actions=2),
                        ScaleWorld(31, n_symbols=8, n_contexts=1, n_actions=2), 6000)
        self.assertTrue(learner.program)
        world = ScaleWorld(31, n_symbols=8, n_contexts=1, n_actions=2)
        for _ in range(16):
            episode(learner, world, 0, changed=True)
        self.assertIsNotNone(learner.trial)
        self.assertIsNone(learner.trial["scope"])
        self.assertEqual(learner.trial["other_n"], 0)

    def test_extends_an_admitted_xor_when_context_drift_erases_pair_gain(self):
        # Three-way parity has no marginal gain in any pair. Preserve and
        # extend the already admitted pair instead of relying on label luck.
        learner = SharedLearner(max_symbols=4, max_tasks=2, min_records=256)
        learner.symbols = ["a", "b", "c", "d"]
        learner._symbol_ids = {s: i for i, s in enumerate(learner.symbols)}
        learner.tasks = {slot: {"steps": 0, "records": [], "losses": []} for slot in (0, 1)}
        fa = 4 + pair_index(0, 1, 4)
        fb = 4 + pair_index(2, 3, 4)
        learner.program = [fa, fb]
        rows = []
        for slot in (0, 1):
            for a in (0, 1):
                for b in (0, 1):
                    before = (a << pair_index(0, 1, 4)) | (b << pair_index(2, 3, 4))
                    for action in range(4):
                        target = (a ^ b ^ slot)
                        rows.extend([(slot, 15, before, 0, action, int(action == target))] * 32)
        selected = learner._search(rows)
        self.assertIn(fa, selected)
        self.assertIn(fb, selected)
        self.assertTrue(any(f >= learner.context_offset for f in selected))

    def test_xor_is_found_without_a_handwritten_xor_predicate(self):
        learner = train(SharedLearner(91, max_tasks=2, n_actions=2), ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
        world = ScaleWorld(31, n_contexts=2, n_actions=2)
        world.rng = random.Random(775100)
        self.assertGreaterEqual(evaluate(learner, world), .95)
        self.assertEqual(len(learner.program), 2)


class SharedAdapterTests(unittest.TestCase):
    def test_four_action_pending_request_resume_and_receipt_learns_once(self):
        adapter = SharedAdapter()
        adapter.submit_observation(wire_symbol(0, "opaque:one"))
        prediction = adapter.submit_observation(wire_symbol(1, "sealed", end=True))
        self.assertEqual(len(prediction["forecasts"]), 4)
        request = adapter.register_action(agent_proposal(prediction, 3), executor_id="executor")
        state = json.loads(json.dumps(adapter.checkpoint()))
        json_value(state)
        resumed = SharedAdapter.restore(state)
        self.assertEqual(resumed.checkpoint(), adapter.checkpoint())
        receipt = observed_receipt(request, 1)
        ack = resumed.submit_receipt(receipt)
        self.assertEqual(ack["model_revision"], 1)
        before = resumed.checkpoint()
        self.assertEqual(resumed.submit_receipt(receipt), ack)
        self.assertEqual(resumed.checkpoint(), before)

    def test_shape_old_snapshot_and_stale_proposal_rejected(self):
        with self.assertRaises(ValueError):
            SharedAdapter(actions=("a", "b", "c", "d"), learner_options={"n_actions": 2})
        with self.assertRaises(ValueError):
            SharedAdapter.restore(FirstPieceAdapter().checkpoint())
        adapter = SharedAdapter()
        adapter.submit_observation(wire_symbol(0, "x"))
        prediction = adapter.submit_observation(wire_symbol(1, "sealed", end=True))
        proposal = agent_proposal(prediction, 2)
        proposal["model_revision"] += 1
        before = adapter.checkpoint()
        with self.assertRaises(ValueError):
            adapter.register_action(proposal, executor_id="executor")
        self.assertEqual(adapter.checkpoint(), before)

    def test_pending_trial_transaction_copy_refusals_and_snapshots_are_detached(self):
        adapter = SharedAdapter(learner_options={"max_tasks": 4})
        core, world = SharedLearner(5, max_tasks=4), ScaleWorld(1, n_contexts=4)
        train(core, world, 512)
        adapter._learner = core
        adapter._revision = core.steps
        adapter._slots = {f"ctx:{i}": i for i in range(4)}
        events, target = world.episode(0)
        for sequence, event in enumerate(events):
            prediction = adapter.submit_observation(wire_symbol(sequence,
                event["token"] if event["kind"] == "token" else "sealed",
                context="ctx:0", end=event["kind"] == "surface"))
        request = adapter.register_action(agent_proposal(prediction, 3), executor_id="executor")
        before = adapter.checkpoint()
        bad = observed_receipt(request, 1)
        bad["outcome"]["value"] = True
        with self.assertRaises(ValueError):
            adapter.submit_receipt(bad)
        self.assertEqual(before, adapter.checkpoint())
        ack = adapter.submit_receipt(observed_receipt(request, int(target == 3)))
        self.assertEqual(ack["model_revision"], 513)
        snapshot = adapter.checkpoint()
        snapshot["learner"]["tasks"]["0"]["records"][0][0] = "0"
        snapshot["learner"]["candidate"]["points"][0][0] = [2, 0, 0]
        self.assertNotEqual(snapshot, adapter.checkpoint())
        self.assertEqual(SharedAdapter.restore(json.loads(json.dumps(adapter.checkpoint()))).checkpoint(),
                         adapter.checkpoint())

    def test_rejected_new_symbol_context_and_duplicate_event_do_not_change_rng(self):
        adapter = SharedAdapter(learner_options={"max_tasks": 1, "max_symbols": 4, "min_records": 256})
        message = wire_symbol(0, "x")
        adapter.submit_observation(message)
        before = adapter.checkpoint()
        adapter.submit_observation(message)
        self.assertEqual(adapter.checkpoint(), before)
        for message in (wire_symbol(1, "y", context="other"), wire_symbol(1, True)):
            with self.assertRaises((ValueError, RuntimeError)):
                adapter.submit_observation(message)
            self.assertEqual(adapter.checkpoint(), before)


if __name__ == "__main__":
    unittest.main()
