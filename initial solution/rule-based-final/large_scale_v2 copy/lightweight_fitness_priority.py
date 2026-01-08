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
    status: str = "waiting"     # waiting/completed/delayed
    actual_start: Optional[int] = None
    delayed_weeks: int = 0


@dataclass
class _UrgentLW:
    """Lightweight urgent case for simulator."""
    uid: str
    surgery_type: str
    arrival_time: float
    arrival_bucket: int
    rank: int                   # From capability model (1=most urgent)
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


def _surgeon_num(code: str) -> int:
    """Extract numeric part from surgeon code 'S12' -> 12."""
    try:
        return int(str(code).strip().lstrip("S"))
    except Exception:
        return 10**9


def _choose_team(
    surgery_type: str,
    available_surgeons: Set[str],
    cap: sim.CapabilityModel,
    prefer_three: bool = True,
) -> Optional[Tuple[str, str, Optional[str]]]:
    """
    Deterministic urgent-team choice.
    Chooses the lowest-number feasible (main, a1, a2/None) from the available pool.
    """
    mains = sorted(set(cap.main_by_type.get(surgery_type, set())) & available_surgeons, key=_surgeon_num)
    a1s = sorted(set(cap.a1_by_type.get(surgery_type, set())) & available_surgeons, key=_surgeon_num)
    a2s = sorted(set(cap.a2_by_type.get(surgery_type, set())) & available_surgeons, key=_surgeon_num)

    if prefer_three:
        for m in mains:
            for a1 in a1s:
                if a1 == m:
                    continue
                for a2 in a2s:
                    if a2 in (m, a1):
                        continue
                    return (m, a1, a2)

    for m in mains:
        for a1 in a1s:
            if a1 == m:
                continue
            return (m, a1, None)

    return None


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
    Lightweight (fast) simulator used for GA fitness evaluation.

    Key behavior (aligned with rule_based_or_sim_v3 intent):
      - Dispatch URGENT first, potentially multiple per minute if resources allow.
      - Then dispatch ELECTIVE (admin time only), potentially multiple per minute.
      - No preemption: once a case starts, resources are blocked until completion.
      - If an urgent is waiting but cannot be dispatched (no room/team), elective dispatch still proceeds.
    """
    # Constants
    week_length = sim.WEEK_LENGTH
    time_limit = (1 + max_reschedule_weeks) * week_length
    surgeons = list(work.surgeons)

    def get_rest_time(stype: str, role: str = "main") -> int:
        if isinstance(rest_time, dict):
            val = rest_time.get(stype, 30)
            if isinstance(val, dict):
                key = "main" if role == "main" else "assistant"
                return int(val.get(key, 30))
            return int(val)
        return int(rest_time)

    # ------------------------------------------------------------------
    # Build elective cases (from baseline + planner overrides)
    # ------------------------------------------------------------------
    elective_cases: Dict[int, _ElectiveLW] = {}
    for pid, baseline_data in elective_baseline.items():
        scheduled_start = elective_overrides.scheduled_start_by_pid[pid]
        room = elective_overrides.room_by_pid[pid]
        team = elective_overrides.team_by_pid[pid]

        elective_cases[pid] = _ElectiveLW(
            pid=pid,
            surgery_type=baseline_data["surgery_type"],
            planned_start=int(baseline_data["planned_start"]),
            scheduled_start=int(scheduled_start),
            priority_rank=int(priority_rank.get(pid, 10**9)),
            room=int(room),
            main=str(team[0]),
            assist1=str(team[1]),
            assist2=str(team[2]) if team[2] else None,
            duration=int(baseline_data["duration"]),
            prep_time=int(baseline_data.get("prep_time", 30)),
        )

    # ------------------------------------------------------------------
    # Build urgent cases
    # ------------------------------------------------------------------
    urgent_cases: List[_UrgentLW] = []
    for idx, (arr_time, stype) in enumerate(urgent_list):
        # Keep the same definition as the "online" sim: hour-level buckets.
        bucket = int(math.floor(arr_time)) // 60
        urgent_cases.append(
            _UrgentLW(
                uid=f"U{idx:03d}",
                surgery_type=stype,
                arrival_time=float(arr_time),
                arrival_bucket=int(bucket),
                rank=_get_rank(cap, stype),
            )
        )

    # ------------------------------------------------------------------
    # Room/surgeon calendars (busy-until)
    # ------------------------------------------------------------------
    room_busy: Dict[int, int] = {r: 0 for r in range(1, n_rooms + 1)}  # room -> busy_until
    surg_busy: Dict[str, int] = {s: 0 for s in surgeons}               # surgeon -> busy_until

    # Execution log
    log: List[Dict] = []

    # Simulation time
    now = 0
    max_time = time_limit + 7 * 24 * 60  # Extra buffer for late urgents

    # ------------------------------------------------------------------
    # Main dispatch loop
    # ------------------------------------------------------------------
    while now < max_time:
        # Ready urgent = arrived and waiting
        ready_urgent = [u for u in urgent_cases if u.status == "waiting" and _ceil_minute(u.arrival_time) <= now]
        # Due elective = scheduled_start passed and still waiting
        due_elective = [e for e in elective_cases.values() if e.status == "waiting" and e.scheduled_start <= now]

        # If nothing can start at "now", jump forward to the next relevant event
        if not ready_urgent and not due_elective:
            waiting_urgent_future = [u for u in urgent_cases if u.status == "waiting" and _ceil_minute(u.arrival_time) > now]
            waiting_elective = [e for e in elective_cases.values() if e.status == "waiting"]

            next_arr = min((_ceil_minute(u.arrival_time) for u in waiting_urgent_future), default=None)
            next_elec = min((e.scheduled_start for e in waiting_elective if e.scheduled_start > now), default=None)

            candidates = [x for x in (next_arr, next_elec) if x is not None]
            if not candidates:
                # No remaining arrivals and no remaining elective -> stop
                break
            now = min(candidates)
            continue

        # Availability sets at current minute (before dispatch)
        free_rooms: Set[int] = {r for r in range(1, n_rooms + 1) if room_busy[r] <= now}
        free_surgeons: Set[str] = {s for s in surgeons if surg_busy.get(s, 0) <= now}

        # ==============================================================
        # 1) URGENT DISPATCH FIRST
        # ==============================================================

        if ready_urgent and free_rooms:
            ready_urgent.sort(key=lambda u: (u.arrival_bucket, u.rank, u.arrival_time, u.uid))
            available_urgent_surgeons = {s for s in free_surgeons if work.on_duty_for_urgent(s, float(now))}

            for u in ready_urgent:
                if not free_rooms:
                    break

                team = _choose_team(u.surgery_type, available_urgent_surgeons, cap, prefer_three=True)
                if team is None:
                    continue

                main, a1, a2 = team
                room = min(free_rooms)

                # Allocate resources at this minute
                free_rooms.remove(room)
                for s in (main, a1):
                    available_urgent_surgeons.discard(s)
                    free_surgeons.discard(s)
                if a2:
                    available_urgent_surgeons.discard(a2)
                    free_surgeons.discard(a2)

                # Durations
                dur = int(sim.SURGERY_DURATION_MIN.get(u.surgery_type, 60))
                prep = int(sim.PREP_TIME_MIN.get(u.surgery_type, 30))

                # Block resources
                room_busy[room] = now + dur + prep

                rt_main = get_rest_time(u.surgery_type, "main")
                rt_asst = get_rest_time(u.surgery_type, "assistant")

                surg_busy[main] = now + dur + rt_main
                surg_busy[a1] = now + dur + rt_asst
                if a2:
                    surg_busy[a2] = now + dur + rt_asst

                rt_val = max(rt_main, rt_asst)  # for log only

                # Log
                wait = float(now) - float(u.arrival_time)
                log.append(
                    {
                        "type": "URGENT",
                        "uid": u.uid,
                        "surgery_type": u.surgery_type,
                        "arrival": u.arrival_time,
                        "start": now,
                        "end": now + dur,
                        "end_surgeon": now + dur + rt_val,
                        "wait": wait,
                        "room": room,
                        "main": main,
                        "assist1": a1,
                        "assist2": a2,
                    }
                )

                # Mark as started (completed for lightweight)
                u.status = "completed"
                u.start_time = now
                u.room = room
                u.team = (main, a1, a2)
                u.complete_time = now + dur

        # ==============================================================
        # 2) ELECTIVE DISPATCH SECOND
        # ==============================================================

        eligible = [e for e in elective_cases.values() if e.status == "waiting" and e.scheduled_start <= now]
        eligible.sort(key=lambda e: (e.scheduled_start, e.priority_rank, e.planned_start, e.pid))

        if eligible:
            day_idx = now // sim.MINUTES_PER_DAY
            weekday = day_idx % 7
            time_in_day = now % sim.MINUTES_PER_DAY

            # Electives only within admin shift (Mon-Fri 08:00-16:00)
            in_admin_shift = (weekday <= 4) and (sim.ADMIN_SHIFT_START <= time_in_day < sim.ADMIN_SHIFT_END)

            if in_admin_shift:
                for e in eligible:
                    # Room available?
                    if e.room not in free_rooms:
                        continue

                    # Surgeons available?
                    surgeons_needed = [e.main, e.assist1] + ([e.assist2] if e.assist2 else [])
                    if not set(surgeons_needed).issubset(free_surgeons):
                        continue

                    # Must finish within admin hours same day
                    if time_in_day + e.duration > sim.ADMIN_SHIFT_END:
                        e.status = "delayed"
                        e.delayed_weeks += 1
                        continue

                    # On duty for elective?
                    if not all(work.on_duty_for_elective(s, float(now)) for s in surgeons_needed):
                        continue

                    # Dispatch elective
                    e.actual_start = now

                    # Allocate resources in this minute
                    free_rooms.remove(e.room)
                    for s in surgeons_needed:
                        free_surgeons.discard(s)

                    # Block resources
                    room_busy[e.room] = now + e.duration + e.prep_time

                    rt_main = get_rest_time(e.surgery_type, "main")
                    rt_asst = get_rest_time(e.surgery_type, "assistant")

                    surg_busy[e.main] = now + e.duration + rt_main
                    surg_busy[e.assist1] = now + e.duration + rt_asst
                    if e.assist2:
                        surg_busy[e.assist2] = now + e.duration + rt_asst

                    rt_val = max(rt_main, rt_asst)

                    # Log
                    delay = now - e.planned_start
                    log.append(
                        {
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
                        }
                    )

                    e.status = "completed"

        # Advance one minute
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
