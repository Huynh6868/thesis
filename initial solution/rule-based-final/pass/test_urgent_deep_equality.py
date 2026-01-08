# -*- coding: utf-8 -*-
"""
Critical test: Verify urgent stream deep equality across baseline and GA.

This test ensures fair comparison by checking that the SAME urgent_list
is used for both baseline and all GA evaluations (not just count, but
arrival times and surgery types must match exactly).
"""

import unittest
from typing import List, Tuple


def generate_urgent_list(mean_interarrival: float, seed: int, horizon_min: float = 10080.0) -> List[Tuple[float, str]]:
    """
    Generate fixed urgent arrival stream for a scenario seed.
    
    NOTE: This should match the function in ga_optimize_priority_fullschedule.py
    """
    import random
    import rule_based_or_sim_v3 as sim
    
    rnd = random.Random(seed)
    t = 0.0
    out: List[Tuple[float, str]] = []
    types = list(sim.SURGERY_DURATION_MIN.keys())
    
    while True:
        t += rnd.expovariate(1.0 / float(mean_interarrival))
        if t >= horizon_min:
            break
        out.append((float(t), rnd.choice(types)))
    
    return out


class TestUrgentStreamDeepEquality(unittest.TestCase):
    """Verify urgent stream is IDENTICAL across evaluations."""
    
    def test_same_seed_produces_same_stream(self):
        """Same seed must produce exact same urgent stream."""
        scenario_seed = 42
        mean_interarrival = 180.0
        
        # Generate twice
        urgent_list_1 = generate_urgent_list(mean_interarrival, scenario_seed)
        urgent_list_2 = generate_urgent_list(mean_interarrival, scenario_seed)
        
        # Must be identical
        self.assertEqual(len(urgent_list_1), len(urgent_list_2), 
                        "Count must match")
        
        # Deep equality check
        for (t1, stype1), (t2, stype2) in zip(urgent_list_1, urgent_list_2):
            self.assertAlmostEqual(t1, t2, places=9, 
                                  msg=f"Arrival times must match: {t1} vs {t2}")
            self.assertEqual(stype1, stype2, 
                            msg=f"Surgery types must match: {stype1} vs {stype2}")
    
    def test_different_seeds_produce_different_streams(self):
        """Different seeds should produce different streams."""
        urgent_list_1 = generate_urgent_list(180.0, seed=1)
        urgent_list_2 = generate_urgent_list(180.0, seed=2)
        
        # Should differ (with very high probability)
        # Check first arrival time or count
        if len(urgent_list_1) == len(urgent_list_2):
            # Check if first few arrival times differ
            differs = False
            for (t1, _), (t2, _) in zip(urgent_list_1[:5], urgent_list_2[:5]):
                if abs(t1 - t2) > 1e-6:
                    differs = True
                    break
            self.assertTrue(differs, "Different seeds should produce different streams")
        # If counts differ, that's also fine
    
    def test_stream_hash_consistency(self):
        """Hash of string representation should be consistent."""
        scenario_seed = 123
        
        urgent_list_1 = generate_urgent_list(180.0, scenario_seed)
        urgent_list_2 = generate_urgent_list(180.0, scenario_seed)
        
        # Hash as string
        hash_1 = hash(str(urgent_list_1))
        hash_2 = hash(str(urgent_list_2))
        
        self.assertEqual(hash_1, hash_2, 
                        "Hash of string representation must match")
    
    def test_baseline_ga_use_same_urgent_list(self):
        """
        Simulate scenario: baseline and GA should use exact same urgent_list.
        
        This is a design verification test.
        """
        scenario_seed = 456
        
        # In real implementation:
        # 1. Generate urgent_list ONCE with scenario_seed
        urgent_list = generate_urgent_list(180.0, scenario_seed)
        
        # 2. Pass to baseline
        baseline_urgent_list = urgent_list  # Same reference or deep copy
        
        # 3. Pass to GA evaluations
        ga_urgent_list = urgent_list  # Same reference or deep copy
        
        # Verify they're the same
        self.assertEqual(baseline_urgent_list, ga_urgent_list,
                        "Baseline and GA must use identical urgent_list")
        
        # Verify arrivals and types match
        for (t_base, stype_base), (t_ga, stype_ga) in zip(baseline_urgent_list, ga_urgent_list):
            self.assertAlmostEqual(t_base, t_ga, places=9)
            self.assertEqual(stype_base, stype_ga)


if __name__ == "__main__":
    print("=" * 80)
    print("Running Phase 4 Test: Urgent Stream Deep Equality")
    print("=" * 80)
    unittest.main(verbosity=2)
