import copy
import json
import random
import unittest

from first_piece.adapter import FirstPieceAdapter
from first_piece.integration_probe import wire_event, agent_proposal, observed_receipt
from first_piece.temporal import TemporalLearner, advance, feature_route, PAIRS
from first_piece.temporal_adapter import TemporalAdapter
from first_piece.temporal_run import episode, evaluate, bounds, resume_probe
from first_piece.temporal_world import TemporalWorld


def train(learner, world, n, rng=None):
    rng = random.Random(8101) if rng is None else rng
    for _ in range(n):
        episode(world, [learner], rng.randrange(2))
    return learner


class TemporalMemoryTests(unittest.TestCase):
    def test_equal_presence_different_order_and_repetitions_do_not_overwrite_first(self):
        states = []
        for events in ([0, 1, 0, 1], [1, 0, 1, 0]):
            mask, before = 0, 0
            for token in events:
                mask, before = advance(mask, before, token)
            states.append((mask, before))
        self.assertEqual(states[0][0], states[1][0])
        self.assertNotEqual(states[0][1], states[1][1])
        feature = 10 + PAIRS.index((0, 1))
        self.assertEqual(feature_route(*states[0], feature), 1)
        self.assertEqual(feature_route(*states[1], feature), 0)

    def test_world_never_announces_relation_or_change_and_presences_are_constant(self):
        world = TemporalWorld(51)
        for pair in ((0, 1), (2, 3)):
            world.change(pair=pair)
            for _ in range(16):
                tokens = []
                while True:
                    event = world.next_event()
                    self.assertEqual(set(event), {"kind", "task", "token"} if event["kind"] == "token"
                                     else {"kind", "task", "surface"})
                    self.assertEqual(event["task"], 0)
                    if event["kind"] == "surface":
                        break
                    tokens.append(event["token"])
                self.assertTrue(all(tokens.count(t) == 1 for t in range(4)))
                world.act(0)

    def test_invalid_events_and_feedback_do_not_mutate_memory(self):
        learner = TemporalLearner()
        before = learner.checkpoint()
        for event in ({"kind": "token", "task": 0, "token": True},
                      {"kind": "token", "task": 0, "token": 10},
                      {"kind": "surface", "task": 0, "surface": "sealed"}):
            with self.assertRaises((ValueError, RuntimeError)):
                learner.receive(event)
            self.assertEqual(learner.checkpoint(), before)
        learner.receive({"kind": "token", "task": 0, "token": 0})
        learner.receive({"kind": "surface", "task": 0, "surface": "sealed"})
        before = learner.checkpoint()
        for action, outcome in ((True, 1), (0, -1), (0, True)):
            with self.assertRaises(ValueError):
                learner.learn(action, outcome)
            self.assertEqual(learner.checkpoint(), before)


class TemporalLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trained = train(TemporalLearner(105), TemporalWorld(72), 6000)

    def test_learns_order_and_transfers_against_equal_budget_readout(self):
        result = evaluate(self.trained, seed=381, phase="transfer", n=512)
        self.assertGreaterEqual(result["models"]["full"]["policy_success"], .95)
        self.assertLessEqual(result["models"]["without_order"]["policy_success"], .65)
        self.assertLessEqual(result["models"]["order_erased"]["policy_success"], .65)
        self.assertEqual(self.trained.metrics()["tasks"]["0"]["feature"],
                         {"kind": "first_before", "first": 0, "second": 1})
        state = self.trained.tasks[0]
        self.assertEqual(sum(map(sum, state["active"].counts)), sum(map(sum, state["baseline"].counts)))

    def test_hidden_relation_replacement_uses_same_task_and_does_not_overflow_budget(self):
        learner = TemporalLearner.restore(self.trained.checkpoint())
        world = TemporalWorld(910, pair=(2, 3))
        train(learner, world, 6000)
        self.assertEqual(set(learner.tasks), {0})
        self.assertEqual(learner.metrics()["tasks"]["0"]["feature"],
                         {"kind": "first_before", "first": 2, "second": 3})
        self.assertGreaterEqual(learner.tasks[0]["replacements"], 1)
        scores = evaluate(learner, seed=1001, pair=(2, 3), n=256)["models"]
        self.assertGreaterEqual(scores["full"]["policy_success"], .95)
        bounds(learner)

    def test_hidden_inversion_relearns_without_new_context(self):
        learner = TemporalLearner.restore(self.trained.checkpoint())
        train(learner, TemporalWorld(71, rule=1), 6000)
        self.assertEqual(set(learner.tasks), {0})
        scores = evaluate(learner, seed=1021, rule=1, n=256)["models"]
        self.assertGreaterEqual(scores["full"]["policy_success"], .95)

    def test_new_attempt_after_unhelpful_data_can_later_learn(self):
        learner = TemporalLearner(91)
        train(learner, TemporalWorld(78, mode="noise"), 1200)
        self.assertGreaterEqual(learner.tasks[0]["attempts"], 2)
        self.assertIsNone(learner.tasks[0]["feature"])
        train(learner, TemporalWorld(71), 6000)
        self.assertIsNotNone(learner.tasks[0]["feature"])
        self.assertGreaterEqual(evaluate(learner, seed=1821, n=256)["models"]["full"]["policy_success"], .95)

    def test_live_and_trial_predictors_are_frozen_during_validation(self):
        learner, world = TemporalLearner(12), TemporalWorld(7)
        train(learner, world, 256)
        self.assertEqual(learner.tasks[0]["status"], "validating")
        before = {k: learner.tasks[0][k].checkpoint() for k in ("active", "baseline", "candidate", "control")}
        train(learner, world, 64)
        self.assertEqual(before, {k: learner.tasks[0][k].checkpoint() for k in before})

    def test_attempt_budget_exhaustion_keeps_learning_but_stops_new_trials(self):
        learner = TemporalLearner(90, max_attempts=2)
        train(learner, TemporalWorld(83, mode="noise"), 10000)
        state = learner.tasks[0]
        self.assertEqual(state["attempts"], 2)
        self.assertEqual(state["status"], "exhausted")
        self.assertIsNone(state["candidate"])
        updates = state["neural_updates"]
        train(learner, TemporalWorld(92, mode="noise"), 128)
        self.assertEqual(state["attempts"], 2)
        self.assertGreater(state["neural_updates"], updates)
        bounds(learner)

    def test_structure_budget_blocks_admission(self):
        learner = TemporalLearner(80, max_units=2, max_attempts=2)
        train(learner, TemporalWorld(83), 10000)
        self.assertIsNone(learner.tasks[0]["feature"])
        self.assertIn("blocked_by_budget", [d["decision"] for d in learner.tasks[0]["decisions"]])

    def test_other_context_neural_state_survives_replacement(self):
        learner = TemporalLearner.restore(self.trained.checkpoint())
        train(learner, TemporalWorld(919, rule=1, task=1), 2000)
        retained = copy.deepcopy(learner.checkpoint()["tasks"][1])
        train(learner, TemporalWorld(911, pair=(2, 3)), 6000)
        self.assertEqual(learner.checkpoint()["tasks"][1], retained)
        self.assertGreaterEqual(evaluate(learner, seed=9001, rule=1, task=1, n=256)["models"]["full"]["policy_success"], .95)

    def test_no_unnecessary_order_in_action_only_fixture(self):
        learner = train(TemporalLearner(104), TemporalWorld(83, mode="action_only"), 4000)
        self.assertIsNone(learner.tasks[0]["feature"])
        self.assertGreaterEqual(evaluate(learner, seed=183, mode="action_only", n=256)["models"]["full"]["policy_success"], .95)


