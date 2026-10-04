"""Plastic reuse, frozen validation, old imports and exact continuation."""
import copy
import json
import math
import random
import unittest

from first_piece.calibrated import CalibratedLearner
from first_piece.calibrated_adapter import CalibratedAdapter
from first_piece.plastic_revision import PlasticRevisionLearner, FAST_HORIZONS, spherical_mean
from first_piece.plastic_revision_adapter import PlasticRevisionAdapter
from first_piece.scale_world import ScaleWorld
from first_piece.shared import log_probability
from first_piece.spherical import unit, norm
from first_piece.tests.test_shared import train, wire_symbol
from first_piece.integration_probe import agent_proposal, observed_receipt


def canonical(core):
    data = core.checkpoint()
    for s in data["searches"]:
        s["elapsed_seconds"] = 0
    return data


class PlasticRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.learnt = train(CalibratedLearner(100, max_tasks=8, max_symbols=16),
                           ScaleWorld(400, n_symbols=16, n_contexts=4), 10000).checkpoint()
        cls.pending = train(PlasticRevisionLearner(5, max_tasks=4, max_symbols=16),
                            ScaleWorld(400, n_symbols=16, n_contexts=4), 600).checkpoint()
        assert cls.pending["trial"] is not None
        assert cls.pending["frozen_reference"] is not None

    def core(self):
        return PlasticRevisionLearner.restore(
            PlasticRevisionLearner.from_calibrated_checkpoint(self.learnt))

    def test_initialization_reuses_spherical_points_but_restarts_optimizer_age(self):
        core = self.core()
        rows = [(slot, *r) for slot in sorted(core.tasks) for r in core.tasks[slot]["records"]]
        before, updates = core.active.checkpoint(), core.neural_updates
        candidate, control, report = core._initialize_banks(core.program, rows)
        self.assertGreater(report["transferred_candidate_points"], 0)
        self.assertGreater(report["transferred_control_points"], 0)
        self.assertEqual(report["mapped_records"], len(rows))
        self.assertEqual(sum(map(sum, candidate.counts)), 0)
        self.assertEqual(sum(map(sum, control.counts)), 0)
        self.assertEqual(core.neural_updates, updates)
        self.assertEqual(core.active.checkpoint(), before)
        neutral = core._new_model()
        for route in range(2 ** len(core.program)):
            for a in range(4):
                if candidate.points[route][a] != neutral.points[route][a]:
                    self.assertEqual(candidate.points[route][a], core.active.points[route][a])
                self.assertAlmostEqual(norm(candidate.points[route][a]), 1)

    def test_extending_a_program_maps_semantic_routes_instead_of_copying_indices(self):
        core = self.core()
        self.assertEqual(len(core.program), 2)
        rows = [(slot, *r) for slot in sorted(core.tasks) for r in core.tasks[slot]["records"]]
        program = sorted([*core.program, core.context_offset])
        candidate, _, report = core._initialize_banks(program, rows)
        self.assertGreater(report["transferred_candidate_points"], 0)
        neutral = core._new_model()
        for r in range(8):
            for a in range(4):
                if candidate.points[r][a] != neutral.points[r][a]:
                    self.assertEqual(candidate.points[r][a], core.active.points[r & 3][a])

    def test_intrinsic_initialization_is_equivariant_under_rotation(self):
        points = [unit([1, .4, .2]), unit([.4, 1, .1]), unit([.7, .8, .4])]
        def rotate(p):
            angle = .7
            return [math.cos(angle) * p[0] - math.sin(angle) * p[1],
                    math.sin(angle) * p[0] + math.cos(angle) * p[1], p[2]]
        a, steps = spherical_mean(points, [1, 3, 2])
        b, other = spherical_mean([rotate(p) for p in points], [1, 3, 2])
        self.assertEqual(steps, other)
        self.assertLess(max(abs(x-y) for x, y in zip(rotate(a), b)), 1e-12)

    def test_antipodal_source_mean_has_an_explicit_neutral_fallback(self):
        core = PlasticRevisionLearner(max_tasks=4, max_symbols=16)
        core.active.points[0][0], core.active.points[1][0] = [0, 0, 1], [0, 0, -1]
        rows = [(0, 1, 0, coin, 0, 1) for _ in range(8) for coin in (0, 1)]
        candidate, _, report = core._initialize_banks([0], rows)
        self.assertGreater(report["ambiguous_means"], 0)
        self.assertEqual(candidate.points[1][0], core._new_model().points[1][0])

    def test_initial_reference_stays_frozen_while_working_banks_learn(self):
        core = PlasticRevisionLearner.restore(self.pending)
        frozen = core.checkpoint()["frozen_reference"]
        active = core.active.checkpoint()
        world, rng = ScaleWorld(400, n_symbols=16, n_contexts=4), random.Random(44)
        for i in range(30):
            events, _ = world.episode(i % 4)
            for event in events:
                p = core.receive(event)
            action, y = rng.randrange(4), int(rng.random() < .25)
            self.assertEqual(core.learn(action, y), p[action])
        self.assertEqual(core.checkpoint()["frozen_reference"], frozen)
        self.assertNotEqual(core.active.checkpoint(), active)
        self.assertEqual(core.metrics()["allocated_points_including_trial"], 160)
        self.assertEqual(core._horizons(), FAST_HORIZONS)

    def test_fixed_ranges_cover_every_action_route_and_both_labels(self):
        core = PlasticRevisionLearner.restore(self.pending)
        widths = core._validation(core.attempts)["widths"]
        for old, new in core._principal_pairs([], core.trial["program"], None):
            for a in range(4):
                p = core.candidate.probability(a, new)
                q = core._frozen_reference["bank"].probability(a, old)
                gains = [log_probability(p, y)-log_probability(q, y) for y in (0, 1)]
                self.assertLessEqual(abs(gains[1]-gains[0]), widths["improvement"]+1e-12)
                for coin in range(8):
                    q = core.control.probability(a, coin)
                    gains = [log_probability(p, y)-log_probability(q, y) for y in (0, 1)]
                    self.assertLessEqual(abs(gains[1]-gains[0]), widths["relevance"]+1e-12)

    def test_pending_targeted_revision_resumes_through_a_real_admission(self):
        core, world, rng = self.core(), ScaleWorld(400, n_symbols=16, n_contexts=4), random.Random(108)
        for i in range(6000):
            events, target = world.episode(i % 4, changed=True)
            for event in events:
                core.receive(event)
            action = rng.randrange(4)
            core.learn(action, int(action == target))
            if core.trial is not None and core.trial["scope"] == 0 and core.trial["n"] == 32:
                break
        self.assertIsNotNone(core.trial)
        restored = PlasticRevisionLearner.restore(json.loads(json.dumps(core.checkpoint())))
        before = core.admissions
        for i in range(20000):
            events, target = world.episode(i % 4, changed=True)
            action = rng.randrange(4)
            for model in (core, restored):
                for event in events:
                    p = model.receive(event)
                self.assertEqual(model.learn(action, int(action == target)), p[action])
            if core.admissions > before:
                break
        self.assertGreater(core.admissions, before)
        self.assertEqual(canonical(core), canonical(restored))

    def test_corrupt_live_range_reference_and_initialization_are_rejected(self):
        for field in ("width", "horizons", "reference", "mapping", "frozen_at", "frontier"):
            bad = copy.deepcopy(self.pending)
            if field == "width":
                bad["searches"][-1]["validation"]["widths"]["relevance"] *= .5
            elif field == "horizons":
                bad["searches"][-1]["validation"]["horizons"][1] = 513
            elif field == "reference":
                bad["searches"][-1]["validation"]["reference"] = "moving_plastic"
            elif field == "mapping":
                bad["searches"][-1]["initialization"]["mapped_records"] += 1
            elif field == "frozen_at":
                bad["frozen_reference"]["at"] -= 1
            else:
                bad["revision_start_attempt"] = bad["attempts"]+2
            with self.subTest(field=field), self.assertRaises(ValueError):
                PlasticRevisionLearner.restore(bad)
        core = PlasticRevisionLearner.restore(self.pending)
        before = core.checkpoint()
        fork = core._transaction_copy()
        fork._frozen_reference["bank"].points[0][0][0] += .1
        self.assertEqual(core.checkpoint(), before)

    def test_old_pending_trial_keeps_original_horizons_predictions_and_risk(self):
        old = train(CalibratedLearner(5, max_tasks=4, max_symbols=16),
                    ScaleWorld(400, n_symbols=16, n_contexts=4), 600)
        for event in ScaleWorld(400, n_symbols=16, n_contexts=4).episode(0)[0]:
            p = old.receive(event)
        core = PlasticRevisionLearner.restore(
            PlasticRevisionLearner.from_calibrated_checkpoint(old.checkpoint()))
        self.assertEqual(core.pending_probabilities(), p)
        self.assertIsNone(core._frozen_reference)
        self.assertEqual(core._horizons(core.attempts), (128, 1024, 4096, 8192, 16384))
        self.assertEqual(core._horizons(core.attempts+1), FAST_HORIZONS)
        self.assertEqual(core.metrics()["lifetime_alpha_upper_bound"], .05)
        for key in ("trial", "rng", "searches", "decisions", "active", "baseline", "candidate", "control"):
            self.assertEqual(core.checkpoint()[key], old.checkpoint()[key])

    def test_disabling_both_changes_reproduces_the_previous_engine_exactly(self):
        cores = [CalibratedLearner(5, max_tasks=4, max_symbols=16),
                 PlasticRevisionLearner(5, max_tasks=4, max_symbols=16,
                                       reuse_plastic_weights=False, bounded_validation_ranges=False)]
        world, rng = ScaleWorld(400, n_symbols=16, n_contexts=4), random.Random(801)
        for i in range(1200):
            events, target = world.episode(i % 4)
            a = rng.randrange(4)
            for core in cores:
                for event in events:
                    core.receive(event)
                core.learn(a, int(a == target))
        old, new = map(canonical, cores)
        for k in ("revision_start_attempt", "revision_import_at", "frozen_reference", "revision_variance", "archived_supersessions"):
            new.pop(k)
        for k in ("reuse_plastic_weights", "bounded_validation_ranges"):
            new["config"].pop(k)
        for s in new["searches"]:
            s.pop("initialization")
            s["validation"].pop("reference")
            s["validation"].pop("variance_checks")
            s["validation"].pop("refresh_checks")
        new["format"], new["implementation"] = old["format"], old["implementation"]
        self.assertEqual(new, old)

    def test_wire_import_and_duplicate_receipt_keep_one_learning_update(self):
        old = CalibratedAdapter(actions=("left", "right"))
        old.submit_observation(wire_symbol(0, "opaque"))
        p = old.submit_observation(wire_symbol(1, "sealed", end=True))
        request = old.register_action(agent_proposal(p, 0), executor_id="executor")
        core = PlasticRevisionAdapter.restore(PlasticRevisionAdapter.from_calibrated_checkpoint(old.checkpoint()))
        self.assertEqual(core.current_prediction(), p)
        ack = core.submit_receipt(observed_receipt(request, 1))
        after = core.checkpoint()
        self.assertEqual(core.submit_receipt(observed_receipt(request, 1)), ack)
        self.assertEqual(core.checkpoint(), after)
        self.assertEqual(core.metrics()["model_revision"], 1)


if __name__ == "__main__":
    unittest.main()
