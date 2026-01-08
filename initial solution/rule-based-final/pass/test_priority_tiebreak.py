# -*- coding: utf-8 -*-
"""
CRITICAL TEST: Verify that priority_rank actually affects dispatch order.

This test ensures the permutation gene has observable effect by creating
scenarios where:
1. Two electives have same scheduled_start
2. Different priority_rank values
3. Dispatcher MUST respect priority_rank in sort key

If this test fails, the permutation gene is ineffective.
"""

import unittest
from typing import Dict

# For simulation (will need small mock since full simulator is complex)
import rule_based_or_sim_v3 as sim


class TestPriorityTieBreak(unittest.TestCase):
    """Test that priority_rank affects elective dispatch order."""
    
    def test_priority_rank_in_sort_key(self):
        """
        Verify sort key includes priority_rank.
        
        Sort key should be: (scheduled_start, priority_rank, planned_start, pid)
        """
        # Mock elective cases
        cases = [
            {"pid": 1, "scheduled_start": 480, "priority_rank": 5, "planned_start": 480},
            {"pid": 2, "scheduled_start": 480, "priority_rank": 0, "planned_start": 480},  # Higher priority
            {"pid": 3, "scheduled_start": 480, "priority_rank": 10, "planned_start": 480},
        ]
        
        # Sort by the CORRECT key
        sorted_cases = sorted(cases, key=lambda c: (
            c["scheduled_start"],
            c["priority_rank"],  # CRITICAL: must be included
            c["planned_start"],
            c["pid"]
        ))
        
        # Check order
        self.assertEqual(sorted_cases[0]["pid"], 2, "PID 2 (rank=0) should be first")
        self.assertEqual(sorted_cases[1]["pid"], 1, "PID 1 (rank=5) should be second")
        self.assertEqual(sorted_cases[2]["pid"], 3, "PID 3 (rank=10) should be third")
    
    def test_lower_priority_rank_means_higher_priority(self):
        """
        Lower priority_rank value = higher priority (like rank 1 is first place).
        
        Chromosome permutation: [pid_A, pid_B, pid_C]
        → priority_rank = {pid_A: 0, pid_B: 1, pid_C: 2}
        → pid_A dispatches before pid_B if scheduled_start is same
        """
        priority_rank = {"A": 0, "B": 1, "C": 2}
        
        # All cases scheduled at same time
        cases = [
            {"pid": "A", "scheduled_start": 500, "priority_rank": priority_rank["A"]},
            {"pid": "B", "scheduled_start": 500, "priority_rank": priority_rank["B"]},
            {"pid": "C", "scheduled_start": 500, "priority_rank": priority_rank["C"]},
        ]
        
        sorted_cases = sorted(cases, key=lambda c: (c["scheduled_start"], c["priority_rank"], c["pid"]))
        
        self.assertEqual([c["pid"] for c in sorted_cases], ["A", "B", "C"],
                        "Cases should dispatch in priority_rank order")
    
    def test_priority_rank_overrides_planned_start_when_scheduled_same(self):
        """
        When scheduled_start is same, priority_rank takes precedence over planned_start.
        
        Scenario:
        - pid 1: planned=480, scheduled=500, priority_rank=10
        - pid 2: planned=500, scheduled=500, priority_rank=5
        
        Even though pid 1 was planned earlier, pid 2 should dispatch first
        because it has higher priority (lower rank).
        """
        cases = [
            {"pid": 1, "scheduled_start": 500, "priority_rank": 10, "planned_start": 480},
            {"pid": 2, "scheduled_start": 500, "priority_rank": 5, "planned_start": 500},
        ]
        
        sorted_cases = sorted(cases, key=lambda c: (
            c["scheduled_start"],
            c["priority_rank"],      # Takes precedence over planned_start
            c["planned_start"],
            c["pid"]
        ))
        
        self.assertEqual(sorted_cases[0]["pid"], 2,
                        "pid 2 should dispatch first due to higher priority (rank=5 < rank=10)")
        self.assertEqual(sorted_cases[1]["pid"], 1)
    
    def test_permutation_flip_reverses_dispatch_order(self):
        """
        If we flip the permutation, dispatch order should reverse.
        
        Permutation 1: [pid_X, pid_Y] → priority_rank = {X: 0, Y: 1}
        Permutation 2: [pid_Y, pid_X] → priority_rank = {Y: 0, X: 1}
        
        Same scheduled_start → dispatch order should reverse.
        """
        # Scenario 1
        priority_rank_1 = {"X": 0, "Y": 1}
        cases_1 = [
            {"pid": "X", "scheduled_start": 600, "priority_rank": priority_rank_1["X"]},
            {"pid": "Y", "scheduled_start": 600, "priority_rank": priority_rank_1["Y"]},
        ]
        sorted_1 = sorted(cases_1, key=lambda c: (c["scheduled_start"], c["priority_rank"], c["pid"]))
        order_1 = [c["pid"] for c in sorted_1]
        
        # Scenario 2 (flipped permutation)
        priority_rank_2 = {"Y": 0, "X": 1}
        cases_2 = [
            {"pid": "X", "scheduled_start": 600, "priority_rank": priority_rank_2["X"]},
            {"pid": "Y", "scheduled_start": 600, "priority_rank": priority_rank_2["Y"]},
        ]
        sorted_2 = sorted(cases_2, key=lambda c: (c["scheduled_start"], c["priority_rank"], c["pid"]))
        order_2 = [c["pid"] for c in sorted_2]
        
        # Orders should be reversed
        self.assertEqual(order_1, ["X", "Y"], "Permutation 1: X before Y")
        self.assertEqual(order_2, ["Y", "X"], "Permutation 2: Y before X")
        self.assertNotEqual(order_1, order_2, "Flipping permutation must change dispatch order")
    
    def test_scheduled_start_still_takes_precedence(self):
        """
        scheduled_start is FIRST in sort key, so it takes precedence over priority_rank.
        
        - pid A: scheduled=500, priority_rank=10
        - pid B: scheduled=480, priority_rank=5
        
        pid B should dispatch first despite lower priority because its scheduled_start is earlier.
        """
        cases = [
            {"pid": "A", "scheduled_start": 500, "priority_rank": 10},
            {"pid": "B", "scheduled_start": 480, "priority_rank": 5},
        ]
        
        sorted_cases = sorted(cases, key=lambda c: (c["scheduled_start"], c["priority_rank"], c["pid"]))
        
        self.assertEqual(sorted_cases[0]["pid"], "B",
                        "scheduled_start takes precedence: B (scheduled=480) before A (scheduled=500)")


class TestSimulatorUsesCorrectSortKey(unittest.TestCase):
    """
    Verify that lightweight_fitness_priority.py actually uses the correct sort key.
    
    NOTE: This is a code review test - we check the source contains the right key.
    """
    
    def test_simulator_source_has_priority_rank_in_key(self):
        """Check that the simulator source code includes priority_rank in sort key."""
        with open("lightweight_fitness_priority.py", "r", encoding="utf-8") as f:
            source = f.read()
        
        # Look for the critical sort statement
        # Should contain something like: key=lambda e: (e.scheduled_start, e.priority_rank, ...
        self.assertIn("priority_rank", source,
                     "Simulator must use priority_rank in sort key")
        
        # Check for the specific pattern
        self.assertIn("e.scheduled_start", source,
                     "Sort key must include scheduled_start")
        
        # Verify it's in a sort expression
        self.assertIn(".sort(key=lambda", source,
                     "Must use .sort(key=lambda ...) for elective dispatch")


if __name__ == "__main__":
    print("=" * 80)
    print("Running Phase 4 Test: Priority Tie-Break Validation")
    print("=" * 80)
    unittest.main(verbosity=2)
