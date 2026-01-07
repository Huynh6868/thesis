# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import bisect
import random
import json
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set, Union

import pandas as pd

# Import shared simulator utilities
import rule_based_or_sim_v3 as sim

# Mapping from short names (heuristic output) to full names (capability model)
SHORT_TO_FULL_SURGERY_TYPE = {
    "Adeno": "adenotonsillectomy",
    "Micro": "microlaryngoscopy",
    "Buccal": "buccal mucosa bioppsy",
    "Excision": "excision of the lymphadenopathy from the lumbar",
    "Septo": "septoplasty",
    "Modified": "modified radical mastoidectomy",
    "Thyroi": "thyroidectomy",
    "Rhino": "rhinoplasty",
    "Endos": "endoscopic sinus",
    "Sleep": "sleep apnea diagnosis test",
}

def normalize_surgery_type(stype: str) -> str:
    """Convert short surgery type name to full name for capability lookup."""
    # First check if it's already a full name
    if stype.lower() in [v.lower() for v in SHORT_TO_FULL_SURGERY_TYPE.values()]:
        return stype.lower()
    # Check short name mapping
    for short, full in SHORT_TO_FULL_SURGERY_TYPE.items():
        if stype.lower() == short.lower():
            return full
    # Return as-is (lowercase) if no mapping found
    return stype.lower()


# ==============================================================================
# Core Data Structures
# ==============================================================================

Team = Tuple[str, str, Optional[str]]  # (main, assist1, assist2_or_None)


@dataclass(frozen=True)
class ElectiveCase:
    """Immutable elective case representation for planner."""
    pid: int
    surgery_type: str
    planned_start: int          # absolute minutes since week start
    duration: int               # surgery duration in minutes
    prep_time: int              # prep/cleanup time in minutes
    baseline_room: int
    baseline_team: Team


@dataclass
class PlannerOverrides:
    """Output from planner: elective-only schedule overrides."""
    scheduled_start_by_pid: Dict[int, int]     # Planned start times from planner
    room_by_pid: Dict[int, int]                # Room assignments
    team_by_pid: Dict[int, Team]               # Team assignments


@dataclass
class GAIndividual:
    """Priority permutation chromosome."""
    priority_list: List[int]                   # Permutation of elective PIDs
    team_idx_by_pid: Dict[int, int]            # PID -> index in valid_teams_by_type[stype]
    room_by_pid: Optional[Dict[int, int]]      # PID -> room (optional, None = decoder chooses)
    
    fitness: Optional[float] = None
    metrics: Optional[dict] = None


# ==============================================================================
# Calendar Interval Helpers
# ==============================================================================

def _can_insert(intervals: List[Tuple[int, int]], start: int, end: int) -> bool:
    """
    Check if [start, end) can be inserted without overlap.
    
    intervals: sorted list of non-overlapping (s, e) tuples
    Returns True if [start, end) does not overlap with any existing interval.
    
    Uses bisect for O(log n) performance.
    """
    if not intervals:
        return True
    
    # Find position where start would be inserted
    idx = bisect.bisect_left(intervals, (start, start))
    
    # Check previous interval (if exists)
    if idx > 0:
        prev_start, prev_end = intervals[idx - 1]
        if prev_end > start:  # Overlaps with previous
            return False
    
    # Check next interval (if exists)
    if idx < len(intervals):
        next_start, next_end = intervals[idx]
        if end > next_start:  # Overlaps with next
            return False
    
    return True


def _insert(intervals: List[Tuple[int, int]], start: int, end: int) -> None:
    """
    Insert [start, end) into sorted interval list.
    
    Assumes _can_insert has already verified no overlap.
    Maintains sorted order.
    """
    bisect.insort(intervals, (start, end))


# ==============================================================================
# Valid Teams Generator
# ==============================================================================

