# -*- coding: utf-8 -*-
"""
Unit tests for planner feasibility and delayed cases.

Tests ensure:
1. Planner produces schedules with no overlaps (room and surgeon calendars)
2. Cases that cannot be scheduled are marked as delayed
3. Admin hours constraints are respected
"""

import unittest
from typing import Dict, List
import sys

# Test setup
sys.path.insert(0, '.')

import rule_based_or_sim_v3 as sim
from ga_optimize_priority_fullschedule import (
    build_elective_plan,
    build_valid_teams_by_type,
    ElectiveCase,
    _can_insert
)


class TestPlannerFeasibility(unittest.TestCase):
    """Test that planner produces feasible schedules without overlaps."""
    
    def setUp(self):
        """Load work schedule and capability model."""
        self.work = sim.WorkSchedule(
            sim.load_work_schedule_xlsx("lich_lam_viec_tuan1.xlsx"),
            [f"S{i}" for i in range(1, 13)]
        )
        self.cap = sim.load_cap_rank_xlsx("Cap_Rank.xlsx")
        self.valid_teams = build_valid_teams_by_type(self.cap)
    
    def test_planner_no_room_overlaps(self):
        """Planner should not create overlapping room bookings."""
        # Get a valid surgery type from capability model
        stype = list(self.cap.main_by_type.keys())[0]  # Use first available type
        
        # Create simple test case with 3 electives same day
        elective_cases = {
            1: ElectiveCase(
                pid=1,
                surgery_type=stype,
                planned_start=480,  # 08:00 Monday
                duration=60,
                prep_time=30,
                baseline_room=1,
                baseline_team=("S1", "S2", None)
            ),
            2: ElectiveCase(
                pid=2,
                surgery_type=stype,
                planned_start=490,  # 08:10 Monday (overlaps if same room)
                duration=90,
                prep_time=30,
                baseline_room=1,
                baseline_team=("S3", "S4", None)
            ),
            3: ElectiveCase(
                pid=3,
                surgery_type=stype,
                planned_start=500,  # 08:20 Monday
                duration=60,
                prep_time=30,
                baseline_room=1,
                baseline_team=("S5", "S6", None)
            ),
        }
        
        priority_list = [1, 2, 3]
        team_idx = {1: 0, 2: 0, 3: 0}
        
        overrides = build_elective_plan(
            elective_cases=elective_cases,
            priority_list=priority_list,
            team_idx_by_pid=team_idx,
            room_by_pid={1: 1, 2: 1, 3: 1},  # Force same room
            valid_teams_by_type=self.valid_teams,
            work=self.work,
            n_rooms=2,
            rest_time=30,
        )
        
        # Check no overlaps in room 1
        room_bookings = []
        for pid in priority_list:
            c = elective_cases[pid]
            start = overrides.scheduled_start_by_pid[pid]
            end = start + c.duration + c.prep_time
            room = overrides.room_by_pid[pid]
            
            if room == 1:
                # Check this booking doesn't overlap with existing
                for prev_start, prev_end in room_bookings:
                    self.assertFalse(
                        (start < prev_end and end > prev_start),
                        f"Room overlap: [{start}, {end}) overlaps [{prev_start}, {prev_end})"
                    )
                room_bookings.append((start, end))
    
    def test_planner_no_surgeon_overlaps(self):
        """Planner should not create overlapping surgeon bookings."""
        stype = list(self.cap.main_by_type.keys())[0]
        
        # Cases with same surgeon
        elective_cases = {
            1: ElectiveCase(
                pid=1,
                surgery_type=stype,
                planned_start=480,  # 08:00 Monday
                duration=60,
                prep_time=30,
                baseline_room=1,
                baseline_team=("S1", "S2", None)
            ),
            2: ElectiveCase(
                pid=2,
                surgery_type=stype,
                planned_start=490,  # 08:10 Monday (S1 still busy)
                duration=60,
                prep_time=30,
                baseline_room=2,
                baseline_team=("S1", "S3", None)  # Same S1
            ),
        }
        
        priority_list = [1, 2]
        
        # Find team indices for these teams
        team_idx = {}
        teams_for_type = self.valid_teams.get(stype, [])
        for pid, case in elective_cases.items():
            team = case.baseline_team
            if team in teams_for_type:
                team_idx[pid] = teams_for_type.index(team)
            else:
                team_idx[pid] = 0
        
        overrides = build_elective_plan(
            elective_cases=elective_cases,
            priority_list=priority_list,
            team_idx_by_pid=team_idx,
            room_by_pid=None,
            valid_teams_by_type=self.valid_teams,
            work=self.work,
            n_rooms=2,
            rest_time=30,
        )
        
        # Check S1's schedule
        s1_bookings = []
        for pid in priority_list:
            c = elective_cases[pid]
            team = overrides.team_by_pid[pid]
            if "S1" in team:
                start = overrides.scheduled_start_by_pid[pid]
                end = start + c.duration + 30  # rest_time
                
                for prev_start, prev_end in s1_bookings:
                    self.assertFalse(
                        (start < prev_end and end > prev_start),
                        f"S1 overlap: [{start}, {end}) overlaps [{prev_start}, {prev_end})"
                    )
                s1_bookings.append((start, end))
    
    def test_planner_respects_admin_hours(self):
        """All elective cases should start within admin hours."""
        stype = list(self.cap.main_by_type.keys())[0]
        
        elective_cases = {
            1: ElectiveCase(
                pid=1,
                surgery_type=stype,
                planned_start=960,  # 16:00 Monday (end of admin)
                duration=60,
                prep_time=30,
                baseline_room=1,
                baseline_team=("S1", "S2", None)
            ),
        }
        
        priority_list = [1]
        team_idx = {1: 0}
        
        overrides = build_elective_plan(
            elective_cases=elective_cases,
            priority_list=priority_list,
            team_idx_by_pid=team_idx,
            room_by_pid=None,
            valid_teams_by_type=self.valid_teams,
            work=self.work,
            n_rooms=2,
            rest_time=30,
        )
        
        start = overrides.scheduled_start_by_pid[1]
        
        # Check within admin hours
        time_in_day = start % sim.MINUTES_PER_DAY
        day_idx = start // sim.MINUTES_PER_DAY
        weekday = day_idx % 7
        
        # Should be on weekday
        self.assertLessEqual(weekday, 4, f"Should be on weekday, got day {weekday}")
        
        # Should start within admin hours
        self.assertGreaterEqual(time_in_day, sim.ADMIN_SHIFT_START, 
                               f"Start time {time_in_day} before admin start")
        self.assertLess(time_in_day, sim.ADMIN_SHIFT_END,
                       f"Start time {time_in_day} at/after admin end")


