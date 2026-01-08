# -*- coding: utf-8 -*-
"""
Unit tests for team index mapping and valid teams generation.

Tests ensure:
1. Team indices are within bounds for each surgery type
2. Baseline identity mapping works correctly
3. Valid teams are properly generated from capability model
"""

import unittest
from typing import Dict, List, Tuple, Optional

# Mock capability model for testing
class MockCap:
    def __init__(self):
        self.main_by_type = {
            "TypeA": ["S1", "S2"],
            "TypeB": ["S3", "S4", "S5"],
        }
        self.a1_by_type = {
            "TypeA": ["S3", "S4"],
            "TypeB": ["S6", "S7"],
        }
        self.a2_by_type = {
            "TypeA": ["S5", "S6"],
            "TypeB": ["S8"],
        }


class TestValidTeamsGeneration(unittest.TestCase):
    """Test valid team building from capability model."""
    
    def test_build_valid_teams_structure(self):
        """Valid teams should include both 3-person and 2-person teams."""
        from ga_optimize_priority_fullschedule import build_valid_teams_by_type
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        
        # Should have entries for both types
        self.assertIn("TypeA", valid_teams)
        self.assertIn("TypeB", valid_teams)
        
        # TypeA teams
        teams_a = valid_teams["TypeA"]
        self.assertGreater(len(teams_a), 0, "TypeA should have teams")
        
        # Check 3-person teams exist
        three_person_a = [t for t in teams_a if t[2] is not None]
        self.assertGreater(len(three_person_a), 0, "Should have 3-person teams")
        
        # Check 2-person teams exist
        two_person_a = [t for t in teams_a if t[2] is None]
        self.assertGreater(len(two_person_a), 0, "Should have 2-person teams")
    
    def test_valid_teams_no_duplicates_in_team(self):
        """Each team should have distinct surgeons."""
        from ga_optimize_priority_fullschedule import build_valid_teams_by_type
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        
        for stype, teams in valid_teams.items():
            for team in teams:
                main, a1, a2 = team
                # Main and assist1 must be different
                self.assertNotEqual(main, a1, f"Main and assist1 are same in {team}")
                # If assist2 exists, must differ from main and assist1
                if a2 is not None:
                    self.assertNotEqual(main, a2, f"Main and assist2 are same in {team}")
                    self.assertNotEqual(a1, a2, f"Assist1 and assist2 are same in {team}")
    
    def test_teams_from_capability_lists(self):
        """Teams should only use surgeons from capability lists."""
        from ga_optimize_priority_fullschedule import build_valid_teams_by_type
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        
        # TypeA teams
        for team in valid_teams["TypeA"]:
            main, a1, a2 = team
            self.assertIn(main, cap.main_by_type["TypeA"])
            self.assertIn(a1, cap.a1_by_type["TypeA"])
            if a2 is not None:
                self.assertIn(a2, cap.a2_by_type["TypeA"])


class TestTeamToIndexMapping(unittest.TestCase):
    """Test reverse mapping from team tuple to index."""
    
    def test_team_to_idx_map_structure(self):
        """Team to index map should cover all surgery types."""
        from ga_optimize_priority_fullschedule import (
            build_valid_teams_by_type,
            build_team_to_idx_map
        )
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        team_to_idx = build_team_to_idx_map(valid_teams)
        
        # Should have same keys
        self.assertEqual(set(team_to_idx.keys()), set(valid_teams.keys()))
        
        # Each surgery type should map all its teams
        for stype in valid_teams:
            self.assertIn(stype, team_to_idx)
            self.assertEqual(len(team_to_idx[stype]), len(valid_teams[stype]))
    
    def test_team_to_idx_round_trip(self):
        """Team -> idx -> team should be identity."""
        from ga_optimize_priority_fullschedule import (
            build_valid_teams_by_type,
            build_team_to_idx_map
        )
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        team_to_idx = build_team_to_idx_map(valid_teams)
        
        for stype in valid_teams:
            teams = valid_teams[stype]
            mapping = team_to_idx[stype]
            
            for team in teams:
                # Get index
                idx = mapping[team]
                # Retrieve team back
                retrieved_team = teams[idx]
                self.assertEqual(team, retrieved_team, "Round-trip should preserve team")
    
    def test_baseline_team_lookup(self):
        """Can find baseline team in valid teams list."""
        from ga_optimize_priority_fullschedule import (
            build_valid_teams_by_type,
            build_team_to_idx_map
        )
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        team_to_idx = build_team_to_idx_map(valid_teams)
        
        # Simulate baseline team for TypeA
        baseline_team = ("S1", "S3", "S5")  # Should be in valid teams
        
        if baseline_team in team_to_idx["TypeA"]:
            idx = team_to_idx["TypeA"][baseline_team]
            self.assertIsInstance(idx, int)
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, len(valid_teams["TypeA"]))
        else:
            self.fail(f"Baseline team {baseline_team} not found in valid teams for TypeA")


class TestTeamIndexBounds(unittest.TestCase):
    """Test that team indices stay within bounds."""
    
    def test_team_idx_within_bounds(self):
        """Team index must be within valid range for surgery type."""
        from ga_optimize_priority_fullschedule import build_valid_teams_by_type
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        
        # Simulate individual with team indices
        elective_cases = {
            1: {"surgery_type": "TypeA"},
            2: {"surgery_type": "TypeB"},
            3: {"surgery_type": "TypeA"},
        }
        
        team_idx_by_pid = {
            1: 0,
            2: len(valid_teams["TypeB"]) - 1,  # Last valid index
            3: 2,
        }
        
        # Verify all indices are valid
        for pid, case in elective_cases.items():
            stype = case["surgery_type"]
            team_idx = team_idx_by_pid[pid]
            
            self.assertGreaterEqual(team_idx, 0, f"Index for PID {pid} is negative")
            self.assertLess(team_idx, len(valid_teams[stype]), 
                           f"Index for PID {pid} exceeds valid teams count")
    
    def test_modulo_handles_out_of_bounds(self):
        """Decoder should use modulo to handle out-of-bounds indices gracefully."""
        from ga_optimize_priority_fullschedule import build_valid_teams_by_type
        
        cap = MockCap()
        valid_teams = build_valid_teams_by_type(cap)
        
        stype = "TypeA"
        n_teams = len(valid_teams[stype])
        
        # Simulate out-of-bounds indices (mutation can create these)
        out_of_bounds_indices = [n_teams, n_teams + 5, n_teams * 10]
        
        for idx in out_of_bounds_indices:
            # Modulo should bring it back to valid range
            valid_idx = idx % n_teams
            self.assertGreaterEqual(valid_idx, 0)
            self.assertLess(valid_idx, n_teams)
            
            # Should be able to retrieve team
            team = valid_teams[stype][valid_idx]
            self.assertIsInstance(team, tuple)
            self.assertEqual(len(team), 3)  # (main, a1, a2_or_None)


if __name__ == "__main__":
    print("=" * 80)
    print("Running Phase 2 Tests: Team Index Mapping & Valid Teams")
    print("=" * 80)
    unittest.main(verbosity=2)