def build_valid_teams_by_type(cap: sim.CapabilityModel) -> Dict[str, List[Team]]:
    """
    Build all valid surgical teams per surgery type based on capability model.
    
    Returns:
        Dict[surgery_type -> List[Team]]
        where Team = (main, assist1, assist2_or_None)
    """
    valid: Dict[str, List[Team]] = {}
    
    for stype in cap.main_by_type.keys():
        mains = list(cap.main_by_type.get(stype, []))
        a1s = list(cap.a1_by_type.get(stype, []))
        a2s = list(cap.a2_by_type.get(stype, []))
        
        teams: List[Team] = []
        
        # 3-person teams (preferred)
        for m in mains:
            for a1 in a1s:
                if a1 == m:
                    continue
                for a2 in a2s:
                    if a2 in (m, a1):
                        continue
                    teams.append((m, a1, a2))
        
        # 2-person fallback teams
        for m in mains:
            for a1 in a1s:
                if a1 == m:
                    continue
                teams.append((m, a1, None))
        
        valid[stype] = teams
    
    return valid


def build_team_to_idx_map(valid_teams_by_type: Dict[str, List[Team]]) -> Dict[str, Dict[Team, int]]:
    """
    Create reverse mapping: team tuple -> index for baseline identity chromosome.
    
    Critical for baseline reproduction: cannot assume baseline team = index 0.
    """
    team_to_idx: Dict[str, Dict[Team, int]] = {}
    for stype, teams in valid_teams_by_type.items():
        team_to_idx[stype] = {team: i for i, team in enumerate(teams)}
    return team_to_idx


# ==============================================================================
# Planner: First-Fit Elective Scheduler
# ==============================================================================

def build_elective_plan(
    elective_cases: Dict[int, ElectiveCase],
    priority_list: List[int],
    team_idx_by_pid: Dict[int, int],
    room_by_pid: Optional[Dict[int, int]],
    valid_teams_by_type: Dict[str, List[Team]],
    work: sim.WorkSchedule,
    n_rooms: int,
    rest_time: Union[int, Dict[str, int]],
    max_reschedule_weeks: int = 1,
    time_step: int = 5,
) -> PlannerOverrides:
    """
    Convert GA chromosome to feasible elective-only schedule.
    
    CRITICAL: This function does NOT schedule urgent cases.
    Urgent dispatch happens later in simulator.
    
    Algorithm:
    - For each PID in priority_list order:
      - Get desired team from valid_teams
      - Search forward from planned_start in time_step increments
      - Check: admin hours, room availability, surgeon availability, on-duty
      - First feasible slot → commit
      - No slot within horizon → mark delayed beyond time_limit
    
    Returns:
        PlannerOverrides with scheduled_start, room, team for each elective
    """
    week_length = sim.WEEK_LENGTH
    time_limit = (1 + max_reschedule_weeks) * week_length
    admin_start = sim.ADMIN_SHIFT_START
    admin_end = sim.ADMIN_SHIFT_END
    minutes_per_day = sim.MINUTES_PER_DAY
    
    # Initialize calendars
    room_cal: Dict[int, List[Tuple[int, int]]] = {r: [] for r in range(1, n_rooms + 1)}
    surg_cal: Dict[str, List[Tuple[int, int]]] = {}
    
    def ensure_surg(s: str):
        if s not in surg_cal:
            surg_cal[s] = []
    
    # Output
    scheduled_start: Dict[int, int] = {}
    assigned_room: Dict[int, int] = {}
    assigned_team: Dict[int, Team] = {}
    
    # Process in priority order
    for pid in priority_list:
        c = elective_cases[pid]
        teams = valid_teams_by_type.get(c.surgery_type, [])
        if not teams:
            raise ValueError(f"No valid teams for surgery type {c.surgery_type}")
        
        # Get team (use modulo to handle out-of-bounds indices)
        team_idx = team_idx_by_pid.get(pid, 0)
        team = teams[team_idx % len(teams)]
        main, a1, a2 = team
        
        ensure_surg(main)
        ensure_surg(a1)
        if a2:
            ensure_surg(a2)
        
        dur_room = c.duration + c.prep_time
        # Handle rest time (conservative max if dict)
        if isinstance(rest_time, dict):
            val = rest_time.get(c.surgery_type, 30)
            if isinstance(val, dict):
                rt_val = max(val.values())
            else:
                rt_val = int(val)
        else:
            rt_val = int(rest_time)
            
        dur_surg = c.duration + rt_val
        
        # Determine room candidates
        # Determine which rooms to try
        if room_by_pid is not None and pid in room_by_pid:
            # If room specified by GA, only try that room
            rooms_to_try = [room_by_pid[pid]]
        else:
            # If no room constraint, try all rooms (flexibility for GA)
            rooms_to_try = list(range(1, n_rooms + 1))
        
        # Search for feasible slot
        found = False
        search_start = c.planned_start
        search_end = time_limit
        
        t = search_start
        while t < search_end and not found:
            # Admin time constraint
            day_idx = t // minutes_per_day
            weekday = day_idx % 7  # 0=Mon, 6=Sun
            time_in_day = t % minutes_per_day
            
            # Must be weekday (Mon-Fri) and within admin hours
            if weekday > 4:  # Sat or Sun
                # Jump to Monday 08:00
                days_until_monday = (7 - weekday) % 7
                if days_until_monday == 0:
                    days_until_monday = 1
                t = (day_idx + days_until_monday) * minutes_per_day + admin_start
                continue
            
            if time_in_day < admin_start:
                t = day_idx * minutes_per_day + admin_start
                continue
            
            if time_in_day >= admin_end:
                # Jump to next day 08:00
                t = (day_idx + 1) * minutes_per_day + admin_start
                continue
            
            # Must finish within admin hours same day
            if time_in_day + dur_room > admin_end:
                t = (day_idx + 1) * minutes_per_day + admin_start
                continue
            
            # Check surgeon on-duty for elective
            if not all(work.on_duty_for_elective(s, float(t)) for s in [main, a1] + ([a2] if a2 else [])):
                t += time_step
                continue
            
            # Try each room candidate
            for r in rooms_to_try:
                s_room = t
                e_room = t + dur_room
                
                if not _can_insert(room_cal[r], s_room, e_room):
                    continue
                
                # Check surgeon calendars
                s_surg = t
                e_surg = t + dur_surg
                
                if not _can_insert(surg_cal[main], s_surg, e_surg):
                    continue
                if not _can_insert(surg_cal[a1], s_surg, e_surg):
                    continue
                if a2 and not _can_insert(surg_cal[a2], s_surg, e_surg):
                    continue
                
                # Feasible! Commit
                _insert(room_cal[r], s_room, e_room)
                _insert(surg_cal[main], s_surg, e_surg)
                _insert(surg_cal[a1], s_surg, e_surg)
                if a2:
                    _insert(surg_cal[a2], s_surg, e_surg)
                
                scheduled_start[pid] = t
                assigned_room[pid] = r
                assigned_team[pid] = team
                found = True
                break
            
            if not found:
                t += time_step
        
        # If no feasible slot found, mark as delayed beyond horizon
        if not found:
            scheduled_start[pid] = time_limit + 1  # Beyond time limit
            assigned_room[pid] = rooms_to_try[0]
            assigned_team[pid] = team
    
    return PlannerOverrides(scheduled_start, assigned_room, assigned_team)


