# -*- coding: utf-8 -*-
"""
Lightweight (non-SimPy) evaluator for the weekly OR scheduling problem.

Goal:
- Mimic the dispatch logic used in rule_based_or_sim_v3.run_simulation (and/or GA's simulate_fixed_urgent),
  but without SimPy, so GA fitness is fast.
- Produce metrics compatible with simulate_fixed_urgent() in ga_optimize_per_scenario.py:
    urgent_wait_total, urgent_wait_weighted, elective_delay_total,
    elective_delayed_next_week, overtime_total, unproductive_total, urgent_backlog_end, etc.

Assumptions (match v3):
- Time unit: minutes. Scheduler ticks in integer minutes.
- Room busy time = duration + prep (clean-up)
- Surgeon busy time = duration + rest_time
- Electives can start ONLY in admin time (Mon–Fri, admin shift), and must also finish surgeons within admin time & same day.
- Urgents can arrive anytime; their start is constrained by room + duty availability of surgeons.

This module does NOT preempt an ongoing surgery.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import math

# Your simulator module (v3)
import rule_based_or_sim_v3 as sim


@dataclass
class _UrgentLW:
    uid: str
    surgery_type: str
    arrival_time: float
    arrival_bucket: int
    status: str = "waiting"           # waiting/executing/completed
    start_time: Optional[int] = None
    room: Optional[int] = None
    team: Optional[Tuple[str, str, Optional[str]]] = None
    used_team_size: int = 0
    complete_time: Optional[int] = None


def _ceil_minute(x: float) -> int:
    """Eligibility minute for a float arrival (scheduler ticks in integers)."""
    return int(math.ceil(x - 1e-12))


def _next_int_after(t: int, candidates: List[Optional[int]]) -> Optional[int]:
    cands = [c for c in candidates if c is not None and c > t]
    return min(cands) if cands else None


def simulate_fixed_urgent_lightweight(
    work: sim.WorkSchedule,
    cap: sim.CapabilityModel,
    elective_df,
    urgent_list: List[Tuple[float, str]],
    rest_time: int,
    max_reschedule_weeks: int,
    penalty_next_week: int,
    n_rooms: Optional[int] = None,
) -> dict:
    """
    Lightweight replica of the SimPy scheduling loop.

    Parameters
    ----------
    work, cap : from sim.load_work_schedule_xlsx / sim.load_cap_rank_xlsx
    elective_df : DataFrame like sim.load_surgery_schedule_xlsx output
    urgent_list : list[(arrival_time_float, surgery_type)]
    rest_time : surgeon rest minutes after surgery
    max_reschedule_weeks : how many weeks ahead electives may be pushed to find a slot
    penalty_next_week : penalty multiplier (returned via elective_delayed_next_week only; GA uses it)
    n_rooms : if None, inferred from elective_df['room'] (at least 1)

    Returns metrics dict compatible with ga_optimize_per_scenario.simulate_fixed_urgent()
    """
    # --- rooms / surgeons
    if n_rooms is None:
        try:
            n_rooms = int(max(elective_df["room"])) if len(elective_df) else 1
        except Exception:
            n_rooms = 1
    rooms = list(range(1, n_rooms + 1))
    surgeons = list(work.surgeons)

    # --- build elective cases dict
    elective_cases: Dict[str, sim.ElectiveCase] = {}
    for _, r in elective_df.iterrows():
        pid = str(r["pid"])
        day = int(r["day"])
        planned_start = day * sim.MINUTES_PER_DAY + sim.hhmm_to_minutes(str(r["time_hhmm"]))
        elective_cases[pid] = sim.ElectiveCase(
            pid=pid,
            surgery_type=str(r["surgery_type"]),
            planned_start=planned_start,
            scheduled_start=planned_start,
            room=int(r["room"]),
            main=str(r["main"]),
            assist1=str(r["assist1"]),
            assist2=str(r["assist2"]) if str(r["assist2"]) else "",
            status="scheduled",
            delayed_weeks=0,
        )

    # --- urgent arrivals (only those that happen within simulated horizon)
    time_limit = (1 + int(max_reschedule_weeks)) * sim.WEEK_LENGTH
    urgent_events = [(float(a), str(t)) for (a, t) in urgent_list if float(a) <= float(time_limit)]
    urgent_events.sort(key=lambda x: x[0])
    urgent_i = 0
    urgent_cases: List[_UrgentLW] = []

    # --- resource busy-until trackers
    room_busy_until: Dict[int, int] = {k: 0 for k in rooms}
    surg_busy_until: Dict[str, int] = {s: 0 for s in surgeons}

    # --- bookkeeping
    log: List[dict] = []
    stats = {
        "urgent_arrived": 0,
        "urgent_started": 0,
        "urgent_backlog_end": 0,
        "elective_started": 0,
        "elective_rescheduled": [],
    }

    # track completion times to mark "completed" (important for elective-overlap feasibility)
    # pid -> complete_time
    elective_complete_time: Dict[str, int] = {}
    urgent_complete_times: Dict[str, int] = {}

    # --- main scheduler loop (integer minutes)
    t = 0

    while t < time_limit:
        # 0) mark completed cases at this minute
        for pid, ct in list(elective_complete_time.items()):
            if ct <= t:
                c = elective_cases.get(pid)
                if c is not None and c.status != "completed":
                    c.status = "completed"
                elective_complete_time.pop(pid, None)

        for uid, ct in list(urgent_complete_times.items()):
            if ct <= t:
                # find urgent and mark
                for u in urgent_cases:
                    if u.uid == uid and u.status != "completed":
                        u.status = "completed"
                        break
                urgent_complete_times.pop(uid, None)

        # 1) add urgent arrivals that have happened by now (float arrival <= t)
        while urgent_i < len(urgent_events) and urgent_events[urgent_i][0] <= float(t) + 1e-12:
            a, st = urgent_events[urgent_i]
            uid = f"U{stats['urgent_arrived']+1:03d}"
            urgent_cases.append(_UrgentLW(uid=uid, surgery_type=st, arrival_time=a, arrival_bucket=int(a)))
            stats["urgent_arrived"] += 1
            urgent_i += 1

        # 2) compute free resources at this minute
        free_rooms: Set[int] = {k for k in rooms if room_busy_until[k] <= t}
        free_surgeons: Set[str] = {s for s in surgeons if surg_busy_until[s] <= t}

        # ------------------------------------------------------------------
        # 2A) URGENT dispatch: priority-aware, but can skip if cannot form team
        # ------------------------------------------------------------------
        def urgent_sort_key(u: _UrgentLW) -> Tuple[int, int, float, str]:
            rank = int(cap.rank_by_type.get(u.surgery_type, 999))
            return (u.arrival_bucket, rank, float(u.arrival_time), u.uid)

        waiting_urgents = [u for u in urgent_cases if u.status == "waiting" and u.arrival_time <= float(t) + 1e-12]
        waiting_urgents.sort(key=urgent_sort_key)

        for u in waiting_urgents:
            if not free_rooms:
                break

            # available surgeons must be free AND on-duty for urgent now
            avail_urgent_surgeons = {s for s in free_surgeons if work.on_duty_for_urgent(s, float(t))}
            if not avail_urgent_surgeons:
                continue

            room = min(free_rooms)

            pick = sim.choose_urgent_team(u.surgery_type, avail_urgent_surgeons, cap, prefer_three=True)
            if pick is None:
                pick = sim.choose_urgent_team(u.surgery_type, avail_urgent_surgeons, cap, prefer_three=False)
            if pick is None:
                continue

            main, a1, a2, team_size = pick
            team = (main, a1, a2 if a2 is not None else None)
            needed = {main, a1} | ({a2} if a2 is not None else set())

            # allocate this minute
            free_rooms.remove(room)
            free_surgeons -= needed

            # start
            u.status = "executing"
            u.start_time = t
            u.room = room
            u.team = team
            u.used_team_size = team_size
            stats["urgent_started"] += 1

            dur = int(sim.SURGERY_DURATION_MIN[u.surgery_type])
            prep = int(sim.PREP_TIME_MIN[u.surgery_type])
            end_surgeon = t + dur + int(rest_time)
            end_room = t + dur + prep
            complete_time = max(end_surgeon, end_room)
            u.complete_time = complete_time
            urgent_complete_times[u.uid] = complete_time

            # update busy-until
            room_busy_until[room] = max(room_busy_until[room], end_room)
            for s in needed:
                surg_busy_until[s] = max(surg_busy_until[s], end_surgeon)

            # log (match execute_surgery fields used by GA)
            log.append({
                "patient": u.uid,
                "type": "URGENT",
                "surgery_type": u.surgery_type,
                "arrival": float(u.arrival_time),
                "start": float(t),
                "end_room": float(end_room),
                "end_surgeon": float(end_surgeon),
                "wait": float(t) - float(u.arrival_time),
                "main": main,
                "assist1": a1,
                "assist2": a2 if a2 is not None else None,
                "room": room,
                "team_size": team_size,
            })

        # recompute free resources after urgent dispatch
        free_rooms = {k for k in rooms if room_busy_until[k] <= t}
        free_surgeons = {s for s in surgeons if surg_busy_until[s] <= t}

        # ------------------------------------------------------------------
        # 2B) ELECTIVE dispatch (admin time only, FCFS by scheduled_start)
        # ------------------------------------------------------------------
        due_electives = sorted(
            [c for c in elective_cases.values() if c.status == "scheduled" and c.scheduled_start <= t],
            key=lambda c: (c.scheduled_start, c.planned_start, c.pid),
        )

        for c in due_electives:
            # if not admin time, reschedule
            if not sim.is_admin_time(t):
                new_start = sim.find_earliest_elective_slot(
                    t, c, elective_cases, work, int(rest_time)
                )
                if new_start is None:
                    continue
                old = c.scheduled_start
                c.scheduled_start = int(new_start)
                c.delayed_weeks = max(c.delayed_weeks, int(new_start) // sim.WEEK_LENGTH)
                stats["elective_rescheduled"].append({"from": old, "to": int(new_start), "reason": "Not admin time"})
                continue

            # room must be free (match SimPy: reschedule instead of waiting minute-by-minute)
            if c.room not in free_rooms:
                new_start = sim.find_earliest_elective_slot(
                    t, c, elective_cases, work, int(rest_time)
                )
                if new_start is None:
                    continue
                # Important: SimPy will keep re-checking each minute; because we jump time,
                # we push the scheduled_start to the earliest minute the room becomes free.
                min_free = int(room_busy_until.get(c.room, t + 1))
                ns = max(int(new_start), min_free)
                old = c.scheduled_start
                c.scheduled_start = int(ns)
                c.delayed_weeks = max(c.delayed_weeks, int(ns) // sim.WEEK_LENGTH)
                stats["elective_rescheduled"].append({"from": old, "to": int(ns), "reason": "Room busy"})
                continue

            needed = {c.main, c.assist1} | ({c.assist2} if c.assist2 else set())

            # all surgeons must be on duty for elective now
            if any(not work.on_duty_for_elective(s, float(t)) for s in needed):
                new_start = sim.find_earliest_elective_slot(
                    t, c, elective_cases, work, int(rest_time)
                )
                if new_start is None:
                    continue
                old = c.scheduled_start
                c.scheduled_start = int(new_start)
                c.delayed_weeks = max(c.delayed_weeks, int(new_start) // sim.WEEK_LENGTH)
                stats["elective_rescheduled"].append({"from": old, "to": int(new_start), "reason": "Surgeon off-duty"})
                continue

            # surgeons must be free (match SimPy: reschedule instead of waiting)
            if not needed.issubset(free_surgeons):
                new_start = sim.find_earliest_elective_slot(
                    t, c, elective_cases, work, int(rest_time)
                )
                if new_start is None:
                    continue
                # Push scheduled_start to when ALL needed surgeons become free (see note above).
                min_free = 0
                for s in needed:
                    min_free = max(min_free, int(surg_busy_until.get(s, t + 1)))
                ns = max(int(new_start), min_free)
                old = c.scheduled_start
                c.scheduled_start = int(ns)
                c.delayed_weeks = max(c.delayed_weeks, int(ns) // sim.WEEK_LENGTH)
                stats["elective_rescheduled"].append({"from": old, "to": int(ns), "reason": "Surgeon busy"})
                continue

            # ensure finish within admin hours same day
            day_start = (t // sim.MINUTES_PER_DAY) * sim.MINUTES_PER_DAY
            admin_end = day_start + sim.ADMIN_SHIFT_END
            end_surg = t + c.duration() + int(rest_time)
            if end_surg > admin_end:
                new_start = sim.find_earliest_elective_slot(
                    t, c, elective_cases, work, int(rest_time)
                )
                if new_start is None:
                    continue
                old = c.scheduled_start
                c.scheduled_start = int(new_start)
                c.delayed_weeks = max(c.delayed_weeks, int(new_start) // sim.WEEK_LENGTH)
                stats["elective_rescheduled"].append({"from": old, "to": int(new_start), "reason": "Would exceed admin hours"})
                continue

            # allocate
            free_rooms.remove(c.room)
            free_surgeons -= needed

            # start elective
            actual_start = t
            c.scheduled_start = actual_start
            c.status = "executing"
            stats["elective_started"] += 1

            dur = c.duration()
            prep = c.prep()
            end_surgeon = actual_start + dur + int(rest_time)
            end_room = actual_start + dur + prep
            elective_complete_time[c.pid] = max(end_surgeon, end_room)

            # update busy-until
            room_busy_until[c.room] = max(room_busy_until[c.room], end_room)
            for s in needed:
                surg_busy_until[s] = max(surg_busy_until[s], end_surgeon)

            log.append({
                "patient": c.pid,
                "type": "ELECTIVE",
                "surgery_type": c.surgery_type,
                "arrival": float(c.planned_start),
                "start": float(actual_start),
                "end_room": float(end_room),
                "end_surgeon": float(end_surgeon),
                "wait": float(actual_start) - float(c.planned_start),
                "main": c.main,
                "assist1": c.assist1,
                "assist2": c.assist2 if c.assist2 else None,
                "room": int(c.room),
                "team_size": 3,
            })

        # ---- advance time (event-driven jump)
        # next urgent eligible minute
        next_u_tick: Optional[int] = None
        if urgent_i < len(urgent_events):
            next_u_tick = _ceil_minute(urgent_events[urgent_i][0])

        # next elective due minute
        next_e_tick: Optional[int] = None
        future_sched = [c.scheduled_start for c in elective_cases.values() if c.status == "scheduled" and c.scheduled_start > t]
        if future_sched:
            next_e_tick = int(min(future_sched))

        # next resource release minute
        next_rel: Optional[int] = None
        rels = [v for v in room_busy_until.values()] + [v for v in surg_busy_until.values()]
        rels = [v for v in rels if v > t]
        if rels:
            next_rel = int(min(rels))

        nxt = _next_int_after(t, [next_u_tick, next_e_tick, next_rel])
        if nxt is None:
            break
        # ensure at least +1 to avoid stalling
        t = max(t + 1, nxt)

    # backlog urgent at end (only those that have arrived)
    backlog_urgent = sum(1 for u in urgent_cases if u.status == "waiting" and u.arrival_time <= float(time_limit) + 1e-12)
    stats["urgent_backlog_end"] = backlog_urgent

    # ---- KPIs (match GA wrapper)
    sim_end = 0
    for rec in log:
        sim_end = max(sim_end, int(math.ceil(rec["end_room"])), int(math.ceil(rec["end_surgeon"])))
    sim_end = max(sim_end, int(time_limit))

    duty_map = {s: work.duty_intervals_abs(s, sim_end) for s in surgeons}
    busy_map = {s: [] for s in surgeons}
    for r in log:
        a = int(r["start"])
        b = int(r["end_surgeon"])
        for s in [r["main"], r["assist1"]]:
            busy_map[s].append((a, b))
        if r.get("assist2") is not None:
            busy_map[r["assist2"]].append((a, b))

    overtime_total = 0
    unproductive_total = 0
    for s in surgeons:
        duty = sim.merge_intervals(duty_map[s])
        busy = sim.merge_intervals(busy_map[s])
        busy_in_duty = sim.overlap_total(busy, duty)
        duty_total = sim.interval_total(duty)
        busy_total = sim.interval_total(busy)
        overtime_total += max(0, busy_total - busy_in_duty)
        unproductive_total += max(0, duty_total - busy_in_duty)

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

    metrics = {
        "rooms": int(n_rooms),
        "urgent_arrived": int(stats["urgent_arrived"]),
        "urgent_started": int(stats["urgent_started"]),
        "urgent_backlog_end": int(stats["urgent_backlog_end"]),
        "urgent_wait_total": float(urgent_wait_total),
        "urgent_wait_weighted": float(urgent_wait_weighted),
        "elective_started": int(stats["elective_started"]),
        "elective_delay_total": float(elective_delay_total),
        "elective_delayed_next_week": int(delayed_next_week),
        "overtime_total": int(overtime_total),
        "unproductive_total": int(unproductive_total),
        "elective_rescheduled_count": int(len(stats["elective_rescheduled"])),
        # keep for debugging
        "_log_len": int(len(log)),
    }
    return metrics
