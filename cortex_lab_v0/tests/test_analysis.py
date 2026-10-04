import math
import unittest

from cortex_lab_v0.analyze import (
    bootstrap_mean_interval, describe, paired_comparison,
)


class AnalysisTests(unittest.TestCase):
    def test_summary_matches_hand_calculation(self):
        result = describe([1., 3.])
        self.assertEqual(result["mean"], 2.)
        self.assertEqual(result["median"], 2.)
        self.assertAlmostEqual(result["sample_std"], math.sqrt(2))
        self.assertEqual((result["min"], result["max"], result["n"]), (1., 3., 2))

    def test_pairing_uses_seed_identity_and_difference_direction(self):
        result = paired_comparison({4: .1, 1: .4}, {1: .3, 4: .2})
        self.assertAlmostEqual(result["left_minus_right"]["mean"], 0.)
        self.assertEqual(result["left_better_seeds"], 1)
        self.assertEqual(result["right_better_seeds"], 1)
        self.assertLess(result["bootstrap95_mean_difference"][0], 0)
        self.assertGreater(result["bootstrap95_mean_difference"][1], 0)
        with self.assertRaises(ValueError):
            paired_comparison({1: .1}, {2: .1})

    def test_constant_bootstrap_has_no_spurious_uncertainty(self):
        self.assertEqual(bootstrap_mean_interval([.2] * 20, samples=100), [.2, .2])

    def test_missing_and_nonfinite_values_are_rejected(self):
        for values in ([], [float("nan")], [float("inf")]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    describe(values)


if __name__ == "__main__":
    unittest.main()