# ==============================================================================
# GA Operators (Phase 5)
# ==============================================================================

def ox_crossover(parent1: List[int], parent2: List[int], rng: random.Random) -> Tuple[List[int], List[int]]:
    """
    Order Crossover (OX) for permutations.
    Preserves permutation property (no duplicates, no missing).
    """
    n = len(parent1)
    if n <= 2:
        return parent1[:], parent2[:]
    
    a, b = sorted(rng.sample(range(n), 2))
    
    def create_child(p1, p2):
        child = [None] * n
        child[a:b] = p1[a:b]
        segment_set = set(p1[a:b])
        fill = [x for x in p2 if x not in segment_set]
        fill_idx = 0
        for i in list(range(0, a)) + list(range(b, n)):
            child[i] = fill[fill_idx]
            fill_idx += 1
        return child
    
    return create_child(parent1, parent2), create_child(parent2, parent1)


def mutate_priority_swap(priority: List[int], rng: random.Random) -> None:
    """Swap two random positions."""
    if len(priority) < 2:
        return
    i, j = rng.sample(range(len(priority)), 2)
    priority[i], priority[j] = priority[j], priority[i]


def mutate_priority_insert(priority: List[int], rng: random.Random) -> None:
    """Remove element and insert at random position."""
    if len(priority) < 2:
        return
    i = rng.randrange(len(priority))
    j = rng.randrange(len(priority))
    elem = priority.pop(i)
    priority.insert(j, elem)


