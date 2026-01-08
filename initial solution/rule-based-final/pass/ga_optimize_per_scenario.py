# -*- coding: utf-8 -*-
"""
GA post-optimizer (per-scenario) for weekly elective schedule.

Design goal (thesis / offline):
- For each urgent scenario (seed), run:
    1) Baseline simulation using the elective schedule you already have (from CPLEX/rule-based input file).
    2) GA to propose a NEW elective baseline schedule (reorder + allow room changes),
       evaluated under the SAME urgent scenario.
    3) Compare KPIs: urgent waiting (weighted by priority), elective delay, overtime, pushed-to-next-week.

Important modeling notes:
- Urgent arrivals are unknown in reality. This GA is *offline* and optimizes for the realized scenario
  (or for a fixed scenario defined by a random seed). That is acceptable for thesis "improvement heuristic".
- Elective day is kept fixed by default (Mon-Fri). GA can change room and sequence within each day.

Requirements:
- simpy, pandas, openpyxl
- Your existing simulator file: rule_based_or_sim_v3.py (same folder)

Run example:
    python ga_optimize_per_scenario.py --scenario_seed 1 --gens 80 --pop 60

Outputs:
- best_schedule_seed<seed>.xlsx
- comparison_seed<seed>.json
"""

from __future__ import annotations

import argparse
import random
import math
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from multiprocessing import Pool, cpu_count
import pandas as pd

# --- import your current simulator (v3)
# This import requires simpy, because your simulator imports simpy at module import-time.
import rule_based_or_sim_v3 as sim

# --- import lightweight fitness for GA optimization
import lightweight_fitness as lf


# ----------------------------
# Urgent scenario generator
# ----------------------------
def generate_urgent_list(seed: int, mean_interarrival: float, horizon_min: int) -> List[Tuple[float, str]]:
    """
    Deterministic urgent arrivals for a scenario.
    - arrival times follow expovariate(mean_interarrival)
    - surgery_type chosen uniformly from sim.SURGERY_DURATION_MIN keys
    """
    rnd = random.Random(seed)
    t = 0.0
    types = list(sim.SURGERY_DURATION_MIN.keys())
    out: List[Tuple[float, str]] = []
    while True:
        inter = rnd.expovariate(1.0 / mean_interarrival)
        t += inter
        if t >= horizon_min:
            break
        out.append((t, rnd.choice(types)))
    return out


# ----------------------------
# Chromosome encoding
# ----------------------------
# We keep DAY fixed (from the input elective schedule).
# For each day d:
#   - a permutation P_d of the elective cases belonging to day d
#   - a room assignment R(case) in {1..K}
#
# Decoder:
#   For each day:
#       build room lists by scanning P_d and appending case -> R(case)
#       schedule each room list in order with a list-scheduling algorithm that respects:
#           - room availability (duration + prep)
#           - surgeon availability (duration + rest)
#       planned start times are produced in admin hours (08:00-16:00) when possible.
#
# Mutation:
#   - swap two positions in P_d
#   - flip room assignment of one case (move between rooms)
#
# Crossover:
#   - Order crossover (OX) for P_d
#   - uniform crossover for room assignment


@dataclass
class GAIndividual:
    perms_by_day: Dict[int, List[str]]         # day -> list of pid
    room_by_pid: Dict[str, int]                # pid -> room
    fitness: Optional[float] = None
    metrics: Optional[dict] = None


