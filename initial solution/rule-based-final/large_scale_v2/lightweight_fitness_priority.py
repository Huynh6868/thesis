# -*- coding: utf-8 -*-
"""
Lightweight (non-SimPy) evaluator with PRIORITY PERMUTATION support.

CRITICAL ARCHITECTURAL CHANGES from v3_fullschedule:
1. Accepts elective OVERRIDES (from planner) instead of full schedule DataFrame
2. Accepts PRIORITY_RANK dict to enable permutation gene effect
3. Dispatches URGENT FIRST, then elective (GA does NOT control urgent start times)
4. Elective sort key includes priority_rank: (scheduled_start, priority_rank, planned_start, pid)

This ensures:
- Fair urgent comparison (same urgent_list input across all evaluations)
- Permutation gene has strong effect (not just relying on scheduled_start)
- GA controls elective ONLY
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union
import math

import rule_based_or_sim_v3 as sim
from ga_optimize_priority_fullschedule import PlannerOverrides


# ==============================================================================
# Data Structures
# ==============================================================================

@dataclass
class _ElectiveLW:
    """Lightweight elective case for simulator."""
    pid: int
    surgery_type: str
    planned_start: int          # Original baseline planned start
    scheduled_start: int        # From planner override
    priority_rank: int          # From chromosome permutation
    room: int
    main: str
    assist1: str
    assist2: Optional[str]
    duration: int
    prep_time: int = 30         # Default prep time
    status: str = "waiting"     # waiting/executing/completed/delayed
    actual_start: Optional[int] = None
    delayed_weeks: int = 0


@dataclass
class _UrgentLW:
    """Lightweight urgent case for simulator."""
    uid: str
    surgery_type: str
    arrival_time: float
    arrival_bucket: int
    rank: int                   # From capability model
    status: str = "waiting"
    start_time: Optional[int] = None
    room: Optional[int] = None
    team: Optional[Tuple[str, str, Optional[str]]] = None
    complete_time: Optional[int] = None


# ==============================================================================
# Helper Functions
# ==============================================================================

def _ceil_minute(x: float) -> int:
    """Round up arrival time to next integer minute."""
    return int(math.ceil(x - 1e-12))


def _get_rank(cap: sim.CapabilityModel, surgery_type: str) -> int:
    """Get urgency rank for surgery type (1=most urgent)."""
    return cap.rank_by_type.get(surgery_type, 999)


# ==============================================================================
# Main Simulator Function
# ==============================================================================

def simulate_elective_plan_with_urgent(
    elective_overrides: PlannerOverrides,
    elective_baseline: Dict[int, Dict],  # pid -> {surgery_type, planned_start, duration, ...}
    priority_rank: Dict[int, int],       # pid -> rank in priority permutation
    urgent_list: List[Tuple[float, str]],
    work: sim.WorkSchedule,
    cap: sim.CapabilityModel,
    n_rooms: int,
    rest_time: Union[int, Dict[str, int]],
    max_reschedule_weeks: int,
    penalty_next_week: int,
) -> dict:
    """
    Simulate elective plan against fixed urgent stream with priority-based dispatch.
    
    CRITICAL: Urgent dispatch FIRST, elective SECOND with priority_rank tie-break.
    
    Parameters:
    -----------
    elective_overrides : PlannerOverrides
        Scheduled start times, rooms, teams from planner (GA output)
    elective_baseline : dict
        Original elective case data (pid -> properties)
    priority_rank : dict
        PID -> rank in chromosome permutation (0=highest priority)
    urgent_list : list
        Fixed scenario input: [(arrival_time, surgery_type), ...]
    work, cap : loaded from xlsx files
    n_rooms : number of operating rooms
    rest_time : surgeon rest after surgery (minutes)
    max_reschedule_weeks : horizon for rescheduling
    penalty_next_week : penalty for delayed cases
    
    Returns:
    --------
    metrics : dict
        urgent_wait_total, urgent_wait_weighted, elective_delay_total,
        elective_delayed_next_week, overtime_total, unproductive_total, etc.
    """
    
    # Constants
    week_length = sim.WEEK_LENGTH
    time_limit = (1 + max_reschedule_weeks) * week_length
    surgeons = list(work.surgeons)
    
    def get_rest_time(stype: str, role: str = 'main') -> int:
        if isinstance(rest_time, dict):
            val = rest_time.get(stype, 30)
            if isinstance(val, dict):
                # Role keys: 'main' or 'assistant'
                key = 'main' if role == 'main' else 'assistant'
                return val.get(key, 30)
            return int(val)
        return int(rest_time)

    # Build elective cases
    elective_cases: Dict[int, _ElectiveLW] = {}
    for pid, baseline_data in elective_baseline.items():
        scheduled_start = elective_overrides.scheduled_start_by_pid[pid]
        room = elective_overrides.room_by_pid[pid]
        team = elective_overrides.team_by_pid[pid]
        
        elective_cases[pid] = _ElectiveLW(
            pid=pid,
            surgery_type=baseline_data["surgery_type"],
            planned_start=baseline_data["planned_start"],
            scheduled_start=scheduled_start,
            priority_rank=priority_rank.get(pid, 10**9),
            room=room,
            main=team[0],
            assist1=team[1],
            assist2=team[2],
            duration=baseline_data["duration"],
            prep_time=baseline_data.get("prep_time", 30),
        )
    
    # Build urgent cases
    urgent_cases: List[_UrgentLW] = []
    for idx, (arr_time, stype) in enumerate(urgent_list):
        bucket = int(arr_time) // 60
        urgent_cases.append(_UrgentLW(
            uid=f"U{idx:03d}",
            surgery_type=stype,
            arrival_time=arr_time,
            arrival_bucket=bucket,
            rank=_get_rank(cap, stype),
        ))
    
    # Room/surgeon calendars
    room_busy: Dict[int, int] = {r: 0 for r in range(1, n_rooms + 1)}  # room -> busy_until
    surg_busy: Dict[str, int] = {s: 0 for s in surgeons}               # surgeon -> busy_until
    
    # Execution log
    log: List[Dict] = []
    
    # Simulation time
    now = 0
    max_time = time_limit + 7 * 24 * 60  # Extra buffer for late urgents
    
    # Main dispatch loop
    while now < max_time:
        # Check if any work left
        waiting_urgent = [u for u in urgent_cases if u.status == "waiting" and _ceil_minute(u.arrival_time) <= now]
        waiting_elective = [e for e in elective_cases.values() if e.status == "waiting"]
        
        if not waiting_urgent and not waiting_elective:
            # Advance to next event
            next_arr = min([_ceil_minute(u.arrival_time) for u in urgent_cases if u.status == "waiting"], default=None)
            next_elec = min([e.scheduled_start for e in waiting_elective if e.scheduled_start > now], default=None)
            next_free_room = min([t for t in room_busy.values() if t > now], default=None)
            next_free_surg = min([t for t in surg_busy.values() if t > now], default=None)
            
            candidates = [x for x in [next_arr, next_elec, next_free_room, next_free_surg] if x is not None]
            if not candidates:
                break
            now = min(candidates)
            continue
        
        # ==================================================================
        # URGENT DISPATCH FIRST (Priority: arrival_bucket, rank, arrival_time, uid)
        # ==================================================================
        if waiting_urgent:
            # Sort by priority
            waiting_urgent.sort(key=lambda u: (u.arrival_bucket, u.rank, u.arrival_time, u.uid))
            
            for u in waiting_urgent:
                # Find available room
                avail_rooms = [r for r in range(1, n_rooms + 1) if room_busy[r] <= now]
                if not avail_rooms:
                    break  # No room, try later
                
                # Try to find team
                team_candidates = []
                for main in cap.main_by_type.get(u.surgery_type, []):
                    if surg_busy.get(main, 0) > now or not work.on_duty_for_urgent(main, float(now)):
                        continue
                    for a1 in cap.a1_by_type.get(u.surgery_type, []):
                        if a1 == main or surg_busy.get(a1, 0) > now or not work.on_duty_for_urgent(a1, float(now)):
                            continue
                        # Try 3-person team
                        for a2 in cap.a2_by_type.get(u.surgery_type, []):
                            if a2 in (main, a1) or surg_busy.get(a2, 0) > now or not work.on_duty_for_urgent(a2, float(now)):
                                continue
                            team_candidates.append((main, a1, a2))
                        # 2-person team
                        team_candidates.append((main, a1, None))
                        break
                    if team_candidates:
                        break
                
                if not team_candidates:
                    continue  # No team, skip this urgent for now
                
                # Dispatch urgent
                team = team_candidates[0]
                room = avail_rooms[0]
                dur = sim.SURGERY_DURATION_MIN.get(u.surgery_type, 60)
                
                u.status = "executing"
                u.start_time = now
                u.room = room
                u.team = team
                u.complete_time = now + dur
                
                # Block resources
                # Block resources
                prep = sim.PREP_TIME_MIN.get(u.surgery_type, 30)
                room_busy[room] = now + dur + prep
                
                rt_main = get_rest_time(u.surgery_type, 'main')
                rt_asst = get_rest_time(u.surgery_type, 'assistant')
                
                surg_busy[team[0]] = now + dur + rt_main
                surg_busy[team[1]] = now + dur + rt_asst
                if team[2]:
                    surg_busy[team[2]] = now + dur + rt_asst
                
                rt_val = max(rt_main, rt_asst)
                
                # Log
                wait = now - u.arrival_time
                log.append({
                    "type": "URGENT",
                    "uid": u.uid,
                    "surgery_type": u.surgery_type,
                    "arrival": u.arrival_time,
                    "start": now,
                    "end": u.complete_time,
                    "end_surgeon": now + dur + rt_val,
                    "wait": wait,
                    "room": room,
                    "main": team[0],
                    "assist1": team[1],
                    "assist2": team[2],
                })
                
                u.status = "completed"
                break  # Dispatched one urgent, loop again
        
        # ==================================================================
        # ELECTIVE DISPATCH SECOND (Priority: scheduled_start, priority_rank, planned_start, pid)
        # ==================================================================
        else:
            # CRITICAL: Sort with priority_rank for permutation gene effect
            eligible = [e for e in waiting_elective if e.scheduled_start <= now]
            eligible.sort(key=lambda e: (e.scheduled_start, e.priority_rank, e.planned_start, e.pid))
            
            dispatched = False
            for e in eligible:
                # Check if can dispatch
                # 1. Room available?
                if room_busy.get(e.room, 0) > now:
                    continue
                
                # 2. Surgeons available?
                surgeons_needed = [e.main, e.assist1] + ([e.assist2] if e.assist2 else [])
                if any(surg_busy.get(s, 0) > now for s in surgeons_needed):
                    continue
                
                # 3. Admin hours check
                day_idx = now // sim.MINUTES_PER_DAY
                weekday = day_idx % 7
                time_in_day = now % sim.MINUTES_PER_DAY
                
                if weekday > 4:  # Weekend
                    continue
                if time_in_day < sim.ADMIN_SHIFT_START or time_in_day >= sim.ADMIN_SHIFT_END:
                    continue
                
                # 4. Must finish within admin hours same day
                if time_in_day + e.duration > sim.ADMIN_SHIFT_END:
                    # Need to reschedule
                    e.status = "delayed"
                    e.delayed_weeks += 1
                    continue
                
                # 5. On duty for elective?
                if not all(work.on_duty_for_elective(s, float(now)) for s in surgeons_needed):
                    continue
                
                # Dispatch elective
                e.status = "executing"
                e.actual_start = now
                
                # Block resources
                # Block resources
                room_busy[e.room] = now + e.duration + e.prep_time
                
                rt_main = get_rest_time(e.surgery_type, 'main')
                rt_asst = get_rest_time(e.surgery_type, 'assistant')
                
                surg_busy[e.main] = now + e.duration + rt_main
                surg_busy[e.assist1] = now + e.duration + rt_asst
                if e.assist2:
                    surg_busy[e.assist2] = now + e.duration + rt_asst
                
                rt_val = max(rt_main, rt_asst)
                
                # Log
                delay = now - e.planned_start
                log.append({
                    "type": "ELECTIVE",
                    "pid": e.pid,
                    "surgery_type": e.surgery_type,
                    "planned": e.planned_start,
                    "start": now,
                    "end": now + e.duration,
                    "end_surgeon": now + e.duration + rt_val,
                    "wait": max(0, delay),
                    "room": e.room,
                    "main": e.main,
                    "assist1": e.assist1,
                    "assist2": e.assist2,
                })
                
                e.status = "completed"
                dispatched = True
                break
            
            if not dispatched:
                now += 1
        
        now += 1
    
    # ==================================================================
    # COMPUTE METRICS
    # ==================================================================
    
    # Urgent metrics
    urgent_recs = [r for r in log if r["type"] == "URGENT"]
    urgent_wait_by_rank: Dict[int, List[float]] = {}
    for r in urgent_recs:
        rank = _get_rank(cap, r["surgery_type"])
        urgent_wait_by_rank.setdefault(rank, []).append(float(r["wait"]))
    
    max_rank = max(urgent_wait_by_rank.keys()) if urgent_wait_by_rank else 1
    def w_rank(rank: int) -> float:
        return float(max_rank - rank + 1)
    
    urgent_wait_total = sum(sum(ws) for ws in urgent_wait_by_rank.values())
    urgent_wait_weighted = sum(sum(w * w_rank(rank) for w in ws) for rank, ws in urgent_wait_by_rank.items())
    urgent_backlog_end = sum(1 for u in urgent_cases if u.status == "waiting")
    
    # Elective metrics
    elective_recs = [r for r in log if r["type"] == "ELECTIVE"]
    elective_delay_total = sum(max(0.0, float(r["wait"])) for r in elective_recs)
    delayed_next_week = sum(1 for e in elective_cases.values() if e.delayed_weeks >= 1)
    
    # Overtime/unproductive
    duty_map = {s: work.duty_intervals_abs(s, time_limit) for s in surgeons}
    busy_map = {s: [] for s in surgeons}
    for r in log:
        for s in [r["main"], r["assist1"]]:
            busy_map[s].append((int(r["start"]), int(r["end_surgeon"])))
        if r.get("assist2"):
            busy_map[r["assist2"]].append((int(r["start"]), int(r["end_surgeon"])))
    
    overtime_total = 0
    unproductive_total = 0
    for s in surgeons:
        duty = sim.merge_intervals(duty_map[s])
        busy = sim.merge_intervals(busy_map[s])
        busy_in_duty = sim.overlap_total(busy, duty)
        duty_total = sim.interval_total(duty)
        busy_total = sim.interval_total(busy)
        overtime = max(0, busy_total - busy_in_duty)
        unproductive = max(0, duty_total - busy_in_duty)
        overtime_total += overtime
        unproductive_total += unproductive
    
    return {
        "rooms": n_rooms,
        "urgent_arrived": len(urgent_cases),
        "urgent_started": len(urgent_recs),
        "urgent_backlog_end": urgent_backlog_end,
        "urgent_wait_total": float(urgent_wait_total),
        "urgent_wait_weighted": float(urgent_wait_weighted),
        "elective_started": len(elective_recs),
        "elective_delay_total": float(elective_delay_total),
        "elective_delayed_next_week": int(delayed_next_week),
        "overtime_total": int(overtime_total),
        "unproductive_total": int(unproductive_total),
        "simulation_log": log,  # Add simulation log for combined schedule export
    }