def mutate_team(team_idx_by_pid: Dict[int, int], elective_cases: Dict[int, ElectiveCase],
                valid_teams_by_type: Dict[str, List[Team]], rng: random.Random, rate: float = 0.3) -> None:
    """Flip team assignments for random subset of cases."""
    for pid in team_idx_by_pid.keys():
        if rng.random() < rate:
            stype = elective_cases[pid].surgery_type
            n_teams = len(valid_teams_by_type.get(stype, []))
            if n_teams > 0:
                team_idx_by_pid[pid] = rng.randrange(n_teams)


def mutate_room(ind: GAIndividual, n_rooms: int, rng: random.Random) -> None:
    """Mutate room assignment for a random elective.
    
    Args:
        ind: Individual to mutate
        n_rooms: Total number of available rooms
        rng: Random number generator
    """
    if not ind.room_by_pid:
        return
    
    # Pick random elective to change room
    pid = rng.choice(list(ind.room_by_pid.keys()))
    
    # Assign random room (1 to n_rooms)
    ind.room_by_pid[pid] = rng.randint(1, n_rooms)


def clone_ind(ind: GAIndividual) -> GAIndividual:
    """Deep copy individual."""
    return GAIndividual(
        priority_list=ind.priority_list[:],
        team_idx_by_pid=dict(ind.team_idx_by_pid),
        room_by_pid=dict(ind.room_by_pid) if ind.room_by_pid else None,
        fitness=ind.fitness,
        metrics=ind.metrics,
    )


def tournament_select(pop: List[GAIndividual], k: int, rng: random.Random) -> GAIndividual:
    """Tournament selection."""
    candidates = rng.sample(pop, k)
    candidates.sort(key=lambda ind: ind.fitness if ind.fitness is not None else float("inf"))
    return candidates[0]


# ==============================================================================
# Utility Functions
# ==============================================================================

def generate_urgent_list(mean_interarrival: float, seed: int, horizon_min: float = None) -> List[Tuple[float, str]]:
    """Generate fixed urgent arrival stream for scenario seed."""
    if horizon_min is None:
        horizon_min = sim.WEEK_LENGTH
    
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


# ==============================================================================
# Evaluation Function (Phase 6)
# ==============================================================================

def evaluate_individual(
    ind: GAIndividual,
    elective_cases: Dict[int, ElectiveCase],
    elective_baseline_data: Dict[int, Dict],
    urgent_list: List[Tuple[float, str]],
    valid_teams_by_type: Dict[str, List[Team]],
    work: sim.WorkSchedule,
    cap: sim.CapabilityModel,
    n_rooms: int,
    rest_time: Union[int, Dict[str, int]],
    max_reschedule_weeks: int,
    penalty_next_week: int,
    weights: Dict[str, float],
) -> Tuple[float, dict]:
    """
    Evaluate GA individual: planner → simulator → metrics → objective.
    
    Returns: (fitness, metrics_dict)
    """
    from lightweight_fitness_priority import simulate_elective_plan_with_urgent
    
    # Step 1: Planner (decode chromosome to elective overrides)
    overrides = build_elective_plan(
        elective_cases=elective_cases,
        priority_list=ind.priority_list,
        team_idx_by_pid=ind.team_idx_by_pid,
        room_by_pid=ind.room_by_pid,
        valid_teams_by_type=valid_teams_by_type,
        work=work,
        n_rooms=n_rooms,
        rest_time=rest_time,
        max_reschedule_weeks=max_reschedule_weeks,
    )
    
    # Step 2: Build priority_rank from permutation
    priority_rank = {pid: i for i, pid in enumerate(ind.priority_list)}
    
    # Step 3: Simulator (dispatch with urgent first, priority_rank tie-break)
    metrics = simulate_elective_plan_with_urgent(
        elective_overrides=overrides,
        elective_baseline=elective_baseline_data,
        priority_rank=priority_rank,
        urgent_list=urgent_list,
        work=work,
        cap=cap,
        n_rooms=n_rooms,
        rest_time=rest_time,
        max_reschedule_weeks=max_reschedule_weeks,
        penalty_next_week=penalty_next_week,
    )
    
    # Step 4: Compute weighted objective
    obj = (
        weights["urgent"] * metrics["urgent_wait_weighted"]
        + weights["elective_delay"] * metrics["elective_delay_total"]
        + weights["overtime"] * metrics["overtime_total"]
        + weights["next_week"] * (metrics["elective_delayed_next_week"] * penalty_next_week)
    )
    
    metrics["objective"] = float(obj)
    return float(obj), metrics


