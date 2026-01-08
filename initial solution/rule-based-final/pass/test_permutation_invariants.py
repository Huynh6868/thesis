# -*- coding: utf-8 -*-
"""
Unit tests for permutation invariants in GA operators.

Tests ensure that crossover and mutation preserve permutation property:
- No duplicate elements
- No missing elements
- Same length as input
"""

import random
import unittest
from typing import List


# ==============================================================================
# Permutation Operators (Temporary - will move to main file later)
# ==============================================================================

def ox_crossover(parent1: List[int], parent2: List[int], rng: random.Random) -> tuple[List[int], List[int]]:
    """
    Order Crossover (OX) for permutations.
    
    Algorithm:
    1. Select random segment from parent1
    2. Copy segment to child1 at same position
    3. Fill remaining from parent2 in order (excluding segment elements)
    4. Repeat symmetrically for child2
    """
    n = len(parent1)
    if n <= 2:
        return parent1[:], parent2[:]
    
    # Random segment
    a, b = sorted(rng.sample(range(n), 2))
    
    def create_child(p1, p2):
        child = [None] * n
        # Copy segment from p1
        child[a:b] = p1[a:b]
        segment_set = set(p1[a:b])
        
        # Fill from p2 (excluding segment)
        fill = [x for x in p2 if x not in segment_set]
        fill_idx = 0
        for i in list(range(0, a)) + list(range(b, n)):
            child[i] = fill[fill_idx]
            fill_idx += 1
        
        return child
    
    child1 = create_child(parent1, parent2)
    child2 = create_child(parent2, parent1)
    
    return child1, child2


def mutate_priority_swap(priority: List[int], rng: random.Random) -> None:
    """Swap mutation: exchange two random positions."""
    if len(priority) < 2:
        return
    i, j = rng.sample(range(len(priority)), 2)
    priority[i], priority[j] = priority[j], priority[i]


def mutate_priority_insert(priority: List[int], rng: random.Random) -> None:
    """Insert mutation: remove element and insert at random position."""
    if len(priority) < 2:
        return
    i = rng.randrange(len(priority))
    j = rng.randrange(len(priority))
    elem = priority.pop(i)
    priority.insert(j, elem)


def mutate_priority_scramble(priority: List[int], rng: random.Random) -> None:
    """Scramble mutation: shuffle random segment."""
    if len(priority) < 2:
        return
    a, b = sorted(rng.sample(range(len(priority)), 2))
    if b - a < 2:
        return
    segment = priority[a:b]
    rng.shuffle(segment)
    priority[a:b] = segment


# ==============================================================================
# Test Cases
# ==============================================================================

class TestPermutationInvariants(unittest.TestCase):
    """Test suite for permutation operators."""
    
    def setUp(self):
        """Fixed seed random generator for reproducibility."""
        self.rng = random.Random(42)
    
    def test_ox_crossover_preserves_elements(self):
        """OX crossover must preserve all elements (no duplicates, no missing)."""
        parent1 = [1, 2, 3, 4, 5, 6, 7, 8]
        parent2 = [8, 7, 6, 5, 4, 3, 2, 1]
        
        for _ in range(100):  # Multiple random runs
            child1, child2 = ox_crossover(parent1, parent2, self.rng)
            
            # Check child1
            self.assertEqual(len(child1), len(parent1), "Child1 length mismatch")
            self.assertEqual(set(child1), set(parent1), "Child1 has wrong elements")
            self.assertEqual(len(set(child1)), len(child1), "Child1 has duplicates")
            
            # Check child2
            self.assertEqual(len(child2), len(parent2), "Child2 length mismatch")
            self.assertEqual(set(child2), set(parent2), "Child2 has wrong elements")
            self.assertEqual(len(set(child2)), len(child2), "Child2 has duplicates")
    
    def test_ox_crossover_small_input(self):
        """OX crossover on small inputs (edge case)."""
        parent1 = [1, 2]
        parent2 = [2, 1]
        
        child1, child2 = ox_crossover(parent1, parent2, self.rng)
        
        self.assertEqual(set(child1), {1, 2})
        self.assertEqual(set(child2), {1, 2})
        self.assertEqual(len(child1), 2)
        self.assertEqual(len(child2), 2)
    
    def test_swap_mutation_preserves_permutation(self):
        """Swap mutation must preserve permutation property."""
        original = [10, 20, 30, 40, 50]
        
        for _ in range(100):
            mutated = original[:]
            mutate_priority_swap(mutated, self.rng)
            
            self.assertEqual(len(mutated), len(original), "Length changed")
            self.assertEqual(set(mutated), set(original), "Elements changed")
            self.assertEqual(len(set(mutated)), len(mutated), "Duplicates created")
    
    def test_insert_mutation_preserves_permutation(self):
        """Insert mutation must preserve permutation property."""
        original = [10, 20, 30, 40, 50]
        
        for _ in range(100):
            mutated = original[:]
            mutate_priority_insert(mutated, self.rng)
            
            self.assertEqual(len(mutated), len(original), "Length changed")
            self.assertEqual(set(mutated), set(original), "Elements changed")
            self.assertEqual(len(set(mutated)), len(mutated), "Duplicates created")
    
    def test_scramble_mutation_preserves_permutation(self):
        """Scramble mutation must preserve permutation property."""
        original = [10, 20, 30, 40, 50, 60, 70]
        
        for _ in range(100):
            mutated = original[:]
            mutate_priority_scramble(mutated, self.rng)
            
            self.assertEqual(len(mutated), len(original), "Length changed")
            self.assertEqual(set(mutated), set(original), "Elements changed")
            self.assertEqual(len(set(mutated)), len(mutated), "Duplicates created")
    
    def test_mutations_on_small_input(self):
        """Mutations on small permutations (edge case)."""
        original = [1, 2]
        
        # Swap
        mutated = original[:]
        mutate_priority_swap(mutated, self.rng)
        self.assertEqual(set(mutated), {1, 2})
        
        # Insert
        mutated = original[:]
        mutate_priority_insert(mutated, self.rng)
        self.assertEqual(set(mutated), {1, 2})
        
        # Scramble
        mutated = original[:]
        mutate_priority_scramble(mutated, self.rng)
        self.assertEqual(set(mutated), {1, 2})
    
    def test_mutations_on_single_element(self):
        """Mutations on single-element list (degenerate case)."""
        original = [42]
        
        mutated = original[:]
        mutate_priority_swap(mutated, self.rng)
        self.assertEqual(mutated, [42])
        
        mutated = original[:]
        mutate_priority_insert(mutated, self.rng)
        self.assertEqual(mutated, [42])
        
        mutated = original[:]
        mutate_priority_scramble(mutated, self.rng)
        self.assertEqual(mutated, [42])


