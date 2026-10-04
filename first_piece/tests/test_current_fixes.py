"""Regression cases for the six current-review defect families."""
import copy
import json
import math
import random
import unittest

from first_piece.shared import SharedLearner
from first_piece.shared_adapter import SharedAdapter
from first_piece.temporal import TemporalLearner
from first_piece.temporal_world import TemporalWorld
from first_piece.temporal_run import episode as temporal_episode
from first_piece.scale_world import ScaleWorld
from first_piece.spherical import SpherePredictor, unit
from first_piece.tests.test_shared import episode, train, evaluate, wire_symbol
from first_piece.integration_probe import agent_proposal, observed_receipt


class CurrentFixes(unittest.TestCase):
    def test_default_single_context_learns_without_lowering_configured_target(self):
        core = train(SharedLearner(91), ScaleWorld(31, n_contexts=1), 10000)
        self.assertEqual(core.config["min_records"], 512)
        self.assertEqual(core.required_fit_records(), 256)
        self.assertGreaterEqual(core.admissions, 1)
        world = ScaleWorld(31, n_contexts=1)
        world.rng = random.Random(71000031)
        self.assertGreaterEqual(evaluate(core, world, n=512), .95)

    def test_single_context_capacity_and_late_unlabelled_context(self):
        core = SharedLearner(max_tasks=1)
        self.assertEqual(core.required_fit_records(), 256)
        core.receive({"kind": "token", "token": "a", "task": 0})
        core.receive({"kind": "surface", "surface": "sealed", "task": 0})
        core.learn(0, 1)
        wider = SharedLearner()
        wider.receive({"kind": "token", "token": "a", "task": 1})
        wider.receive({"kind": "surface", "surface": "sealed", "task": 1})
        wider.finish_evaluation()
        self.assertEqual(wider.required_fit_records(), 256)
        for slot in (0, 1):
            wider.receive({"kind": "token", "token": "a", "task": slot})
            wider.receive({"kind": "surface", "surface": "sealed", "task": slot})
            wider.learn(0, 1)
        self.assertEqual(wider.required_fit_records(), 512)

    def test_briefly_observed_context_cannot_make_fit_target_unreachable(self):
        core, world = SharedLearner(91), ScaleWorld(31, n_contexts=2)
        actions = random.Random(801)
        episode(core, world, 1, rng=actions)
        for _ in range(511):
            episode(core, world, 0, rng=actions)
        self.assertEqual(core.steps, 512)
        self.assertEqual(len(core.tasks[1]["records"]), 1)
        self.assertEqual(core.required_fit_records(), 257)
        self.assertEqual(core.attempts, 1)
        self.assertEqual(core.trial["fit_required_records"], 257)
        self.assertEqual(SharedLearner.restore(core.checkpoint()).checkpoint(), core.checkpoint())

    def test_single_context_shared_adapter_default_learns_and_resumes(self):
        adapter = SharedAdapter(seed=91)
        world = ScaleWorld(31, n_contexts=1)
        rng = random.Random(801)
        sequence = 0
        for i in range(6000):
            events, target = world.episode(0)
            for event in events:
                prediction = adapter.submit_observation(wire_symbol(sequence,
                    event.get("token", "sealed"), end=event["kind"] == "surface"))
                sequence += 1
            action = rng.randrange(4)
            request = adapter.register_action(agent_proposal(prediction, action), executor_id="executor")
            if i == 300:
                adapter = SharedAdapter.restore(json.loads(json.dumps(adapter.checkpoint())))
            adapter.submit_receipt(observed_receipt(request, int(action == target)))
        self.assertGreaterEqual(adapter._learner.admissions, 1)
        self.assertEqual(adapter.metrics()["model_revision"], 6000)

    def test_disappearing_scope_expires_and_resume_does_not_reset_wait(self):
        core = train(SharedLearner(91, max_tasks=2, n_actions=2, trial_stall_limit=128),
                     ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
        world = ScaleWorld(31, n_contexts=2, n_actions=2)
        for _ in range(4096):
            episode(core, world, 0, changed=True)
            if core.trial is not None:
                break
        self.assertIsNotNone(core.trial)
        self.assertEqual(core.trial["scope"], 0)
        attempt = core.attempts
        for _ in range(100):
            episode(core, world, 1)
        resumed = SharedLearner.restore(json.loads(json.dumps(core.checkpoint())))
        for _ in range(27):
            events, target = world.episode(1)
            for model in (core, resumed):
                for event in events:
                    model.receive(event)
                model.learn(0, int(target == 0))
        self.assertIsNotNone(core.trial)
        events, target = world.episode(1)
        for model in (core, resumed):
            for event in events:
                model.receive(event)
            model.learn(0, int(target == 0))
            self.assertIsNone(model.trial)
            self.assertEqual(model.attempts, attempt)
            self.assertEqual(model.decisions[-1]["decision"], "expired")
            self.assertNotIn("relevance", model.decisions[-1])
        self.assertEqual(core.checkpoint(), resumed.checkpoint())
        rng = random.Random(91)
        for _ in range(600):
            events, target = world.episode(1)
            for event in events:
                core.receive(event)
            core.learn(0, rng.randrange(2))
        self.assertGreater(core.attempts, attempt)

    def test_principal_return_refreshes_stall_counter(self):
        core = train(SharedLearner(91, max_tasks=2, n_actions=2, trial_stall_limit=128),
                     ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
        world = ScaleWorld(31, n_contexts=2, n_actions=2)
        for _ in range(4096):
            episode(core, world, 0, changed=True)
            if core.trial is not None:
                break
        self.assertIsNotNone(core.trial)
        for _ in range(127):
            episode(core, world, 1)
        self.assertEqual(core.metrics()["trial_idle_interactions"], 127)
        episode(core, world, 0, changed=True)
        self.assertEqual(core.metrics()["trial_idle_interactions"], 0)
        for _ in range(127):
            episode(core, world, 1)
        self.assertIsNotNone(core.trial)
        episode(core, world, 1)
        self.assertIsNone(core.trial)
        self.assertEqual(core.decisions[-1]["decision"], "expired")

    def test_readout_and_learn_score_agree_in_both_shared_modes(self):
        trained = train(SharedLearner(91, max_tasks=2, n_actions=2),
                        ScaleWorld(31, n_contexts=2, n_actions=2), 10000)
        for mode in (True, False):
            core = SharedLearner.restore(trained.checkpoint())
            core.config["use_structure"] = mode
            world = ScaleWorld(31, n_contexts=2, n_actions=2)
            for i in range(16):
                events, target = world.episode(i % 2)
                for event in events:
                    p = core.receive(event)
                action, y = i % 2, int(i % 2 == target)
                recorded = core.learn(action, y)
                self.assertEqual(recorded, p[action])
                self.assertAlmostEqual(core.tasks[i % 2]["losses"][-1], (p[action] - y) ** 2)

    def test_temporal_ablation_scores_public_probability(self):
        core, world = TemporalLearner(105), TemporalWorld(72)
        rng = random.Random(8101)
        for _ in range(6000):
            temporal_episode(world, [core], rng.randrange(2))
        core.config["use_structure"] = False
        for i in range(16):
            while True:
                event = world.next_event()
                p = core.receive(event)
                if p is not None:
                    break
            y = world.act(i % 2)
            core.learn(i % 2, y)
            self.assertAlmostEqual(core.tasks[0]["losses"][-1], (p[i % 2] - y) ** 2)

    def test_counter_search_decision_and_trial_corruptions_rejected(self):
        core = train(SharedLearner(5, max_tasks=4), ScaleWorld(1, n_contexts=4), 512)
        original = core.checkpoint()
        self.assertEqual(SharedLearner.restore(original).checkpoint(), original)
        mutators = [
            lambda s: s["active"]["counts"][0].__setitem__(0, s["active"]["counts"][0][0] + 1),
            lambda s: s["searches"].__setitem__(0, {"attempt": 999999, "scope": "wrong"}),
            lambda s: s["searches"][0].__setitem__("at", s["steps"] + 1),
            lambda s: s["searches"][0].__setitem__("program", [{}]),
            lambda s: s["searches"][0].__setitem__("program", [1, "bad"]),
            lambda s: s["trial"].__setitem__("last_progress_at", s["steps"] + 1),
            lambda s: s.__setitem__("neural_updates", s["neural_updates"] + 1),
        ]
        for mutate in mutators:
            bad = copy.deepcopy(original)
            mutate(bad)
            with self.assertRaises(ValueError):
                SharedLearner.restore(bad)
        self.assertEqual(core.checkpoint(), original)

    def test_last_token_must_be_bound_and_present(self):
        adapter = SharedAdapter()
        adapter.submit_observation(wire_symbol(0, "a"))
        bad = adapter.checkpoint()
        bad["last_observation"]["payload"]["value"] = "b"
        with self.assertRaises(ValueError):
            SharedAdapter.restore(bad)

    def test_restoration_rejects_antipodes_but_accepts_regular_neighbours(self):
        for model in (SpherePredictor(), SharedLearner().active):
            for anchor in model.anchors:
                bad = model.checkpoint()
                bad["points"][0][0] = [-v for v in anchor]
                with self.assertRaises(ValueError):
                    type(model).restore(bad)
            state = model.checkpoint()
            state["points"][0][0] = unit([-1, 1e-5, 1e-5])
            restored = type(model).restore(state)
            diagnostic = restored.update(0, 1, 0)
            self.assertLess(diagnostic["sphere_residual"], 1e-10)

    def test_shared_seed_validated_before_allocation(self):
        with self.assertRaises(ValueError):
            SharedLearner(2**53 + 1)
        core = SharedLearner(2**53 - 1)
        self.assertEqual(SharedLearner.restore(json.loads(json.dumps(core.checkpoint()))).checkpoint(),
                         core.checkpoint())


if __name__ == "__main__":
    unittest.main()