class TestDelayedNextWeek(unittest.TestCase):
    """Test handling of cases that cannot be scheduled within horizon."""
    
    def setUp(self):
        """Load work schedule and capability model."""
        self.work = sim.WorkSchedule(
            sim.load_work_schedule_xlsx("lich_lam_viec_tuan1.xlsx"),
            [f"S{i}" for i in range(1, 13)]
        )
        self.cap = sim.load_cap_rank_xlsx("Cap_Rank.xlsx")
        self.valid_teams = build_valid_teams_by_type(self.cap)
    
    def test_unschedulable_marked_beyond_horizon(self):
        """Cases that cannot fit should be scheduled beyond time_limit."""
        stype = list(self.cap.main_by_type.keys())[0]
        
        # Create many overlapping cases to fill the week
        elective_cases = {}
        for i in range(20):  # Many cases
            elective_cases[i] = ElectiveCase(
                pid=i,
                surgery_type=stype,
                planned_start=480 + i * 10,  # Spread across week start
                duration=240,  # Long surgeries (4 hours)
                prep_time=60,
                baseline_room=1,
                baseline_team=("S1", "S2", None)
            )
        
        priority_list = list(range(20))
        team_idx = {i: 0 for i in range(20)}
        
        overrides = build_elective_plan(
            elective_cases=elective_cases,
            priority_list=priority_list,
            team_idx_by_pid=team_idx,
            room_by_pid={i: 1 for i in range(20)},  # All same room
            valid_teams_by_type=self.valid_teams,
            work=self.work,
            n_rooms=1,  # Only 1 room
            rest_time=30,
            max_reschedule_weeks=1,
        )
        
        time_limit = 2 * sim.WEEK_LENGTH  # max_reschedule_weeks=1
        
        # Some cases should be beyond time_limit
        delayed_count = sum(
            1 for pid in priority_list
            if overrides.scheduled_start_by_pid[pid] > time_limit
        )
        
        self.assertGreater(delayed_count, 0, 
                          "With limited resources, some cases should be delayed")
    
    def test_delayed_cases_still_have_assignments(self):
        """Even delayed cases should have room and team assignments."""
        stype = list(self.cap.main_by_type.keys())[0]
        
        elective_cases = {
            1: ElectiveCase(
                pid=1,
                surgery_type=stype,
                planned_start=10000,  # Very late planned start
                duration=60,
                prep_time=30,
                baseline_room=1,
                baseline_team=("S1", "S2", None)
            ),
        }
        
        priority_list = [1]
        team_idx = {1: 0}
        
        overrides = build_elective_plan(
            elective_cases=elective_cases,
            priority_list=priority_list,
            team_idx_by_pid=team_idx,
            room_by_pid=None,
            valid_teams_by_type=self.valid_teams,
            work=self.work,
            n_rooms=2,
            rest_time=30,
            max_reschedule_weeks=1,
        )
        
        # Should have room assignment
        self.assertIn(1, overrides.room_by_pid)
        self.assertGreater(overrides.room_by_pid[1], 0)
        
        # Should have team assignment
        self.assertIn(1, overrides.team_by_pid)
        team = overrides.team_by_pid[1]
        self.assertEqual(len(team), 3)  # (main, a1, a2_or_None)


if __name__ == "__main__":
    print("=" * 80)
    print("Running Phase 3 Tests: Planner Feasibility & Delayed Cases")
    print("=" * 80)
    unittest.main(verbosity=2)