class TestCalendarHelpers(unittest.TestCase):
    """Test suite for calendar interval helpers."""
    
    def test_can_insert_empty_calendar(self):
        """Can insert into empty calendar."""
        from ga_optimize_priority_fullschedule import _can_insert
        
        intervals = []
        self.assertTrue(_can_insert(intervals, 10, 20))
    
    def test_can_insert_no_overlap(self):
        """Can insert when no overlap exists."""
        from ga_optimize_priority_fullschedule import _can_insert
        
        intervals = [(10, 20), (30, 40), (50, 60)]
        
        # Before all
        self.assertTrue(_can_insert(intervals, 0, 5))
        
        # Between first and second
        self.assertTrue(_can_insert(intervals, 22, 28))
        
        # Between second and third
        self.assertTrue(_can_insert(intervals, 42, 48))
        
        # After all
        self.assertTrue(_can_insert(intervals, 65, 70))
    
    def test_can_insert_overlaps(self):
        """Cannot insert when overlap exists."""
        from ga_optimize_priority_fullschedule import _can_insert
        
        intervals = [(10, 20), (30, 40), (50, 60)]
        
        # Overlaps with first
        self.assertFalse(_can_insert(intervals, 5, 15))
        self.assertFalse(_can_insert(intervals, 15, 25))
        self.assertFalse(_can_insert(intervals, 10, 20))  # Exact match
        
        # Overlaps with second
        self.assertFalse(_can_insert(intervals, 25, 35))
        self.assertFalse(_can_insert(intervals, 35, 45))
        
        # Overlaps with third
        self.assertFalse(_can_insert(intervals, 55, 65))
    
    def test_insert_maintains_order(self):
        """Insert maintains sorted order."""
        from ga_optimize_priority_fullschedule import _insert, _can_insert
        
        intervals = [(10, 20), (50, 60)]
        
        # Insert in middle
        self.assertTrue(_can_insert(intervals, 30, 40))
        _insert(intervals, 30, 40)
        self.assertEqual(intervals, [(10, 20), (30, 40), (50, 60)])
        
        # Insert at beginning
        self.assertTrue(_can_insert(intervals, 0, 5))
        _insert(intervals, 0, 5)
        self.assertEqual(intervals, [(0, 5), (10, 20), (30, 40), (50, 60)])
        
        # Insert at end
        self.assertTrue(_can_insert(intervals, 70, 80))
        _insert(intervals, 70, 80)
        self.assertEqual(intervals, [(0, 5), (10, 20), (30, 40), (50, 60), (70, 80)])
    
    def test_calendar_realistic_scenario(self):
        """Realistic scenario: multiple insertions."""
        from ga_optimize_priority_fullschedule import _insert, _can_insert
        
        intervals = []
        
        # Schedule surgeries throughout the day
        surgeries = [(480, 540), (600, 660), (720, 780), (540, 600)]  # Out of order
        
        for start, end in surgeries:
            if _can_insert(intervals, start, end):
                _insert(intervals, start, end)
        
        # Should be sorted
        self.assertEqual(intervals, [(480, 540), (540, 600), (600, 660), (720, 780)])
        
        # Cannot insert overlapping
        self.assertFalse(_can_insert(intervals, 500, 550))
        
        # Can insert in gap
        self.assertTrue(_can_insert(intervals, 660, 720))


if __name__ == "__main__":
    # Run tests
    print("=" * 80)
    print("Running Phase 1 Tests: Permutation Invariants & Calendar Helpers")
    print("=" * 80)
    unittest.main(verbosity=2)