# ==============================================================================
# Main GA Loop (Phase 7)
# ==============================================================================

def run_ga_for_scenario(
    elective_input_df: pd.DataFrame,
    work_schedule_path: str,
    cap_rank_path: str,
    scenario_seed: int,
    mean_interarrival: float,
    rest_time: Union[int, Dict[str, int]],
    max_reschedule_weeks: int,
    penalty_next_week: int,
    pop_size: int,
    gens: int,
    cx_rate: float,
    mut_rate: float,
    tournament_k: int,
    weights: Dict[str, float],
    seed_ga: int,
) -> Tuple[pd.DataFrame, dict, dict]:
    """
    Run GA for single scenario seed.
    
    Returns: (best_schedule_df, best_metrics, baseline_metrics)
    """
    rng = random.Random(seed_ga)
    
    # Load work and capability
    work = sim.WorkSchedule(
        [sim.load_work_schedule_xlsx(work_schedule_path)],  # Wrap in list - WorkSchedule expects list of DataFrames
        [f"S{i}" for i in range(1, 17)]  # 16 surgeons for medium scale
    )
    cap = sim.load_cap_rank_xlsx(cap_rank_path)
    
    # Build valid teams
    valid_teams = build_valid_teams_by_type(cap)
    team_to_idx_map = build_team_to_idx_map(valid_teams)
    
    # Generate urgent list ONCE for this scenario
    urgent_list = generate_urgent_list(mean_interarrival, scenario_seed)
    print(f"\nScenario seed={scenario_seed}: Generated {len(urgent_list)} urgent arrivals")
    
    # Infer number of rooms
    n_rooms = int(elective_input_df["room"].max()) if len(elective_input_df) else 2
    
    # Build elective cases
    elective_cases: Dict[int, ElectiveCase] = {}
    elective_baseline_data: Dict[int, Dict] = {}
    
    for _, row in elective_input_df.iterrows():
        pid_raw = row["pid"]
        # Handle both "P20" and 20 formats
        if isinstance(pid_raw, str) and pid_raw.startswith("P"):
            pid = int(pid_raw[1:])
        else:
            pid = int(pid_raw)
        
        day = int(row["day"])
        planned_start = day * sim.MINUTES_PER_DAY + sim.hhmm_to_minutes(str(row["time_hhmm"]))
        stype_raw = str(row["surgery_type"])
        stype = normalize_surgery_type(stype_raw)  # Convert short name to full name
        duration = sim.SURGERY_DURATION_MIN.get(stype, 60)
        
        main = str(row.get("main", "S1"))
        a1 = str(row.get("assist1", "S2"))
        a2 = str(row.get("assist2", "")) if row.get("assist2") else None
        
        elective_cases[pid] = ElectiveCase(
            pid=pid,
            surgery_type=stype,
            planned_start=planned_start,
            duration=duration,
            prep_time=sim.PREP_TIME_MIN.get(stype, 30),  # Per-surgery-type prep time
            baseline_room=int(row["room"]),
            baseline_team=(main, a1, a2),
        )
        
        elective_baseline_data[pid] = {
            "surgery_type": stype,
            "planned_start": planned_start,
            "duration": duration,
            "prep_time": sim.PREP_TIME_MIN.get(stype, 30),
        }
    
    # Create baseline individual (identity chromosome)
    baseline_priority = sorted(elective_cases.keys(), key=lambda p: elective_cases[p].planned_start)
    baseline_team_idx = {}
    for pid, case in elective_cases.items():
        team = case.baseline_team
        stype = case.surgery_type
        if stype in team_to_idx_map and team in team_to_idx_map[stype]:
            baseline_team_idx[pid] = team_to_idx_map[stype][team]
        else:
            baseline_team_idx[pid] = 0  # Fallback
    
    baseline_room = {pid: case.baseline_room for pid, case in elective_cases.items()}
    
    baseline_ind = GAIndividual(
        priority_list=baseline_priority[:],
        team_idx_by_pid=dict(baseline_team_idx),
        room_by_pid=dict(baseline_room),
    )
    
    # Evaluate baseline
    print("Evaluating blockchain individual (identity chromosome)...")
    baseline_fitness, baseline_metrics = evaluate_individual(
        baseline_ind,
        elective_cases,
        elective_baseline_data,
        urgent_list,
        valid_teams,
        work,
        cap,
        n_rooms,
        rest_time,
        max_reschedule_weeks,
        penalty_next_week,
        weights,
    )
    baseline_ind.fitness = baseline_fitness
    baseline_ind.metrics = baseline_metrics
    
    print(f"Baseline fitness: {baseline_fitness:.1f}")
    print(f"  Urgent wait weighted: {baseline_metrics['urgent_wait_weighted']:.1f}")
    print(f"  Elective delay: {baseline_metrics['elective_delay_total']:.1f}")
    print(f"  Overtime: {baseline_metrics['overtime_total']}")
    
    # Initialize population (baseline + mutated copies)
    pop: List[GAIndividual] = [clone_ind(baseline_ind)]
    
    while len(pop) < pop_size:
        ind = clone_ind(baseline_ind)
        # Apply random mutations
        for _ in range(rng.randint(1, 3)):
            if rng.random() < 0.5:
                mutate_priority_swap(ind.priority_list, rng)
            else:
                mutate_priority_insert(ind.priority_list, rng)
        mutate_team(ind.team_idx_by_pid, elective_cases, valid_teams, rng, rate=0.3)
        pop.append(ind)
    
    # Evaluate initial population
    print(f"\nEvaluating initial population ({pop_size} individuals)...")
    cache: Dict[str, Tuple[float, dict]] = {}
    
    def get_key(ind: GAIndividual) -> str:
        """Simple hash for caching."""
        parts = [",".join(map(str, ind.priority_list))]
        parts.append("|".join(f"{pid}:{idx}" for pid, idx in sorted(ind.team_idx_by_pid.items())))
        return "#".join(parts)
    
    for ind in pop:
        if ind.fitness is None:
            key = get_key(ind)
            if key in cache:
                ind.fitness, ind.metrics = cache[key]
            else:
                ind.fitness, ind.metrics = evaluate_individual(
                    ind, elective_cases, elective_baseline_data, urgent_list,
                    valid_teams, work, cap, n_rooms, rest_time,
                    max_reschedule_weeks, penalty_next_week, weights
                )
                cache[key] = (ind.fitness, ind.metrics)
    
    # Track best
    best_ind = min(pop, key=lambda x: x.fitness)
    
    print(f"Initial best fitness: {best_ind.fitness:.1f}")
    
    # GA main loop
    print(f"\nStarting GA: {gens} generations...")
    
    for gen in range(1, gens + 1):
        # Elitism: keep top 2
        pop.sort(key=lambda x: x.fitness)
        new_pop = [clone_ind(pop[0]), clone_ind(pop[1])]
        
        # Breed
        while len(new_pop) < pop_size:
            p1 = tournament_select(pop, tournament_k, rng)
            p2 = tournament_select(pop, tournament_k, rng)
            
            c1, c2 = clone_ind(p1), clone_ind(p2)
            
            # Crossover
            if rng.random() < cx_rate:
                c1.priority_list, c2.priority_list = ox_crossover(
                    p1.priority_list, p2.priority_list, rng
                )
                # Uniform crossover for team indices
                for pid in c1.team_idx_by_pid:
                    if rng.random() < 0.5:
                        c1.team_idx_by_pid[pid], c2.team_idx_by_pid[pid] = \
                            c2.team_idx_by_pid[pid], c1.team_idx_by_pid[pid]
                # Uniform crossover for room indices
                for pid in c1.room_by_pid:
                    if rng.random() < 0.5:
                        c1.room_by_pid[pid], c2.room_by_pid[pid] = \
                            c2.room_by_pid[pid], c1.room_by_pid[pid]
            
            # Mutation
            if rng.random() < mut_rate:
                if rng.random() < 0.7:
                    mutate_priority_swap(c1.priority_list, rng)
                else:
                    mutate_priority_insert(c1.priority_list, rng)
                mutate_team(c1.team_idx_by_pid, elective_cases, valid_teams, rng, rate=0.2)
                if rng.random() < mut_rate / 2: # Lower rate for room mutation
                    mutate_room(c1, n_rooms, rng)
                c1.fitness = None
            
            if rng.random() < mut_rate:
                if rng.random() < 0.7:
                    mutate_priority_swap(c2.priority_list, rng)
                else:
                    mutate_priority_insert(c2.priority_list, rng)
                mutate_team(c2.team_idx_by_pid, elective_cases, valid_teams, rng, rate=0.2)
                c2.fitness = None
            
            new_pop.append(c1)
            if len(new_pop) < pop_size:
                new_pop.append(c2)
        
        pop = new_pop
        
        # Evaluate new individuals
        for ind in pop:
            if ind.fitness is None:
                key = get_key(ind)
                if key in cache:
                    ind.fitness, ind.metrics = cache[key]
                else:
                    ind.fitness, ind.metrics = evaluate_individual(
                        ind, elective_cases, elective_baseline_data, urgent_list,
                        valid_teams, work, cap, n_rooms, rest_time,
                        max_reschedule_weeks, penalty_next_week, weights
                    )
                    cache[key] = (ind.fitness, ind.metrics)
        
        # Update best
        current_best = min(pop, key=lambda x: x.fitness)
        if current_best.fitness < best_ind.fitness:
            best_ind = clone_ind(current_best)
        
        # Progress logging
        if gen % 10 == 0 or gen == 1 or gen == gens:
            improvement = ((baseline_fitness - best_ind.fitness) / baseline_fitness * 100) if baseline_fitness > 0 else 0
            print(f"Gen {gen}/{gens}: Best fitness = {best_ind.fitness:.1f} (improvement: {improvement:.2f}%)")
    
    print(f"\nGA complete. Final best fitness: {best_ind.fitness:.1f}")
    print(f"Baseline fitness: {baseline_fitness:.1f}")
    improvement_pct = ((baseline_fitness - best_ind.fitness) / baseline_fitness * 100) if baseline_fitness > 0 else 0
    print(f"Improvement: {improvement_pct:.2f}%")
    
    # Build combined schedule DataFrame (elective + urgent from simulation log)
    simulation_log = best_ind.metrics.get("simulation_log", [])
    
    schedule_rows = []
    
    # Add all cases from simulation log (both urgent and elective)
    for event in simulation_log:
        if event["type"] == "URGENT":
            # Urgent case
            start_abs = int(event["start"])
            day = start_abs // sim.MINUTES_PER_DAY
            time_hhmm = sim.minutes_to_hhmm(start_abs % sim.MINUTES_PER_DAY)
            
            schedule_rows.append({
                "patient_id": event["uid"],
                "patient_type": "URGENT",
                "surgery_type": event["surgery_type"],
                "arrival_time": event.get("arrival", 0),
                "wait_time": event.get("wait", 0),
                "day": day,
                "time_hhmm": time_hhmm,
                "actual_start": start_abs,
                "duration": int(event["end"]) - int(event["start"]),
                "room": event["room"],
                "main": event["main"],
                "assist1": event["assist1"],
                "assist2": event.get("assist2", ""),
            })
        else:  # ELECTIVE
            start_abs = int(event["start"])
            day = start_abs // sim.MINUTES_PER_DAY
            time_hhmm = sim.minutes_to_hhmm(start_abs % sim.MINUTES_PER_DAY)
            
            schedule_rows.append({
                "patient_id": f"E{event['pid']}",
                "patient_type": "ELECTIVE",
                "surgery_type": event["surgery_type"],
                "arrival_time": event.get("planned", 0),
                "wait_time": event.get("wait", 0),
                "day": day,
                "time_hhmm": time_hhmm,
                "actual_start": start_abs,
                "duration": int(event["end"]) - int(event["start"]),
                "room": event["room"],
                "main": event["main"],
                "assist1": event["assist1"],
                "assist2": event.get("assist2", ""),
            })
    
    # Sort by actual start time
    schedule_rows.sort(key=lambda x: x["actual_start"])
    
    best_schedule_df = pd.DataFrame(schedule_rows)
    
    return best_schedule_df, best_ind.metrics, baseline_metrics


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(description="GA Priority Permutation Optimizer")
    
    parser.add_argument("--work_schedule", default="lich_lam_viec_tuan1_med.xlsx")
    parser.add_argument("--cap_rank", default="Cap_Rank.xlsx")
    parser.add_argument("--elective_sched", default="medium_rulebased_output.xlsx")  # Use rule-based output
    
    parser.add_argument("--scenario_seed", type=int, default=1)
    parser.add_argument("--mean_urgent", type=float, default=None)
    
    parser.add_argument("--pop", type=int, default=50)
    parser.add_argument("--gens", type=int, default=50)
    parser.add_argument("--cx", type=float, default=0.7)
    parser.add_argument("--mut", type=float, default=0.3)
    parser.add_argument("--tourn", type=int, default=3)
    parser.add_argument("--ga_seed", type=int, default=42)
    
    parser.add_argument("--rest_time", type=int, default=None)
    parser.add_argument("--max_weeks", type=int, default=1)
    parser.add_argument("--penalty_next_week", type=int, default=sim.DEFAULT_PENALTY_DELAY_NEXT_WEEK)
    
    parser.add_argument("--w_urgent", type=float, default=1.0)
    parser.add_argument("--w_elective_delay", type=float, default=1.0)
    parser.add_argument("--w_overtime", type=float, default=1.0)
    parser.add_argument("--w_next_week", type=float, default=1.0)
    
    args = parser.parse_args()
    # Load urgent parameter from Excel based on scale
    if args.mean_urgent is None:
        args.mean_urgent = sim.load_urgent_param_from_excel(args.cap_rank, 'Medium scale')
    print(f"Using mean_interarrival_urgent: {args.mean_urgent} (Medium scale)")
    
    # Load rest time (dict or int)
    if args.rest_time is None:
        rest_time_val = sim.load_rest_time_map(args.cap_rank)
        print("Using rest_time map loaded from Cap_Rank.xlsx")
    else:
        rest_time_val = args.rest_time
        print(f"Using fixed rest_time: {rest_time_val} min")

    
    # Load elective schedule
    elective_df = sim.load_elective_schedule_xlsx(args.elective_sched, return_df=True)
    # Filter for ELECTIVE patients only (if using combined output from Rule-Based Sim)
    if "patient_type" in elective_df.columns:
        print(f"Filtering for ELECTIVE patients. Total rows before: {len(elective_df)}")
        elective_df = elective_df[elective_df["patient_type"] == "ELECTIVE"].copy()
        print(f"Total rows after filter: {len(elective_df)}")
    
    weights = {
        "urgent": args.w_urgent,
        "elective_delay": args.w_elective_delay,
        "overtime": args.w_overtime,
        "next_week": args.w_next_week,
    }
    
    print("=" * 80)
    print("GA PRIORITY PERMUTATION + TEAM SWAP OPTIMIZER")
    print("=" * 80)
    
    best_schedule, best_metrics, baseline_metrics = run_ga_for_scenario(
        elective_input_df=elective_df,
        work_schedule_path=args.work_schedule,
        cap_rank_path=args.cap_rank,
        scenario_seed=args.scenario_seed,
        mean_interarrival=args.mean_urgent,
        rest_time=rest_time_val,
        max_reschedule_weeks=args.max_weeks,
        penalty_next_week=args.penalty_next_week,
        pop_size=args.pop,
        gens=args.gens,
        cx_rate=args.cx,
        mut_rate=args.mut,
        tournament_k=args.tourn,
        weights=weights,
        seed_ga=args.ga_seed,
    )
    
    # Save results
    out_sched = f"combined_schedule_seed{args.scenario_seed}.xlsx"
    out_cmp = f"comparison_priority_seed{args.scenario_seed}.json"
    
    best_schedule.to_excel(out_sched, index=False)
    
    payload = {
        "scenario_seed": args.scenario_seed,
        "baseline": baseline_metrics,
        "ga_best": best_metrics,
        "improvement": {
            "urgent_wait_weighted": baseline_metrics["urgent_wait_weighted"] - best_metrics["urgent_wait_weighted"],
            "elective_delay_total": baseline_metrics["elective_delay_total"] - best_metrics["elective_delay_total"],
            "overtime_total": baseline_metrics["overtime_total"] - best_metrics["overtime_total"],
        }
    }
    
    with open(out_cmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print(f"RESULTS SAVED: {out_sched}, {out_cmp}")
    print("=" * 80)


if __name__ == "__main__":
    main()