def minutes_to_hhmm_in_day(min_in_day: int) -> str:
    h = int(min_in_day // 60)
    m = int(min_in_day % 60)
    return f"{h:02d}:{m:02d}"


def decode_to_schedule_df(
    base_df: pd.DataFrame,
    ind: GAIndividual,
    K: int,
    rest_time: int,
    allow_after_admin: bool = False,
) -> pd.DataFrame:
    """
    Build a new elective schedule DataFrame with columns:
        pid, surgery_type, day, time_hhmm, room, main, assist1, assist2
    using the individual's permutation + room assignment.

    Scheduling policy inside decoder:
    - Maintain within-room order as given by (P_d + room assignment).
    - Compute earliest feasible start for next case in each room as:
        max(room_ready_time, each-surgeon_ready_time, ADMIN_SHIFT_START).
    - If the computed start would push the room beyond ADMIN_SHIFT_END, we still output a time,
      but it will be outside admin hours. The simulator will reschedule those cases.
      If allow_after_admin=False, we clamp to ADMIN_SHIFT_END (so simulator must reschedule).
    """
    # Build lookup
    base = base_df.copy()
    base["pid"] = base["pid"].astype(str)
    by_pid = base.set_index("pid").to_dict(orient="index")

    admin_start = sim.ADMIN_SHIFT_START
    admin_end = sim.ADMIN_SHIFT_END

    # Precompute duration/prep per pid
    dur = {pid: int(sim.SURGERY_DURATION_MIN[by_pid[pid]["surgery_type"]]) for pid in by_pid.keys()}
    prep = {pid: int(sim.PREP_TIME_MIN[by_pid[pid]["surgery_type"]]) for pid in by_pid.keys()}

    # Output rows will be copied from base but with new day/time_hhmm/room
    out_rows = []

    # Surgeon availability tracker per day (minutes-in-day)
    for d, perm in ind.perms_by_day.items():
        # room lists in the order implied by perm and room assignment
        room_lists: Dict[int, List[str]] = {r: [] for r in range(1, K + 1)}
        for pid in perm:
            r = ind.room_by_pid.get(pid, int(by_pid[pid]["room"]))
            room_lists[r].append(pid)

        # Pointers and ready times
        idx = {r: 0 for r in range(1, K + 1)}
        room_ready = {r: admin_start for r in range(1, K + 1)}
        surg_ready: Dict[str, int] = {}  # surgeon -> minute in day

        # Helper: get team surgeons for pid
        def team(pid: str) -> List[str]:
            rec = by_pid[pid]
            t = [str(rec["main"]), str(rec["assist1"])]
            a2 = str(rec.get("assist2", "")).strip()
            if a2 and a2.lower() != "nan":
                t.append(a2)
            return t

        # We'll schedule by repeatedly selecting the room whose next job can start earliest
        scheduled_pid: List[str] = []
        planned_start_in_day: Dict[str, int] = {}
        planned_room: Dict[str, int] = {}

        remaining = sum(len(room_lists[r]) for r in room_lists)
        while remaining > 0:
            # collect candidates (next unscheduled in each room)
            candidates = []
            for r in range(1, K + 1):
                if idx[r] >= len(room_lists[r]):
                    continue
                pid = room_lists[r][idx[r]]
                earliest = room_ready[r]
                for sname in team(pid):
                    earliest = max(earliest, surg_ready.get(sname, admin_start))
                earliest = max(earliest, admin_start)
                candidates.append((earliest, r, pid))

            # pick the smallest earliest start; tie-break by earliest then room
            candidates.sort(key=lambda x: (x[0], x[1]))
            earliest, r, pid = candidates[0]

            # assign
            planned_start_in_day[pid] = earliest
            planned_room[pid] = r
            scheduled_pid.append(pid)

            # update ready times
            room_ready[r] = earliest + dur[pid] + prep[pid]
            for sname in team(pid):
                surg_ready[sname] = earliest + dur[pid] + rest_time

            idx[r] += 1
            remaining -= 1

        # Produce output rows
        for pid in scheduled_pid:
            base_rec = by_pid[pid]
            start_min = planned_start_in_day[pid]
            # If outside admin, either keep or clamp
            if not allow_after_admin and start_min > admin_end:
                start_min = admin_end
            out_rows.append({
                "pid": pid,
                "surgery_type": base_rec["surgery_type"],
                "day": int(d),
                "time_hhmm": minutes_to_hhmm_in_day(start_min),
                "room": int(planned_room[pid]),
                "main": base_rec["main"],
                "assist1": base_rec["assist1"],
                "assist2": base_rec.get("assist2", ""),
            })

    out_df = pd.DataFrame(out_rows)
    # Keep same column order
    cols = ["pid", "surgery_type", "day", "time_hhmm", "room", "main", "assist1", "assist2"]
    out_df = out_df[cols]
    return out_df


# ----------------------------
# Simulation wrapper (fixed urgent list)
# ----------------------------
def simulate_fixed_urgent(
    work_schedule_path: str,
    cap_rank_path: str,
    elective_df: pd.DataFrame,
    urgent_list: List[Tuple[float, str]],
    rest_time: int,
    max_reschedule_weeks: int,
    penalty_next_week: int,
    seed: int,
    quiet: bool = True,
) -> dict:
    """
    Simulation wrapper that matches the scheduling logic in rule_based_or_sim_v3.py,
    but uses a *fixed* urgent arrival list (scenario) instead of drawing expovariate arrivals.

    Returns a metrics dict used by GA.
    """
    import simpy  # runtime dependency

    rnd = random.Random(seed)

    # ---- Load inputs (same format as v3)
    df_work = sim.load_work_schedule_xlsx(work_schedule_path)
    surgeons = [f"S{i}" for i in range(1, 13)]
    work = sim.WorkSchedule(df_work, surgeons)
    cap = sim.load_cap_rank_xlsx(cap_rank_path)

    # ---- Build ElectiveCase dict from elective_df
    elective_df = elective_df.copy()
    elective_df["pid"] = elective_df["pid"].astype(str)

    elective_cases: Dict[str, sim.ElectiveCase] = {}
    for _, row in elective_df.iterrows():
        pid = str(row["pid"])
        stype = str(row["surgery_type"])
        day = int(row["day"])
        hhmm = str(row["time_hhmm"])
        room = int(row["room"])
        main = str(row["main"])
        a1 = str(row["assist1"])
        a2 = str(row.get("assist2", "")).strip()
        if a2.lower() == "nan":
            a2 = ""
        planned_start = day * sim.MINUTES_PER_DAY + sim.hhmm_to_minutes(hhmm)

        elective_cases[pid] = sim.ElectiveCase(
            pid=pid,
            surgery_type=stype,
            planned_start=int(planned_start),
            scheduled_start=int(planned_start),
            room=room,
            main=main,
            assist1=a1,
            assist2=a2,
            status="waiting",
            delayed_weeks=0,
        )

    # ---- Fixed urgent arrivals generator -> urgent_cases list
    urgent_cases: List[sim.UrgentCase] = []
    urgent_stream = sorted([(float(t), str(st)) for t, st in urgent_list], key=lambda x: x[0])

    # ---- Resources
    n_rooms = int(max(elective_df["room"].max(), 2))
    env = simpy.Environment()
    room_res = {r: simpy.Resource(env, capacity=1) for r in range(1, n_rooms + 1)}
    surg_res = {s: simpy.Resource(env, capacity=1) for s in surgeons}
    rooms = list(room_res.keys())

    # ---- Logs / stats (mirrors v3 where useful)
    log: List[dict] = []
    active_counter = {"active": 0}
    stats = {
        "urgent_arrived": 0,
        "urgent_started": 0,
        "elective_started": 0,
        "elective_rescheduled": [],
        "urgent_backlog_end": 0,
    }

    # ---- Urgent generator with fixed arrival list
    def urgent_generator_fixed():
        nonlocal urgent_cases
        for (t, stype) in urgent_stream:
            if t < env.now:
                continue
            yield env.timeout(t - env.now)
            stats["urgent_arrived"] += 1
            uid = f"U{stats['urgent_arrived']:04d}"
            urgent_cases.append(sim.UrgentCase(
                uid=uid,
                surgery_type=stype,
                arrival_time=float(t),
                arrival_bucket=int(t),
                rank=int(cap.rank_by_type.get(stype, 999)),
                status="waiting",
            ))

    # ---- Scheduler: copied from v3 with urgent arrivals fixed
    def scheduler():
        arrival_horizon = sim.WEEK_LENGTH  # urgents are only generated within scenario horizon
        time_limit = (1 + max_reschedule_weeks) * sim.WEEK_LENGTH

        while True:
            now = float(env.now)
            now_int = int(now)

            # Stop: after horizon, no active work, no waiting urgent, and all electives completed
            all_elective_done = all(c.status == "completed" for c in elective_cases.values())
            waiting_urgent = [u for u in urgent_cases if u.status == "waiting" and u.arrival_time <= now]

            if (now >= arrival_horizon) and (active_counter["active"] == 0) and (not waiting_urgent) and all_elective_done:
                break
            if now >= time_limit:
                break

            # Free rooms/surgeons (count==0 means no current users; we also avoid queueing)
            free_rooms = {r for r in rooms if room_res[r].count == 0}
            free_surgeons = {s for s in surgeons if surg_res[s].count == 0}

            # --------------------
            # URGENT DISPATCH
            # --------------------
            # Filter surgeons who are on duty for urgent at this time
            available_urgent_surgeons = {s for s in free_surgeons if work.on_duty_for_urgent(s, now)}

            # Sort waiting urgent by (arrival_bucket, rank, arrival_time, uid)
            waiting_urgent_sorted = sorted(
                [u for u in urgent_cases if u.status == "waiting" and u.arrival_time <= now],
                key=lambda u: (u.arrival_bucket, u.rank, u.arrival_time, u.uid),
            )

            for u in waiting_urgent_sorted:
                if not free_rooms:
                    break

                # choose a room (lowest id)
                room = min(free_rooms)

                # Prefer 3-person team; fallback to 2-person team if needed
                team_choice = sim.choose_urgent_team(u.surgery_type, available_urgent_surgeons, cap, prefer_three=True)
                if team_choice is None:
                    team_choice = sim.choose_urgent_team(u.surgery_type, available_urgent_surgeons, cap, prefer_three=False)
                if team_choice is None:
                    continue

                main, a1, a2, team_size = team_choice

                # reserve locally (avoid assigning same resource twice in this tick)
                free_rooms.remove(room)
                for sname in (main, a1):
                    available_urgent_surgeons.discard(sname)
                    free_surgeons.discard(sname)
                if a2 is not None:
                    available_urgent_surgeons.discard(a2)
                    free_surgeons.discard(a2)

                u.status = "executing"
                stats["urgent_started"] += 1

                env.process(sim.execute_surgery(
                    env=env,
                    pid=u.uid,
                    surgery_type=u.surgery_type,
                    is_urgent=True,
                    room=room,
                    team=(main, a1, a2),
                    room_res=room_res,
                    surg_res=surg_res,
                    rest_time=rest_time,
                    log=log,
                    active_counter=active_counter,
                    arrival_time=u.arrival_time,
                    start_time=now,
                    case_obj=u,
                ))

            # --------------------
            # ELECTIVE DISPATCH
            # --------------------
            # Eligible electives: waiting and scheduled_start <= now (integer minutes)
            waiting_e = [c for c in elective_cases.values() if c.status == "waiting" and c.scheduled_start <= now_int]
            waiting_e.sort(key=lambda c: (c.scheduled_start, c.pid))

            for c in waiting_e:
                # If not admin time now -> reschedule
                if not sim.is_admin_time(now_int):
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is not None and int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": int(new_start), "reason": "Not admin time"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Room availability
                if c.room not in free_rooms:
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is not None and int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": int(new_start), "reason": "Room busy"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                needed = {c.main, c.assist1}
                if c.assist2:
                    needed.add(c.assist2)

                # Surgeons on duty for elective
                if any(not work.on_duty_for_elective(s, now) for s in needed):
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is not None and int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": int(new_start), "reason": "Surgeon off-duty"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Surgeons availability
                if not needed.issubset(free_surgeons):
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is not None and int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": int(new_start), "reason": "Surgeon busy"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Duration fit inside admin hours (use the same rule as v3)
                dur = int(sim.SURGERY_DURATION_MIN[c.surgery_type])
                prep = int(sim.PREP_TIME_MIN[c.surgery_type])
                end_room = now_int + dur + prep
                end_in_day = end_room % sim.MINUTES_PER_DAY
                if end_in_day > sim.ADMIN_SHIFT_END:
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is not None and int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": int(new_start), "reason": "Would exceed admin hours"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Start elective
                free_rooms.remove(c.room)
                free_surgeons -= needed

                c.status = "executing"
                stats["elective_started"] += 1

                env.process(sim.execute_surgery(
                    env=env,
                    pid=c.pid,
                    surgery_type=c.surgery_type,
                    is_urgent=False,
                    room=c.room,
                    team=(c.main, c.assist1, c.assist2 if c.assist2 else None),
                    room_res=room_res,
                    surg_res=surg_res,
                    rest_time=rest_time,
                    log=log,
                    active_counter=active_counter,
                    arrival_time=float(c.planned_start),
                    start_time=float(now_int),
                    case_obj=c,
                ))

            yield env.timeout(1)

        # backlog
        stats["urgent_backlog_end"] = sum(1 for u in urgent_cases if u.status == "waiting")

    env.process(urgent_generator_fixed())
    env.process(scheduler())
    env.run()

    # --------------------
    # KPI calculation (same as v3, but return dict)
    # --------------------
    urgent_recs = [r for r in log if r["type"] == "URGENT"]
    elective_recs = [r for r in log if r["type"] == "ELECTIVE"]

    urgent_wait_by_rank: Dict[int, List[float]] = {}
    for r in urgent_recs:
        rank = int(cap.rank_by_type.get(r["surgery_type"], 999))
        urgent_wait_by_rank.setdefault(rank, []).append(float(r["wait"]))

    delayed_next_week = sum(1 for c in elective_cases.values() if c.delayed_weeks >= 1)

    # weighted urgent waiting: smaller rank => higher priority => bigger weight
    max_rank = max(urgent_wait_by_rank.keys()) if urgent_wait_by_rank else 1
    def w_rank(rank: int) -> float:
        return float(max_rank - rank + 1)

    urgent_wait_total = sum(sum(ws) for ws in urgent_wait_by_rank.values())
    urgent_wait_weighted = sum(sum(w * w_rank(rank) for w in ws) for rank, ws in urgent_wait_by_rank.items())

    elective_delay_total = sum(max(0.0, float(r["wait"])) for r in elective_recs)

    # overtime/unproductive for surgeons
    time_limit = (1 + max_reschedule_weeks) * sim.WEEK_LENGTH
    duty_map = {s: work.duty_intervals_abs(s, time_limit) for s in surgeons}
    busy_map = {s: [] for s in surgeons}
    for r in log:
        for s in [r["main"], r["assist1"]]:
            busy_map[s].append((int(r["start"]), int(r["end_surgeon"])))
        if r.get("assist2") is not None:
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

    metrics = {
        "rooms": n_rooms,
        "urgent_arrived": stats["urgent_arrived"],
        "urgent_started": stats["urgent_started"],
        "urgent_backlog_end": stats["urgent_backlog_end"],
        "urgent_wait_total": float(urgent_wait_total),
        "urgent_wait_weighted": float(urgent_wait_weighted),
        "elective_started": stats["elective_started"],
        "elective_delay_total": float(elective_delay_total),
        "elective_delayed_next_week": int(delayed_next_week),
        "overtime_total": int(overtime_total),
        "unproductive_total": int(unproductive_total),
        "elective_rescheduled_count": int(len(stats["elective_rescheduled"])),
    }
    return metrics


# ----------------------------
# GA operators
# ----------------------------
def order_crossover(parent1: List[str], parent2: List[str], rnd: random.Random) -> Tuple[List[str], List[str]]:
    """Order crossover (OX) for permutations."""
    n = len(parent1)
    if n <= 2:
        return parent1[:], parent2[:]
    a, b = sorted(rnd.sample(range(n), 2))
    def ox(p1, p2):
        child = [None]*n
        child[a:b] = p1[a:b]
        fill = [x for x in p2 if x not in child[a:b]]
        j = 0
        for i in list(range(0,a)) + list(range(b,n)):
            child[i] = fill[j]; j += 1
        return child
    return ox(parent1, parent2), ox(parent2, parent1)


def tournament_select(pop: List[GAIndividual], k: int, rnd: random.Random) -> GAIndividual:
    cand = rnd.sample(pop, k)
    cand.sort(key=lambda ind: ind.fitness if ind.fitness is not None else float("inf"))
    return cand[0]


def clone_ind(ind: GAIndividual) -> GAIndividual:
    return GAIndividual(
        perms_by_day={d: lst[:] for d, lst in ind.perms_by_day.items()},
        room_by_pid=dict(ind.room_by_pid),
        fitness=ind.fitness,
        metrics=ind.metrics,
    )


def mutate(ind: GAIndividual, day_cases: Dict[int, List[str]], K: int, rnd: random.Random,
           p_swap: float = 0.5, p_room: float = 0.5) -> None:
    # swap mutation in a random day
    if rnd.random() < p_swap:
        d = rnd.choice(list(day_cases.keys()))
        perm = ind.perms_by_day[d]
        if len(perm) >= 2:
            i, j = rnd.sample(range(len(perm)), 2)
            perm[i], perm[j] = perm[j], perm[i]
    # room flip mutation
    if rnd.random() < p_room:
        pid = rnd.choice(list(ind.room_by_pid.keys()))
        current = ind.room_by_pid[pid]
        choices = [r for r in range(1, K+1) if r != current]
        if choices:
            ind.room_by_pid[pid] = rnd.choice(choices)


def crossover(p1: GAIndividual, p2: GAIndividual, day_cases: Dict[int, List[str]], rnd: random.Random) -> Tuple[GAIndividual, GAIndividual]:
    c1 = clone_ind(p1)
    c2 = clone_ind(p2)

    # permutation crossover per day
    for d in day_cases.keys():
        child_perm1, child_perm2 = order_crossover(p1.perms_by_day[d], p2.perms_by_day[d], rnd)
        c1.perms_by_day[d] = child_perm1
        c2.perms_by_day[d] = child_perm2

    # uniform crossover for room assignment
    for pid in c1.room_by_pid.keys():
        if rnd.random() < 0.5:
            c1.room_by_pid[pid], c2.room_by_pid[pid] = c2.room_by_pid[pid], c1.room_by_pid[pid]

    return c1, c2


# ----------------------------
# Main GA loop (per scenario)
# ----------------------------
def run_ga_for_scenario(
    base_df: pd.DataFrame,
    work_schedule_path: str,
    cap_rank_path: str,
    scenario_seed: int,
    mean_interarrival: float,
    rest_time: int,
    max_reschedule_weeks: int,
    penalty_next_week: int,
    pop_size: int,
    gens: int,
    cx_rate: float,
    mut_rate: float,
    tournament_k: int,
    w_urgent: float,
    w_elective_delay: float,
    w_overtime: float,
    w_next_week: float,
    w_shift: float,
    seed_ga: int,
) -> Tuple[pd.DataFrame, dict, dict]:
    """
    Returns: best_schedule_df, best_metrics, baseline_metrics
    """
    rnd = random.Random(seed_ga)

    # infer rooms K
    K = int(max(base_df["room"].max(), 2))

    # day partition
    base_df = base_df.copy()
    base_df["pid"] = base_df["pid"].astype(str)
    day_cases: Dict[int, List[str]] = {d: base_df[base_df["day"] == d]["pid"].tolist() for d in sorted(base_df["day"].unique())}

    # baseline planned start (absolute minutes) for shift penalty
    base_planned_abs = {
        str(r.pid): int(r.day) * sim.MINUTES_PER_DAY + sim.hhmm_to_minutes(str(r.time_hhmm))
        for r in base_df.itertuples(index=False)
    }

    # urgent list for this scenario
    urgent_list = generate_urgent_list(seed=scenario_seed, mean_interarrival=mean_interarrival, horizon_min=sim.WEEK_LENGTH)

    # build baseline individual (no reorder, keep original room)
    base_perms = {d: day_cases[d][:] for d in day_cases.keys()}
    base_room = {pid: int(base_df.set_index("pid").loc[pid, "room"]) for pid in base_df["pid"].tolist()}
    baseline_ind = GAIndividual(perms_by_day=base_perms, room_by_pid=base_room)

    # baseline schedule df (decoded - should match base_df but times may be recomputed; we keep exact base_df for baseline)
    baseline_metrics = simulate_fixed_urgent(
        work_schedule_path=work_schedule_path,
        cap_rank_path=cap_rank_path,
        elective_df=base_df,
        urgent_list=urgent_list,
        rest_time=rest_time,
        max_reschedule_weeks=max_reschedule_weeks,
        penalty_next_week=penalty_next_week,
        seed=scenario_seed,
        quiet=True,
    )

    # Load work schedule for lightweight fitness
    df_work = sim.load_work_schedule_xlsx(work_schedule_path)
    work_sched = sim.WorkSchedule(df_work, [f"S{i}" for i in range(1, 13)])
    cap_data = sim.load_cap_rank_xlsx(cap_rank_path)

    # fitness function - LIGHTWEIGHT for GA evolution
    def evaluate(ind: GAIndividual) -> Tuple[float, dict, pd.DataFrame]:
        sched_df = decode_to_schedule_df(base_df, ind, K=K, rest_time=rest_time, allow_after_admin=False)

        # shift penalty from original schedule (absolute planned start)
        shift = 0.0
        for r in sched_df.itertuples(index=False):
            pid = str(r.pid)
            new_abs = int(r.day) * sim.MINUTES_PER_DAY + sim.hhmm_to_minutes(str(r.time_hhmm))
            shift += abs(new_abs - base_planned_abs[pid])

        # Use LIGHTWEIGHT fitness for GA (fast approximation)
        m = lf.simulate_fixed_urgent_lightweight(
            work=work_sched,
            cap=cap_data,
            elective_df=sched_df,
            urgent_list=urgent_list,
            rest_time=rest_time,
            max_reschedule_weeks=max_reschedule_weeks,
            penalty_next_week=penalty_next_week,
        )

        # objective
        obj = (
            w_urgent * m["urgent_wait_weighted"]
            + w_elective_delay * m["elective_delay_total"]
            + w_overtime * m["overtime_total"]
            + w_next_week * (m["elective_delayed_next_week"] * penalty_next_week)
            + w_shift * shift
        )
        # attach helpful fields
        m["shift_penalty"] = float(shift)
        m["objective"] = float(obj)
        return float(obj), m, sched_df

    # initialize population (baseline + mutated copies)
    pop: List[GAIndividual] = []
    pop.append(clone_ind(baseline_ind))
    while len(pop) < pop_size:
        x = clone_ind(baseline_ind)
        # apply a few random mutations to diversify
        for _ in range(rnd.randint(1, 4)):
            mutate(x, day_cases=day_cases, K=K, rnd=rnd, p_swap=0.9, p_room=0.9)
        pop.append(x)

    # evaluate initial pop
    cache: Dict[str, Tuple[float, dict, pd.DataFrame]] = {}
    def key_of(ind: GAIndividual) -> str:
        # cheap hash
        parts = []
        for d in sorted(ind.perms_by_day.keys()):
            parts.append(",".join(ind.perms_by_day[d]))
        parts.append("|".join(f"{pid}:{ind.room_by_pid[pid]}" for pid in sorted(ind.room_by_pid.keys())))
        return "#".join(parts)

    best_ind = None
    best_sched_df = None

    for ind in pop:
        k = key_of(ind)
        if k in cache:
            obj, m, _sched = cache[k]
        else:
            obj, m, _sched = evaluate(ind)
            cache[k] = (obj, m, _sched)
        ind.fitness = obj
        ind.metrics = m
        if best_ind is None or obj < best_ind.fitness:
            best_ind = clone_ind(ind)
            best_ind.fitness = obj
            best_ind.metrics = m
            best_sched_df = _sched

    # generations
    for g in range(1, gens + 1):
        new_pop: List[GAIndividual] = []

        # elitism: keep top 5-10% of population (min 1, max 5)
        pop.sort(key=lambda ind: ind.fitness if ind.fitness is not None else float("inf"))
        elite_count = max(1, min(5, int(pop_size * 0.1)))
        new_pop.extend([clone_ind(pop[i]) for i in range(elite_count)])

        # breeding
        while len(new_pop) < pop_size:
            p1 = tournament_select(pop, k=tournament_k, rnd=rnd)
            p2 = tournament_select(pop, k=tournament_k, rnd=rnd)
            c1, c2 = clone_ind(p1), clone_ind(p2)

            if rnd.random() < cx_rate:
                c1, c2 = crossover(p1, p2, day_cases=day_cases, rnd=rnd)

            if rnd.random() < mut_rate:
                mutate(c1, day_cases=day_cases, K=K, rnd=rnd)
            if rnd.random() < mut_rate:
                mutate(c2, day_cases=day_cases, K=K, rnd=rnd)

            new_pop.append(c1)
            if len(new_pop) < pop_size:
                new_pop.append(c2)

        pop = new_pop

        # evaluate
        for ind in pop:
            if ind.fitness is not None:
                continue
            k = key_of(ind)
            if k in cache:
                obj, m, _sched = cache[k]
            else:
                obj, m, _sched = evaluate(ind)
                cache[k] = (obj, m, _sched)
            ind.fitness = obj
            ind.metrics = m

            if best_ind is None or obj < best_ind.fitness:
                best_ind = clone_ind(ind)
                best_ind.fitness = obj
                best_ind.metrics = m
                best_sched_df = _sched

    assert best_ind is not None and best_sched_df is not None

    # VALIDATE final best solution with FULL SimPy simulation for accuracy
    print("\n" + "="*60)
    print("VALIDATING BEST SOLUTION WITH FULL SIMPY SIMULATION...")
    print("="*60)
    
    best_simpy_metrics = simulate_fixed_urgent(
        work_schedule_path=work_schedule_path,
        cap_rank_path=cap_rank_path,
        elective_df=best_sched_df,
        urgent_list=urgent_list,
        rest_time=rest_time,
        max_reschedule_weeks=max_reschedule_weeks,
        penalty_next_week=penalty_next_week,
        seed=scenario_seed,
        quiet=True,
    )
    
    # Compare lightweight vs SimPy accuracy
    lw_metrics = best_ind.metrics
    print(f"\nAccuracy Check (Lightweight vs SimPy):")
    print(f"  Elective delay: {lw_metrics['elective_delay_total']:.0f} vs {best_simpy_metrics['elective_delay_total']:.0f}")
    print(f"  Urgent wait: {lw_metrics['urgent_wait_weighted']:.0f} vs {best_simpy_metrics['urgent_wait_weighted']:.0f}")
    print(f"  Overtime: {lw_metrics['overtime_total']:.0f} vs {best_simpy_metrics['overtime_total']:.0f}")
    
    # Use SimPy metrics for final reporting (more accurate)
    return best_sched_df, best_simpy_metrics, baseline_metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work_schedule", default="lich_lam_viec_tuan1.xlsx")
    ap.add_argument("--cap_rank", default="Cap_Rank.xlsx")
    ap.add_argument("--elective_sched", default="surgery_schedule.xlsx")

    ap.add_argument("--scenario_seed", type=int, default=1, help="urgent scenario seed (per-scenario GA)")
    ap.add_argument("--mean_urgent", type=float, default=sim.DEFAULT_MEAN_INTERARRIVAL_URGENT)

    # GA params
    ap.add_argument("--pop", type=int, default=60)
    ap.add_argument("--gens", type=int, default=80)
    ap.add_argument("--cx", type=float, default=0.85)
    ap.add_argument("--mut", type=float, default=0.35)
    ap.add_argument("--tourn", type=int, default=3)
    ap.add_argument("--ga_seed", type=int, default=123)

    # sim params
    ap.add_argument("--rest_time", type=int, default=sim.DEFAULT_REST_TIME_MIN)
    ap.add_argument("--max_weeks", type=int, default=0, help="Not used anymore (reschedule logic changed)")
    ap.add_argument("--penalty_next_week", type=int, default=sim.DEFAULT_PENALTY_DELAY_NEXT_WEEK)

    # objective weights
    ap.add_argument("--w_urgent", type=float, default=1.0)
    ap.add_argument("--w_elective_delay", type=float, default=1.0)
    ap.add_argument("--w_overtime", type=float, default=1.0)
    ap.add_argument("--w_next_week", type=float, default=1.0)
    ap.add_argument("--w_shift", type=float, default=0.01, help="penalize deviation from original elective times")

    args = ap.parse_args()

    base_df = sim.load_elective_schedule_xlsx(args.elective_sched, return_df=True)

    best_df, best_metrics, baseline_metrics = run_ga_for_scenario(
        base_df=base_df,
        work_schedule_path=args.work_schedule,
        cap_rank_path=args.cap_rank,
        scenario_seed=args.scenario_seed,
        mean_interarrival=args.mean_urgent,
        rest_time=args.rest_time,
        max_reschedule_weeks=args.max_weeks,
        penalty_next_week=args.penalty_next_week,
        pop_size=args.pop,
        gens=args.gens,
        cx_rate=args.cx,
        mut_rate=args.mut,
        tournament_k=args.tourn,
        w_urgent=args.w_urgent,
        w_elective_delay=args.w_elective_delay,
        w_overtime=args.w_overtime,
        w_next_week=args.w_next_week,
        w_shift=args.w_shift,
        seed_ga=args.ga_seed,
    )

    out_sched = f"best_schedule_seed{args.scenario_seed}.xlsx"
    out_cmp = f"comparison_seed{args.scenario_seed}.json"

    best_df.to_excel(out_sched, index=False)

    payload = {
        "scenario_seed": args.scenario_seed,
        "baseline": baseline_metrics,
        "ga_best": best_metrics,
        "improvement": {
            "urgent_wait_weighted": baseline_metrics["urgent_wait_weighted"] - best_metrics["urgent_wait_weighted"],
            "urgent_wait_total": baseline_metrics["urgent_wait_total"] - best_metrics["urgent_wait_total"],
            "elective_delay_total": baseline_metrics["elective_delay_total"] - best_metrics["elective_delay_total"],
            "overtime_total": baseline_metrics["overtime_total"] - best_metrics["overtime_total"],
            "elective_delayed_next_week": baseline_metrics["elective_delayed_next_week"] - best_metrics["elective_delayed_next_week"],
        }
    }
    with open(out_cmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("=" * 100)
    print(f"GA DONE for scenario_seed={args.scenario_seed}")
    print(f"Saved: {out_sched}")
    print(f"Saved: {out_cmp}")
    print("-" * 100)
    print("Baseline metrics:")
    print(json.dumps(baseline_metrics, ensure_ascii=False, indent=2))
    print("-" * 100)
    print("GA best metrics:")
    print(json.dumps(best_metrics, ensure_ascii=False, indent=2))
    print("=" * 100)


if __name__ == "__main__":
    main()
