# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import random
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import pandas as pd
import simpy  # baseline rule-based sim uses simpy

import rule_based_or_sim_v3 as sim


# ----------------------------
# Scenario generator
# ----------------------------
def generate_urgent_list(mean_interarrival: float, seed: int) -> List[Tuple[float, str]]:
    """
    Generate a fixed urgent arrival stream for a scenario seed.
    Returned list items are (arrival_time_minute, surgery_type).
    """
    rnd = random.Random(seed)
    t = 0.0
    out: List[Tuple[float, str]] = []
    types = list(sim.SURGERY_DURATION_MIN.keys())
    while True:
        t += rnd.expovariate(1.0 / float(mean_interarrival))
        if t >= sim.WEEK_LENGTH:
            break
        out.append((float(t), rnd.choice(types)))
    return out


def minutes_to_hhmm_in_day(min_in_day: int) -> str:
    h = int(min_in_day // 60)
    m = int(min_in_day % 60)
    return f"{h:02d}:{m:02d}"


# ----------------------------
# Full-schedule baseline (rule-based)
# ----------------------------
def _safe_parse_surgeon(val: object) -> str:
    code = sim.parse_surgeon_code(val)
    return code if code is not None else ""


def _mark_delayed_next_week(
    c: sim.ElectiveCase,
    now_int: int,
    reason: str,
    stats: dict,
) -> None:
    """
    When no feasible slot exists in the current week (find_earliest_elective_slot returns None),
    mimic rule_based_or_sim_v3.run_sim behavior:
      - mark completed (won't be scheduled this week)
      - set delayed_weeks to next week index (>=1)
      - record reschedule log
    """
    current_week = int(now_int // sim.WEEK_LENGTH)
    c.status = "completed"
    c.delayed_weeks = max(c.delayed_weeks, current_week + 1)
    stats["elective_rescheduled"].append({
        "pid": c.pid,
        "from": int(c.scheduled_start),
        "to": f"week_{c.delayed_weeks}",
        "reason": f"{reason} - no slot in current week",
    })


def get_rule_based_baseline(
    work_schedule_path: str,
    cap_rank_path: str,
    elective_input_df: pd.DataFrame,
    urgent_list: List[Tuple[float, str]],
    rest_time: int,
    max_reschedule_weeks: int,
    penalty_next_week: int,
    seed: int,
) -> Tuple[pd.DataFrame, dict]:
    """
    Run rule-based simulation with elective_input_df + urgent_list and extract the FULL executed schedule
    (elective + urgent) from the execution log.

    Returns:
      - baseline_full_schedule_df: rows for BOTH ELECTIVE and URGENT with executed start times
      - baseline_metrics: KPI dict compatible with GA objective
    """
    # Load work + cap
    df_work = sim.load_work_schedule_xlsx(work_schedule_path)
    surgeons = [f"S{i}" for i in range(1, 13)]
    work = sim.WorkSchedule(df_work, surgeons)
    cap = sim.load_cap_rank_xlsx(cap_rank_path)

    # Build elective cases from input df
    df = elective_input_df.copy()
    df["pid"] = df["pid"].astype(str)

    elective_cases: Dict[str, sim.ElectiveCase] = {}
    for _, row in df.iterrows():
        pid = str(row["pid"])
        stype = str(row["surgery_type"])
        day = int(row["day"])
        hhmm = str(row["time_hhmm"])
        room = int(row["room"])
        main = _safe_parse_surgeon(row.get("main", ""))
        a1 = _safe_parse_surgeon(row.get("assist1", ""))
        a2_raw = row.get("assist2", "")
        a2 = _safe_parse_surgeon(a2_raw)
        if a2 == main or a2 == a1:
            a2 = ""
        planned_start = int(day * sim.MINUTES_PER_DAY + sim.hhmm_to_minutes(hhmm))

        elective_cases[pid] = sim.ElectiveCase(
            pid=pid,
            surgery_type=stype,
            planned_start=planned_start,
            scheduled_start=planned_start,
            room=room,
            main=main,
            assist1=a1,
            assist2=a2,
            status="waiting",
            delayed_weeks=0,
        )

    # Urgent stream
    urgent_stream = list(urgent_list)
    urgent_cases: List[sim.UrgentCase] = []

    # Resources
    n_rooms = int(max(df["room"].max() if len(df) else 1, 2))
    env = simpy.Environment()
    room_res = {r: simpy.Resource(env, capacity=1) for r in range(1, n_rooms + 1)}
    surg_res = {s: simpy.Resource(env, capacity=1) for s in surgeons}
    rooms = list(room_res.keys())

    log: List[dict] = []
    active_counter = {"active": 0}
    stats = {
        "urgent_arrived": 0,
        "urgent_started": 0,
        "elective_started": 0,
        "elective_rescheduled": [],
        "urgent_backlog_end": 0,
    }

    # Urgent stream - PRE-CREATE all urgent cases at start
    urgent_cases: List[sim.UrgentCase] = []
    for i, (t, stype) in enumerate(urgent_stream, 1):
        uid = f"U{i:04d}"
        urgent_cases.append(sim.UrgentCase(
            uid=uid,
            surgery_type=str(stype),
            arrival_time=float(t),
            arrival_bucket=int(t),
            rank=int(cap.rank_by_type.get(str(stype), 999)),
            status="waiting",  # All created as waiting, will dispatch when arrival_time <= now
        ))
    stats["urgent_arrived"] = len(urgent_cases)  # Count all urgent from the start

    def scheduler():
        # Simulation stops when: all urgent processed + all elective done + no active surgeries
        arrival_horizon = sim.WEEK_LENGTH  # urgent arrivals only within week 1
        time_limit = (1 + max_reschedule_weeks) * sim.WEEK_LENGTH
        
        while True:
            now = float(env.now)
            now_int = int(env.now)
            
            # Check stopping condition (same as rule_based_or_sim_v3.py)
            all_elective_done = all(c.status == "completed" for c in elective_cases.values())
            waiting_urgent = [u for u in urgent_cases if u.status == "waiting"]
            
            # Stop when: past arrival horizon + no waiting urgent + no active + all elective done
            if (now >= arrival_horizon and not waiting_urgent and active_counter["active"] == 0 and all_elective_done):
                break
            # Safety limit: don't run forever
            if now >= time_limit:
                break
            
            free_rooms = {r for r in rooms if room_res[r].count == 0}
            free_surgeons = {s for s in surgeons if surg_res[s].count == 0}

            # ---------- URGENT DISPATCH ----------
            available_urgent_surgeons = {s for s in free_surgeons if work.on_duty_for_urgent(s, now)}
            waiting_urgent_sorted = sorted(
                [u for u in urgent_cases if u.status == "waiting" and u.arrival_time <= now],
                key=lambda u: (u.arrival_bucket, u.rank, u.arrival_time, u.uid),
            )

            for u in waiting_urgent_sorted:
                if not free_rooms:
                    break
                room = min(free_rooms)
                team_choice = sim.choose_urgent_team(u.surgery_type, available_urgent_surgeons, cap, prefer_three=True)
                if team_choice is None:
                    team_choice = sim.choose_urgent_team(u.surgery_type, available_urgent_surgeons, cap, prefer_three=False)
                if team_choice is None:
                    continue
                main, a1, a2, _team_size = team_choice

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
                    arrival_time=float(u.arrival_time),
                    start_time=float(now_int),
                    case_obj=u,
                ))

            # ---------- ELECTIVE DISPATCH ----------
            for pid in list(elective_cases.keys()):
                c = elective_cases[pid]
                if c.status != "waiting":
                    continue
                if int(c.scheduled_start) > now_int:
                    continue

                now_in_day = now_int % sim.MINUTES_PER_DAY

                # Not admin time => reschedule
                if not sim.is_admin_time(now):
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is None:
                        _mark_delayed_next_week(c, now_int, "Not admin time", stats)
                        continue
                    if int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": int(c.scheduled_start), "to": int(new_start), "reason": "Not admin time"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Room busy => reschedule
                if c.room not in free_rooms:
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is None:
                        _mark_delayed_next_week(c, now_int, "Room busy", stats)
                        continue
                    if int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": int(c.scheduled_start), "to": int(new_start), "reason": "Room busy"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                needed = {c.main, c.assist1}
                if c.assist2:
                    needed.add(c.assist2)

                # Surgeon off-duty => reschedule
                if any(not work.on_duty_for_elective(s, now) for s in needed):
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is None:
                        _mark_delayed_next_week(c, now_int, "Surgeon off-duty", stats)
                        continue
                    if int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": int(c.scheduled_start), "to": int(new_start), "reason": "Surgeon off-duty"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Surgeon busy => reschedule
                if not needed.issubset(free_surgeons):
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is None:
                        _mark_delayed_next_week(c, now_int, "Surgeon busy", stats)
                        continue
                    if int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": int(c.scheduled_start), "to": int(new_start), "reason": "Surgeon busy"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Would exceed admin hours => reschedule
                dur = int(sim.SURGERY_DURATION_MIN[c.surgery_type])
                prep = int(sim.PREP_TIME_MIN[c.surgery_type])
                end_in_day = now_in_day + dur + prep
                if end_in_day > sim.ADMIN_SHIFT_END:
                    new_start = sim.find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time)
                    if new_start is None:
                        _mark_delayed_next_week(c, now_int, "Would exceed admin hours", stats)
                        continue
                    if int(new_start) != int(c.scheduled_start):
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": int(c.scheduled_start), "to": int(new_start), "reason": "Would exceed admin hours"})
                        c.scheduled_start = int(new_start)
                        c.delayed_weeks = max(c.delayed_weeks, int(c.scheduled_start // sim.WEEK_LENGTH))
                    continue

                # Execute elective
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

        stats["urgent_backlog_end"] = sum(1 for u in urgent_cases if u.status == "waiting")

    env.process(scheduler())
    env.run()

    # Build baseline_full_schedule_df from log
    rows = []
    for r in log:
        start = int(r["start"])
        day = start // sim.MINUTES_PER_DAY
        tod = start % sim.MINUTES_PER_DAY
        rows.append({
            "case_id": str(r["pid"]),
            "case_type": str(r["type"]),  # "URGENT" / "ELECTIVE"
            "surgery_type": str(r["surgery_type"]),
            "arrival": float(r["arrival"]),
            "start": float(r["start"]),
            "room": int(r["room"]),
            "main": str(r["main"]),
            "assist1": str(r["assist1"]),
            "assist2": str(r.get("assist2") or ""),
            "day": int(day),
            "time_hhmm": minutes_to_hhmm_in_day(int(tod)),
        })
    
    # Add elective cases that were pushed out of the simulated horizon (not executed => not in log)
    executed_electives = {str(r.get("pid")) for r in log if str(r.get("type","")).upper() == "ELECTIVE"}
    for c in elective_cases.values():
        if str(c.pid) in executed_electives:
            continue
        # If delayed to next week (or later), add a placeholder row so metrics can count it.
        if int(getattr(c, "delayed_weeks", 0)) >= 1:
            placeholder_start = int(int(c.delayed_weeks) * sim.WEEK_LENGTH + sim.ADMIN_SHIFT_START)
        else:
            placeholder_start = int(c.scheduled_start)
        day = placeholder_start // sim.MINUTES_PER_DAY
        tod = placeholder_start % sim.MINUTES_PER_DAY
        rows.append({
            "case_id": str(c.pid),
            "case_type": "ELECTIVE",
            "surgery_type": str(c.surgery_type),
            "arrival": float(c.planned_start),
            "start": float(placeholder_start),
            "room": int(c.room),
            "main": str(c.main),
            "assist1": str(c.assist1),
            "assist2": str(c.assist2 or ""),
            "day": int(day),
            "time_hhmm": minutes_to_hhmm_in_day(int(tod)),
        })
    baseline_full_df = pd.DataFrame(rows).sort_values(["start", "case_type", "case_id"]).reset_index(drop=True)

    baseline_metrics = compute_metrics_from_schedule(
        schedule_df=baseline_full_df,
        work=work,
        cap=cap,
        rest_time=rest_time,
        max_reschedule_weeks=max_reschedule_weeks,
        penalty_next_week=penalty_next_week,
        n_rooms=n_rooms,
        surgeons=surgeons,
        urgent_total=len(urgent_list),
        urgent_backlog_end=int(stats.get("urgent_backlog_end", 0)),
    )
    return baseline_full_df, baseline_metrics


# ----------------------------
# Schedule metrics (deterministic, no SimPy)
# ----------------------------
def compute_metrics_from_schedule(
    schedule_df: pd.DataFrame,
    work: sim.WorkSchedule,
    cap: sim.CapabilityModel,
    rest_time: int,
    max_reschedule_weeks: int,
    penalty_next_week: int,
    n_rooms: int,
    surgeons: List[str],
    urgent_total: Optional[int] = None,
    urgent_backlog_end: Optional[int] = None,
) -> dict:
    """
    Compute metrics compatible with simulate_fixed_urgent() from a fixed schedule dataframe.
    schedule_df must include: case_type, surgery_type, arrival, start, room, main, assist1, assist2
    """
    time_limit = (1 + max_reschedule_weeks) * sim.WEEK_LENGTH

    urgent_wait_by_rank: Dict[int, List[float]] = {}
    elective_recs: List[dict] = []
    log_like: List[dict] = []

    for _, row in schedule_df.iterrows():
        ctype = str(row["case_type"]).upper()
        stype = str(row["surgery_type"])
        arrival = float(row["arrival"])
        start = float(row["start"])
        room = int(row["room"])
        main = str(row["main"])
        a1 = str(row["assist1"])
        a2 = str(row.get("assist2") or "")
        if a2.lower() == "nan":
            a2 = ""
        dur = int(sim.SURGERY_DURATION_MIN[stype])
        prep = int(sim.PREP_TIME_MIN[stype])
        end_surgeon = start + dur + rest_time
        end_room = start + dur + prep

        log_like.append({
            "pid": str(row["case_id"]),
            "type": "URGENT" if ctype == "URGENT" else "ELECTIVE",
            "surgery_type": stype,
            "arrival": arrival,
            "start": start,
            "end_surgeon": end_surgeon,
            "end_room": end_room,
            "room": room,
            "main": main,
            "assist1": a1,
            "assist2": a2,
            "wait": start - arrival,
        })

        if ctype == "URGENT":
            rank = int(cap.rank_by_type.get(stype, 999))
            urgent_wait_by_rank.setdefault(rank, []).append(max(0.0, start - arrival))
        else:
            elective_recs.append({"wait": start - arrival})

    # weighted urgent waiting
    max_rank = max(urgent_wait_by_rank.keys()) if urgent_wait_by_rank else 1
    def w_rank(rank: int) -> float:
        return float(max_rank - rank + 1)

    urgent_wait_total = sum(sum(ws) for ws in urgent_wait_by_rank.values())
    urgent_wait_weighted = sum(sum(w * w_rank(rank) for w in ws) for rank, ws in urgent_wait_by_rank.items())

    elective_delay_total = sum(max(0.0, float(r["wait"])) for r in elective_recs)

    # elective delayed to next week: elective starts at week>=1
    delayed_next_week = int(sum(
        1 for _, row in schedule_df.iterrows()
        if str(row["case_type"]).upper() != "URGENT" and int(float(row["start"]) // sim.WEEK_LENGTH) >= 1
    ))

    # overtime/unproductive for surgeons
    duty_map = {s: work.duty_intervals_abs(s, time_limit) for s in surgeons}
    busy_map = {s: [] for s in surgeons}
    for r in log_like:
        for s in [r["main"], r["assist1"]]:
            if s:
                busy_map[s].append((int(r["start"]), int(r["end_surgeon"])))
        a2 = r.get("assist2") or ""
        if a2:
            busy_map[a2].append((int(r["start"]), int(r["end_surgeon"])))

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

    metrics = {
        "rooms": int(n_rooms),
        "urgent_arrived": int(urgent_total) if urgent_total is not None else int(sum(1 for _ in schedule_df.itertuples() if str(_.case_type).upper()=="URGENT")),
        "urgent_started": int(sum(1 for _ in schedule_df.itertuples() if str(_.case_type).upper()=="URGENT")),
        "urgent_backlog_end": int(urgent_backlog_end) if urgent_backlog_end is not None else 0,
        "urgent_wait_total": float(urgent_wait_total),
        "urgent_wait_weighted": float(urgent_wait_weighted),
        "elective_started": int(sum(1 for _ in schedule_df.itertuples() if str(_.case_type).upper()!="URGENT")),
        "elective_delay_total": float(elective_delay_total),
        "elective_delayed_next_week": int(delayed_next_week),
        "overtime_total": int(overtime_total),
        "unproductive_total": int(unproductive_total),
    }
    # Add penalty-expanded metric if you want to keep old objective structure
    metrics["elective_delayed_next_week_penalized"] = int(delayed_next_week * int(penalty_next_week))
    return metrics


# ----------------------------
# GA representation (full schedule)
# ----------------------------
@dataclass
class GAIndividual:
    delta_by_case: Dict[str, int]         # minutes offset from baseline start
    room_by_case: Dict[str, int]          # room assignment (1..K)
    fitness: Optional[float] = None
    metrics: Optional[dict] = None


def clone_ind(ind: GAIndividual) -> GAIndividual:
    return GAIndividual(
        delta_by_case=dict(ind.delta_by_case),
        room_by_case=dict(ind.room_by_case),
        fitness=ind.fitness,
        metrics=dict(ind.metrics) if ind.metrics else None,
    )


def key_of(ind: GAIndividual) -> str:
    # deterministic ordering
    keys = sorted(ind.delta_by_case.keys())
    deltas = ",".join(f"{k}:{ind.delta_by_case[k]}" for k in keys)
    rooms = ",".join(f"{k}:{ind.room_by_case[k]}" for k in keys)
    return deltas + "|" + rooms


# ----------------------------
# Decoder / Repair (SSGS)
# ----------------------------
def _round_up(x: int, step: int) -> int:
    return int(((x + step - 1) // step) * step)


def _first_conflict(intervals: List[Tuple[int,int]], a: int, b: int) -> Optional[Tuple[int,int]]:
    # intervals assumed merged/sorted
    for (s,e) in intervals:
        if e <= a:
            continue
        if s >= b:
            break
        return (s,e)
    return None


def _insert_interval(intervals: List[Tuple[int,int]], a: int, b: int) -> None:
    intervals.append((a,b))
    intervals.sort()
    merged = sim.merge_intervals(intervals)
    intervals[:] = merged


def _next_admin_start(t: int) -> int:
    """
    Jump to the next valid elective admin-time start (Mon-Fri 08:00-16:00),
    using ABSOLUTE day index (works across reschedule weeks too).
    """
    cur = int(t)
    if cur < 0:
        cur = 0

    while True:
        day_idx = cur // sim.MINUTES_PER_DAY
        wd = int(day_idx % 7)  # 0=Mon..6=Sun
        tod = int(cur % sim.MINUTES_PER_DAY)

        if 0 <= wd <= 4:
            if tod < sim.ADMIN_SHIFT_START:
                return int(day_idx * sim.MINUTES_PER_DAY + sim.ADMIN_SHIFT_START)
            if sim.ADMIN_SHIFT_START <= tod < sim.ADMIN_SHIFT_END:
                return int(cur)

        # advance to next day 08:00
        cur = int((day_idx + 1) * sim.MINUTES_PER_DAY + sim.ADMIN_SHIFT_START)

def decode_full_schedule_df(
    baseline_df: pd.DataFrame,
    ind: GAIndividual,
    work: sim.WorkSchedule,
    cap: sim.CapabilityModel,
    rest_time: int,
    max_reschedule_weeks: int,
    step: int = 5,
) -> pd.DataFrame:
    """
    Build a feasible schedule from a baseline schedule + GA deltas and room decisions.
    - Baseline provides: case_id, case_type, surgery_type, arrival, start (baseline), team fields.
    - GA provides: desired offsets & room changes.
    """
    time_limit = (1 + max_reschedule_weeks) * sim.WEEK_LENGTH

    base = baseline_df.copy()
    base["case_id"] = base["case_id"].astype(str)
    base["case_type"] = base["case_type"].astype(str).str.upper()
    base["baseline_start"] = base["start"].astype(int)

    # precompute case properties
    case_info = {}
    for _, row in base.iterrows():
        cid = str(row["case_id"])
        ctype = str(row["case_type"]).upper()
        stype = str(row["surgery_type"])
        arrival = int(float(row["arrival"]))
        baseline_start = int(row["baseline_start"])
        main = str(row["main"])
        a1 = str(row["assist1"])
        a2 = str(row.get("assist2") or "")
        if a2.lower() == "nan":
            a2 = ""
        team = [main, a1] + ([a2] if a2 else [])
        dur = int(sim.SURGERY_DURATION_MIN[stype])
        prep = int(sim.PREP_TIME_MIN[stype])
        case_info[cid] = {
            "case_type": ctype,
            "surgery_type": stype,
            "arrival": arrival,
            "baseline_start": baseline_start,
            "team": team,
            "dur": dur,
            "prep": prep,
        }

    # calendars
    n_rooms = int(max(ind.room_by_case.values()) if ind.room_by_case else 1)
    room_cal: Dict[int, List[Tuple[int,int]]] = {r: [] for r in range(1, n_rooms+1)}
    surg_cal: Dict[str, List[Tuple[int,int]]] = {s: [] for s in work.surgeons}

    # desired order
    desired_list = []
    for cid, info in case_info.items():
        delta = int(ind.delta_by_case.get(cid, 0))
        desired = int(info["baseline_start"] + delta)
        # clamps
        if info["case_type"] == "URGENT":
            desired = max(desired, int(info["arrival"]))
        else:
            # elective cannot start earlier than planned arrival
            desired = max(desired, int(info["arrival"]))
            desired = _next_admin_start(desired)
        desired_list.append((desired, 0 if info["case_type"] == "URGENT" else 1, cid))
    desired_list.sort()

    scheduled_rows = []

    for desired, _prio, cid in desired_list:
        info = case_info[cid]
        ctype = info["case_type"]
        stype = info["surgery_type"]
        arrival = info["arrival"]
        team = info["team"]
        dur = info["dur"]
        prep = info["prep"]
        room = int(ind.room_by_case.get(cid, 1))

        # CRITICAL FIX: If case unchanged (delta=0, room same) → use baseline exactly
        # This ensures baseline individual evaluates to same metrics as baseline generation
        delta = int(ind.delta_by_case.get(cid, 0))
        baseline_row = base[base["case_id"] == cid]
        
        if (delta == 0 and 
            len(baseline_row) > 0 and 
            room == int(baseline_row.iloc[0]["room"])):
            
            # Case unchanged → Copy baseline exactly, skip constraint checks
            br = baseline_row.iloc[0]
            day = int(br["start"]) // sim.MINUTES_PER_DAY
            tod = int(br["start"]) % sim.MINUTES_PER_DAY
            scheduled_rows.append({
                "case_id": cid,
                "case_type": ctype,
                "surgery_type": stype,
                "arrival": float(arrival),
                "start": float(br["start"]),  # Exact baseline time
                "wait": float(br["start"] - arrival),
                "room": int(room),
                "main": team[0] if len(team) > 0 else "",
                "assist1": team[1] if len(team) > 1 else "",
                "assist2": team[2] if len(team) > 2 else "",
                "day": int(day),
                "time_hhmm": minutes_to_hhmm_in_day(int(tod)),
            })
            continue  # Skip to next case, no constraint checking needed
        
        # ELSE: Case modified (delta != 0 or room changed) → apply normal decode with constraints
        # search feasible start >= desired
        t = int(desired)
        t = _round_up(t, step)

        while t < time_limit:
            # arrival constraint
            if ctype == "URGENT" and t < arrival:
                t = _round_up(arrival, step)
                continue
            if ctype != "URGENT" and t < arrival:
                t = _round_up(arrival, step)
                continue

            # duty/admin constraints
            if ctype == "URGENT":
                if any(not work.on_duty_for_urgent(s, float(t)) for s in team):
                    # advance by step; (could be optimized, but ok)
                    t += step
                    continue
            else:
                if not sim.is_admin_time(float(t)):
                    t = _next_admin_start(t + 1)
                    t = _round_up(t, step)
                    continue
                # must finish within admin shift
                end_in_day = sim.time_in_day(t) + dur + prep
                if end_in_day > sim.ADMIN_SHIFT_END:
                    # next weekday morning
                    t = _next_admin_start((t // sim.MINUTES_PER_DAY + 1) * sim.MINUTES_PER_DAY + sim.ADMIN_SHIFT_START)
                    t = _round_up(t, step)
                    continue
                if any(not work.on_duty_for_elective(s, float(t)) for s in team):
                    # elective duty same as admin + day-off; push to next admin start
                    t = _next_admin_start((t // sim.MINUTES_PER_DAY + 1) * sim.MINUTES_PER_DAY + sim.ADMIN_SHIFT_START)
                    t = _round_up(t, step)
                    continue

            # capacity constraints
            room_interval = (t, t + dur + prep)
            surg_interval = (t, t + dur + rest_time)

            # room conflict
            rc = _first_conflict(room_cal.get(room, []), room_interval[0], room_interval[1])
            if rc is not None:
                t = _round_up(rc[1], step)
                continue

            # surgeon conflict
            conflict_end = None
            for s in team:
                sc = _first_conflict(surg_cal.get(s, []), surg_interval[0], surg_interval[1])
                if sc is not None:
                    conflict_end = sc[1] if conflict_end is None else min(conflict_end, sc[1])
            if conflict_end is not None:
                t = _round_up(conflict_end, step)
                continue

            # feasible: commit
            _insert_interval(room_cal.setdefault(room, []), room_interval[0], room_interval[1])
            for s in team:
                _insert_interval(surg_cal.setdefault(s, []), surg_interval[0], surg_interval[1])

            day = t // sim.MINUTES_PER_DAY
            tod = t % sim.MINUTES_PER_DAY
            scheduled_rows.append({
                "case_id": cid,
                "case_type": ctype,
                "surgery_type": stype,
                "arrival": float(arrival),
                "start": float(t),
                "wait": float(t - arrival),  # Waiting time
                "room": int(room),
                "main": team[0] if len(team) > 0 else "",
                "assist1": team[1] if len(team) > 1 else "",
                "assist2": team[2] if len(team) > 2 else "",
                "day": int(day),
                "time_hhmm": minutes_to_hhmm_in_day(int(tod)),
            })
            break

        else:
            # unscheduled within horizon: push beyond week (counts as next-week delayed if elective)
            t2 = time_limit + 1
            day = t2 // sim.MINUTES_PER_DAY
            tod = t2 % sim.MINUTES_PER_DAY
            scheduled_rows.append({
                "case_id": cid,
                "case_type": ctype,
                "surgery_type": stype,
                "arrival": float(arrival),
                "start": float(t2),
                "wait": float(t2 - arrival),  # Waiting time
                "room": int(room),
                "main": team[0] if len(team) > 0 else "",
                "assist1": team[1] if len(team) > 1 else "",
                "assist2": team[2] if len(team) > 2 else "",
                "day": int(day),
                "time_hhmm": minutes_to_hhmm_in_day(int(tod)),
            })

    out_df = pd.DataFrame(scheduled_rows).sort_values(["start", "case_type", "case_id"]).reset_index(drop=True)
    return out_df


# ----------------------------
# GA operators
# ----------------------------
def tournament_select(pop: List[GAIndividual], k: int, rnd: random.Random) -> GAIndividual:
    cand = rnd.sample(pop, k=min(k, len(pop)))
    return min(cand, key=lambda x: x.fitness if x.fitness is not None else float("inf"))


def crossover(p1: GAIndividual, p2: GAIndividual, rnd: random.Random) -> Tuple[GAIndividual, GAIndividual]:
    keys = sorted(p1.delta_by_case.keys())
    c1 = clone_ind(p1)
    c2 = clone_ind(p2)
    for cid in keys:
        if rnd.random() < 0.5:
            c1.delta_by_case[cid], c2.delta_by_case[cid] = c2.delta_by_case[cid], c1.delta_by_case[cid]
        if rnd.random() < 0.5:
            c1.room_by_case[cid], c2.room_by_case[cid] = c2.room_by_case[cid], c1.room_by_case[cid]
    return c1, c2


def mutate(
    ind: GAIndividual,
    rnd: random.Random,
    step: int = 5,
    p_delta: float = 0.7,
    p_room: float = 0.3,
    delta_max_abs: int = 180,
) -> None:
    keys = list(ind.delta_by_case.keys())
    if not keys:
        return
    # delta mutation
    if rnd.random() < p_delta:
        cid = rnd.choice(keys)
        jump = rnd.choice([-6,-5,-4,-3,-2,-1,1,2,3,4,5,6]) * step
        newv = int(ind.delta_by_case.get(cid, 0) + jump)
        newv = max(-delta_max_abs, min(delta_max_abs, newv))
        ind.delta_by_case[cid] = newv

    # room mutation
    if rnd.random() < p_room:
        cid = rnd.choice(keys)
        max_room = max(ind.room_by_case.values()) if ind.room_by_case else 1
        if max_room >= 2:
            cur = int(ind.room_by_case.get(cid, 1))
            choices = [r for r in range(1, max_room+1) if r != cur]
            if choices:
                ind.room_by_case[cid] = rnd.choice(choices)


# ----------------------------
# Main GA loop
# ----------------------------
def run_ga_for_scenario(
    elective_input_df: pd.DataFrame,
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
    Returns: (best_full_schedule_df, best_metrics, baseline_metrics)
    """
    rnd = random.Random(seed_ga)

    urgent_list = generate_urgent_list(mean_interarrival, seed=scenario_seed)

    # Baseline: rule-based full schedule (elective+urgent)
    baseline_full_df, baseline_metrics = get_rule_based_baseline(
        work_schedule_path=work_schedule_path,
        cap_rank_path=cap_rank_path,
        elective_input_df=elective_input_df,
        urgent_list=urgent_list,
        rest_time=rest_time,
        max_reschedule_weeks=max_reschedule_weeks,
        penalty_next_week=penalty_next_week,
        seed=scenario_seed,
    )

    # Load work/cap once (for decoding + metrics)
    df_work = sim.load_work_schedule_xlsx(work_schedule_path)
    surgeons = [f"S{i}" for i in range(1, 13)]
    work = sim.WorkSchedule(df_work, surgeons)
    cap = sim.load_cap_rank_xlsx(cap_rank_path)

    # Build baseline individual
    baseline_full_df = baseline_full_df.copy()
    baseline_full_df["case_id"] = baseline_full_df["case_id"].astype(str)

    case_ids = baseline_full_df["case_id"].tolist()
    base_start = {str(r["case_id"]): int(float(r["start"])) for _, r in baseline_full_df.iterrows()}
    base_room = {str(r["case_id"]): int(r["room"]) for _, r in baseline_full_df.iterrows()}

    baseline_ind = GAIndividual(
        delta_by_case={cid: 0 for cid in case_ids},
        room_by_case=dict(base_room),
    )

    # fitness cache
    cache: Dict[str, Tuple[float, dict, pd.DataFrame]] = {}

    def evaluate(ind: GAIndividual) -> Tuple[float, dict, pd.DataFrame]:
        k = key_of(ind)
        if k in cache:
            f, m, df_sched = cache[k]
            return f, m, df_sched

        sched_df = decode_full_schedule_df(
            baseline_df=baseline_full_df,
            ind=ind,
            work=work,
            cap=cap,
            rest_time=rest_time,
            max_reschedule_weeks=max_reschedule_weeks,
            step=5,
        )

        metrics = compute_metrics_from_schedule(
            schedule_df=sched_df,
            work=work,
            cap=cap,
            rest_time=rest_time,
            max_reschedule_weeks=max_reschedule_weeks,
            penalty_next_week=penalty_next_week,
            n_rooms=int(max(ind.room_by_case.values()) if ind.room_by_case else 1),
            surgeons=surgeons,
            urgent_total=len(urgent_list),
        )

        # shift penalty vs baseline start times (both elective+urgent)
        shift = 0.0
        for cid, delta in ind.delta_by_case.items():
            # baseline start + delta is desired, but realized could differ; penalize realized deviation from baseline
            new_start = float(sched_df.loc[sched_df["case_id"] == cid, "start"].iloc[0])
            shift += abs(new_start - float(base_start[cid]))

        obj = (
            w_urgent * float(metrics["urgent_wait_weighted"])
            + w_elective_delay * float(metrics["elective_delay_total"])
            + w_overtime * float(metrics["overtime_total"])
            + w_next_week * float(metrics["elective_delayed_next_week"] * penalty_next_week)
            + w_shift * float(shift)
        )

        cache[k] = (float(obj), metrics, sched_df)
        return float(obj), metrics, sched_df

    # Initialize population
    pop: List[GAIndividual] = []
    pop.append(clone_ind(baseline_ind))
    while len(pop) < pop_size:
        x = clone_ind(baseline_ind)
        # apply a few random mutations to diversify
        for _ in range(rnd.randint(1, 6)):
            mutate(x, rnd=rnd)
        pop.append(x)

    # CRITICAL: Evaluate initial population BEFORE GA loop
    best_obj = float("inf")
    best_df = None
    best_metrics = None
    best_ind = None
    
    print("Evaluating initial population...")
    for ind in pop:
        obj, metrics, df_sched = evaluate(ind)
        ind.fitness = obj
        ind.metrics = metrics
        if obj < best_obj:
            best_obj, best_df, best_metrics, best_ind = obj, df_sched, metrics, clone_ind(ind)
    
    print(f"Initial best fitness: {best_obj:.2f}")
    print(f"  Baseline metrics: urgent_wait={best_metrics['urgent_wait_total']:.1f}, elective_delay={best_metrics['elective_delay_total']:.1f}")

    # GA loop
    for g in range(1, gens + 1):
        # elitism
        pop.sort(key=lambda x: x.fitness if x.fitness is not None else float("inf"))
        new_pop = [clone_ind(pop[0]), clone_ind(pop[1])] if len(pop) >= 2 else [clone_ind(pop[0])]

        while len(new_pop) < pop_size:
            p1 = tournament_select(pop, k=tournament_k, rnd=rnd)
            p2 = tournament_select(pop, k=tournament_k, rnd=rnd)
            c1, c2 = clone_ind(p1), clone_ind(p2)
            if rnd.random() < cx_rate:
                c1, c2 = crossover(p1, p2, rnd=rnd)
            if rnd.random() < mut_rate:
                mutate(c1, rnd=rnd)
            if rnd.random() < mut_rate:
                mutate(c2, rnd=rnd)

            new_pop.append(c1)
            if len(new_pop) < pop_size:
                new_pop.append(c2)

        pop = new_pop

        # Evaluate
        for ind in pop:
            obj, metrics, df_sched = evaluate(ind)
            ind.fitness = obj
            ind.metrics = metrics
            if obj < best_obj:
                best_obj, best_df, best_metrics, best_ind = obj, df_sched, metrics, clone_ind(ind)

    assert best_df is not None and best_metrics is not None
    return best_df, best_metrics, baseline_metrics


def main():
    # Auto-detect script directory for file paths
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    ap = argparse.ArgumentParser()
    ap.add_argument("--work_schedule", default=os.path.join(script_dir, "lich_lam_viec_tuan1.xlsx"))
    ap.add_argument("--cap_rank", default=os.path.join(script_dir, "Cap_Rank.xlsx"))
    ap.add_argument("--elective_sched", default=os.path.join(script_dir, "surgery_schedule.xlsx"))

    ap.add_argument("--scenario_seed", type=int, default=1, help="urgent scenario seed (per-scenario GA)")
    ap.add_argument("--mean_urgent", type=float, default=sim.DEFAULT_MEAN_INTERARRIVAL_URGENT)

    # GA params
    ap.add_argument("--pop", type=int, default=80)
    ap.add_argument("--gens", type=int, default=80)
    ap.add_argument("--cx", type=float, default=0.85)
    ap.add_argument("--mut", type=float, default=0.35)
    ap.add_argument("--tourn", type=int, default=3)
    ap.add_argument("--ga_seed", type=int, default=123)

    # sim params
    ap.add_argument("--rest_time", type=int, default=sim.DEFAULT_REST_TIME_MIN)
    ap.add_argument("--max_weeks", type=int, default=1, help="Max weeks for rescheduling (default=1 for 2-week total simulation)")
    ap.add_argument("--penalty_next_week", type=int, default=sim.DEFAULT_PENALTY_DELAY_NEXT_WEEK)

    # objective weights (STRONGLY prioritize patient waiting time)
    ap.add_argument("--w_urgent", type=float, default=10.0, help="Weight for urgent waiting time (priority-weighted)")
    ap.add_argument("--w_elective_delay", type=float, default=8.0, help="Weight for elective delay")
    ap.add_argument("--w_overtime", type=float, default=1.0, help="Weight for surgeon overtime")
    ap.add_argument("--w_next_week", type=float, default=1.0)
    ap.add_argument("--w_shift", type=float, default=0.01)

    args = ap.parse_args()

    elective_df = sim.load_elective_schedule_xlsx(args.elective_sched, return_df=True)

    best_df, best_metrics, baseline_metrics = run_ga_for_scenario(
        elective_input_df=elective_df,
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

    # Generate urgent arrivals info
    urgent_list = generate_urgent_list(mean_interarrival=args.mean_urgent, seed=args.scenario_seed)
    urgent_arrivals_rows = []
    for i, (t, stype) in enumerate(urgent_list, 1):
        day = int(t // sim.MINUTES_PER_DAY)
        tod = int(t % sim.MINUTES_PER_DAY)
        urgent_arrivals_rows.append({
            "urgent_id": f"U{i:04d}",
            "surgery_type": stype,
            "arrival_time": float(t),
            "day": day,
            "time_hhmm": minutes_to_hhmm_in_day(tod),
        })
    urgent_arrivals_df = pd.DataFrame(urgent_arrivals_rows)
    
    # Save to Excel with multiple sheets
    with pd.ExcelWriter(out_sched, engine='openpyxl') as writer:
        best_df.to_excel(writer, sheet_name='Schedule', index=False)
        urgent_arrivals_df.to_excel(writer, sheet_name='Urgent Arrivals', index=False)

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
        },
    }
    with open(out_cmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("Wrote:", out_sched)
    print("Wrote:", out_cmp)
    
    # Display detailed waiting time metrics
    print("\n" + "="*80)
    print("BASELINE METRICS:")
    print("="*80)
    print(f"Urgent cases: {baseline_metrics['urgent_arrived']} arrived, {baseline_metrics['urgent_started']} started")
    if baseline_metrics['urgent_started'] > 0:
        avg_urgent_wait = baseline_metrics['urgent_wait_total'] / baseline_metrics['urgent_started']
        print(f"  Avg urgent wait: {avg_urgent_wait:.1f} minutes ({avg_urgent_wait/60:.1f} hours)")
    print(f"  Total urgent wait: {baseline_metrics['urgent_wait_total']:.1f} minutes")
    print(f"  Weighted urgent wait: {baseline_metrics['urgent_wait_weighted']:.1f}")
    
    print(f"\nElective cases: {baseline_metrics['elective_started']} started")
    if baseline_metrics['elective_started'] > 0:
        avg_elec_delay = baseline_metrics['elective_delay_total'] / baseline_metrics['elective_started']
        print(f"  Avg elective delay: {avg_elec_delay:.1f} minutes ({avg_elec_delay/60:.1f} hours)")
    print(f"  Total elective delay: {baseline_metrics['elective_delay_total']:.1f} minutes")
    
    print(f"\nOther: Overtime={baseline_metrics['overtime_total']} min, Delayed to next week={baseline_metrics['elective_delayed_next_week']}")
    
    # Calculate baseline objective
    baseline_obj = (
        args.w_urgent * baseline_metrics['urgent_wait_weighted'] +
        args.w_elective_delay * baseline_metrics['elective_delay_total'] +
        args.w_overtime * baseline_metrics['overtime_total']
    )
    print(f"\nTotal Objective: {baseline_obj:.2f} (weighted sum)")
    
    print("\n" + "="*80)
    print("GA BEST METRICS:")
    print("="*80)
    print(f"Urgent cases: {best_metrics['urgent_arrived']} arrived, {best_metrics['urgent_started']} started")
    if best_metrics['urgent_started'] > 0:
        avg_urgent_wait = best_metrics['urgent_wait_total'] / best_metrics['urgent_started']
        print(f"  Avg urgent wait: {avg_urgent_wait:.1f} minutes ({avg_urgent_wait/60:.1f} hours)")
    print(f"  Total urgent wait: {best_metrics['urgent_wait_total']:.1f} minutes")
    print(f"  Weighted urgent wait: {best_metrics['urgent_wait_weighted']:.1f}")
    
    print(f"\nElective cases: {best_metrics['elective_started']} started")
    if best_metrics['elective_started'] > 0:
        avg_elec_delay = best_metrics['elective_delay_total'] / best_metrics['elective_started']
        print(f"  Avg elective delay: {avg_elec_delay:.1f} minutes ({avg_elec_delay/60:.1f} hours)")
    print(f"  Total elective delay: {best_metrics['elective_delay_total']:.1f} minutes")
    
    print(f"\nOther: Overtime={best_metrics['overtime_total']} min, Delayed to next week={best_metrics['elective_delayed_next_week']}")
    
    # Calculate total objective (same weights as GA)
    best_obj = (
        args.w_urgent * best_metrics['urgent_wait_weighted'] +
        args.w_elective_delay * best_metrics['elective_delay_total'] +
        args.w_overtime * best_metrics['overtime_total']
    )
    
    print(f"\nTotal Objective: {best_obj:.2f} (weighted sum)")
    
    # Show improvement
    print("\n" + "="*80)
    print("IMPROVEMENT:")
    print("="*80)
    urgent_improvement = baseline_metrics['urgent_wait_total'] - best_metrics['urgent_wait_total']
    elective_improvement = baseline_metrics['elective_delay_total'] - best_metrics['elective_delay_total']
    obj_improvement = baseline_obj - best_obj
    
    print(f"Urgent wait: {urgent_improvement:+.1f} minutes ({urgent_improvement*100/max(baseline_metrics['urgent_wait_total'],1):+.1f}%)")
    print(f"Elective delay: {elective_improvement:+.1f} minutes ({elective_improvement*100/max(baseline_metrics['elective_delay_total'],1):+.1f}%)")
    print(f"\nTotal Objective: {obj_improvement:+.2f} ({obj_improvement*100/max(baseline_obj,1):+.2f}%)")
    print(f"  Baseline: {baseline_obj:.2f}")
    print(f"  GA Best:  {best_obj:.2f}")
    print("="*80)


if __name__ == "__main__":
    main()