class TemporalResumeTests(unittest.TestCase):
    def test_json_resume_includes_pending_order_frozen_trial_and_rng(self):
        self.assertTrue(resume_probe()["exact_json_resume"])

    def test_corrupt_order_trial_and_configuration_rejected(self):
        learner, world = TemporalLearner(), TemporalWorld()
        train(learner, world, 300)
        snapshot = learner.checkpoint()
        cases = []
        bad = copy.deepcopy(snapshot)
        bad["tasks"][0]["trial"]["candidate"][0] = float("nan")
        cases.append(bad)
        bad = copy.deepcopy(snapshot)
        bad["tasks"][0]["trial"]["started_at"] += 1
        cases.append(bad)
        bad = copy.deepcopy(snapshot)
        bad["tasks"][0]["attempts"] = 1000
        cases.append(bad)
        bad = copy.deepcopy(snapshot)
        bad["config"]["unexpected"] = True
        cases.append(bad)
        for bad in cases:
            with self.assertRaises(ValueError):
                TemporalLearner.restore(bad)
        self.assertEqual(snapshot, learner.checkpoint())
        learner.receive({"kind": "token", "token": 0, "task": 0})
        impossible = learner.checkpoint()
        impossible["episode"]["before"] = 1
        with self.assertRaises(ValueError):
            TemporalLearner.restore(impossible)

    def test_temporal_adapter_keeps_wire_contract_and_refuses_old_checkpoint(self):
        adapter, world = TemporalAdapter(seed=101), TemporalWorld(83)
        sequence = 0
        for i in range(300):
            while True:
                event = world.next_event()
                prediction = adapter.submit_observation(wire_event(event, sequence, "one:context"))
                sequence += 1
                if prediction is not None:
                    break
            proposal = agent_proposal(prediction, i % 2)
            request = adapter.register_action(proposal, executor_id="lab.executor")
            if i == 299:
                snapshot = json.loads(json.dumps(adapter.checkpoint()))
                resumed = TemporalAdapter.restore(snapshot)
                self.assertEqual(resumed.register_action(proposal, executor_id="lab.executor"), request)
            receipt = observed_receipt(request, world.act(i % 2))
            ack = adapter.submit_receipt(receipt)
            self.assertEqual(adapter.submit_receipt(receipt), ack)
            if i == 299:
                self.assertEqual(resumed.submit_receipt(receipt), ack)
                self.assertEqual(resumed.checkpoint(), adapter.checkpoint())
        self.assertEqual(adapter.metrics()["context_slots"], {"one:context": 0})
        self.assertEqual(adapter.metrics()["model_revision"], 300)
        self.assertEqual(adapter.capabilities()["contract_version"], 1)
        with self.assertRaises(ValueError):
            TemporalAdapter.restore(FirstPieceAdapter().checkpoint())
        with self.assertRaises(ValueError):
            FirstPieceAdapter.restore(adapter.checkpoint())


if __name__ == "__main__":
    unittest.main()
