
import simpy
import random
import csv
import argparse
import sys
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set

# -------------------------
# GLOBAL CONFIG
# -------------------------
MINUTES_PER_DAY = 24 * 60
WEEK_LENGTH = 7 * MINUTES_PER_DAY

ADMIN_SHIFT_START_HOUR = 8
ADMIN_SHIFT_END_HOUR = 16
ADMIN_SHIFT_START = ADMIN_SHIFT_START_HOUR * 60
ADMIN_SHIFT_END = ADMIN_SHIFT_END_HOUR * 60
ADMIN_DAYS = {0, 1, 2, 3, 4}  # Mon..Fri (0-based)

NUM_OPERATING_ROOMS = 2

# How long surgeons stay occupied after surgery (minutes)
REST_TIME_MIN = 15

# Urgent arrival process (mean inter-arrival in minutes)
MEAN_INTER_ARRIVAL_URGENT = 2520

# How many weeks ahead we allow rescheduling electives (safety)
MAX_RESCHEDULE_WEEKS_AHEAD = 8

# Penalty for pushing an elective to next week (for KPI, not optimization)
PENALTY_DELAY_NEXT_WEEK = 10_000

# Priority: lower number = higher priority in SimPy
PRIORITY_URGENT = 0
PRIORITY_ELECTIVE = 5

# -------------------------
# SURGERY DATA (EDIT LATER WITH YOUR REAL DATA)
# -------------------------
SURGERY_DURATION = {
    "adenotonsillectomy": 60,
    "microlaryngoscopy": 65,
    "septoplasty": 90,
    "thyroidectomy": 160,
    "buccal mucosa bioppsy": 30,
    "excision of the lymphadenopathy from the lumbar": 30,
    "modified radical mastoidectomy": 100,
    "rhinoplasty": 90,
    "endoscopic sinus": 65,
    "sleep apnea diagnosis test": 30,
}

# Prep time (room cleaning) after surgery by type (minutes).
# Replace this with your real prep data.
def prep_time_for_type(surgery_type: str) -> int:
    dur = SURGERY_DURATION.get(surgery_type, 60)
    # example rule-of-thumb: longer surgeries -> longer cleaning
    return 15 if dur >= 90 else 10

# -------------------------
# SURGEON SKILL DATA
# -------------------------
SURGEONS = {
    "S1": {
        "can_main":   {"sleep apnea diagnosis test"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar",
                       "septoplasty", "endoscopic sinus"},
    },
    "S2": {
        "can_main":   {"sleep apnea diagnosis test"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar",
                       "septoplasty", "endoscopic sinus"},
    },
    "S3": {
        "can_main":   {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy",
                       "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy", "rhinoplasty"},
    },
    "S4": {
        "can_main":   {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy",
                       "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy", "rhinoplasty"},
    },
    "S5": {
        "can_main":   {"rhinoplasty", "endoscopic sinus"},
        "can_assist": set(),
    },
    "S6": {
        "can_main":   {"modified radical mastoidectomy", "thyroidectomy"},
        "can_assist": set(),
    },
    "S7": {
        "can_main":   set(),
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy"},
    },
    "S8": {
        "can_main":   set(),
        "can_assist": {"rhinoplasty", "endoscopic sinus"},
    },
    "S9": {
        "can_main":   set(),
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy",
                       "excision of the lymphadenopathy from the lumbar", "septoplasty"},
    },
    "S10": {
        "can_main":   set(),
        "can_assist": {"sleep apnea diagnosis test"},
    },
}

ASSIST2_POOL = {f"S{i}" for i in range(7, 11)}  # S7..S10 only

# -------------------------
# UTILITIES
# -------------------------
def hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)

def minutes_to_hhmm(m: int) -> str:
    h = (m // 60) % 24
    mm = m % 60
    return f"{h:02d}:{mm:02d}"

def weekday_of(t: float) -> int:
    return int(t // MINUTES_PER_DAY) % 7  # 0..6

def time_in_day(t: float) -> int:
    return int(t % MINUTES_PER_DAY)

def is_admin_time(t: float) -> bool:
    wd = weekday_of(t)
    if wd not in ADMIN_DAYS:
        return False
    tod = time_in_day(t)
    return ADMIN_SHIFT_START <= tod < ADMIN_SHIFT_END

def admin_day_start_abs(week_start: int, day: int) -> int:
    return week_start + day * MINUTES_PER_DAY + ADMIN_SHIFT_START

def admin_day_end_abs(week_start: int, day: int) -> int:
    return week_start + day * MINUTES_PER_DAY + ADMIN_SHIFT_END

def next_business_day_abs(t: int) -> int:
    """Return absolute start time (08:00) of the next business day after time t."""
    # step day by day until we hit Mon..Fri
    day = int(t // MINUTES_PER_DAY)
    while True:
        day += 1
        wd = day % 7
        if wd in ADMIN_DAYS:
            return day * MINUTES_PER_DAY + ADMIN_SHIFT_START

def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or a_start >= b_end)

def interval_intersection_len(a: Tuple[int,int], b: Tuple[int,int]) -> int:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    return max(0, e - s)

# -------------------------
# INPUT DATA STRUCTURES
# -------------------------
@dataclass
class OnCallShift:
    shift_id: str
    start_min_week: int  # minutes from week start (0..)
    end_min_week: int    # can exceed WEEK_LENGTH for wrap
    surgeons: Set[str]

@dataclass
class ElectiveCase:
    pid: str
    surgery_type: str
    planned_start: int
    scheduled_start: int
    room: int
    main: str
    assist1: str
    assist2: str
    status: str = "scheduled"   # scheduled/executing/completed
    delayed_to_next_week: bool = False
    reschedule_count: int = 0

    def duration(self) -> int:
        return int(SURGERY_DURATION[self.surgery_type])

    def prep(self) -> int:
        return int(prep_time_for_type(self.surgery_type))

# -------------------------
# CSV LOADERS
# -------------------------
def load_oncall_roster(path: str) -> List[OnCallShift]:
    shifts: List[OnCallShift] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["shift_id"].strip()
            sd = int(row["start_day"])
            ed = int(row["end_day"])
            sh = hhmm_to_minutes(row["start_hhmm"])
            eh = hhmm_to_minutes(row["end_hhmm"])
            start_min = sd * MINUTES_PER_DAY + sh
            end_min = ed * MINUTES_PER_DAY + eh
            surgeons_raw = row.get("oncall_surgeons","").strip()
            surgeons = {s.strip() for s in surgeons_raw.split(";") if s.strip()}
            shifts.append(OnCallShift(sid, start_min, end_min, surgeons))
    return shifts

def load_elective_schedule(path: str) -> List[ElectiveCase]:
    cases: List[ElectiveCase] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["pid"].strip()
            stype = row["surgery_type"].strip()
            day = int(row["day"])
            t_hhmm = row["time_hhmm"].strip()
            room = int(row["room"])
            main = row["main"].strip()
            a1 = row["assist1"].strip()
            a2 = row["assist2"].strip()

            planned_start = day * MINUTES_PER_DAY + hhmm_to_minutes(t_hhmm)  # week 0 baseline (0-based)
            cases.append(ElectiveCase(
                pid=pid, surgery_type=stype,
                planned_start=planned_start,
                scheduled_start=planned_start,
                room=room, main=main, assist1=a1, assist2=a2
            ))
    # sort by planned time
    cases.sort(key=lambda c: c.planned_start)
    return cases

# -------------------------
# ROSTER HELPERS
# -------------------------
class RosterManager:
    """
    Handles:
    - Which surgeons are on-call at time t (outside admin hours)
    - Compensatory day-off after weekday night shift (no elective duty next business day)
    """
    def __init__(self, shifts: List[OnCallShift]):
        self.shifts = shifts
        self._comp_cache: Dict[int, Dict[str, List[Tuple[int,int]]]] = {}  # week_idx -> surgeon -> intervals

    def active_shifts_at(self, t: int) -> List[Tuple[OnCallShift,int,int]]:
        """
        Return list of (shift, abs_start, abs_end) active at absolute time t.
        We check both current week and previous week to handle wrap-around shifts.
        """
        week_idx = t // WEEK_LENGTH
        candidates = []
        for base_week_idx in [week_idx, week_idx - 1]:
            week_start = base_week_idx * WEEK_LENGTH
            for sh in self.shifts:
                abs_start = week_start + sh.start_min_week
                abs_end = week_start + sh.end_min_week
                if abs_start <= t < abs_end:
                    candidates.append((sh, abs_start, abs_end))
        return candidates

    def oncall_surgeons_at(self, t: int) -> Set[str]:
        surgeons: Set[str] = set()
        for sh, _, _ in self.active_shifts_at(t):
            surgeons |= sh.surgeons
        return surgeons

    def _compute_comp_intervals_for_week(self, week_idx: int) -> Dict[str, List[Tuple[int,int]]]:
        """
        For each WEEKDAY_NIGHT shift (Mon-Fri 16:00->08:00 next day),
        surgeons in that shift get next business day off from elective (08:00-16:00).
        """
        week_start = week_idx * WEEK_LENGTH
        comp: Dict[str, List[Tuple[int,int]]] = {s: [] for s in SURGEONS.keys()}

        for sh in self.shifts:
            # Detect weekday night shift pattern: start_day in [0..4], start=16:00, end=08:00 next day
            start_day = sh.start_min_week // MINUTES_PER_DAY
            end_day = sh.end_min_week // MINUTES_PER_DAY
            start_tod = sh.start_min_week % MINUTES_PER_DAY
            end_tod = sh.end_min_week % MINUTES_PER_DAY

            is_weekday_night = (
                start_day in {0,1,2,3,4} and
                end_day == start_day + 1 and
                start_tod == 16*60 and
                end_tod == 8*60
            )
            if not is_weekday_night:
                continue

            shift_end_abs = week_start + sh.end_min_week  # absolute time (08:00 next day)
            # next business day after shift end (could be same day if Tue-Fri at 08:00; or next Mon after Fri night)
            # If shift ends on Tue-Fri at 08:00, the "next business day" is that same weekday (start at 08:00).
            # So we use the date of shift_end_abs (not +1 day) if it is business day.
            end_day_abs = int(shift_end_abs // MINUTES_PER_DAY)
            end_wd = end_day_abs % 7
            if end_wd in ADMIN_DAYS:
                comp_start = end_day_abs * MINUTES_PER_DAY + ADMIN_SHIFT_START
            else:
                comp_start = next_business_day_abs(shift_end_abs - 1)  # after weekend -> Monday 08:00

            comp_end = comp_start + (ADMIN_SHIFT_END - ADMIN_SHIFT_START)
            for s in sh.surgeons:
                if s in comp:
                    comp[s].append((comp_start, comp_end))

        # merge intervals per surgeon (optional)
        for s, intervals in comp.items():
            intervals.sort()
            merged: List[Tuple[int,int]] = []
            for a,b in intervals:
                if not merged or a > merged[-1][1]:
                    merged.append((a,b))
                else:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            comp[s] = merged
        return comp

    def comp_intervals(self, t: int) -> Dict[str, List[Tuple[int,int]]]:
        """Return cached comp intervals for the week of time t."""
        week_idx = t // WEEK_LENGTH
        if week_idx not in self._comp_cache:
            self._comp_cache[week_idx] = self._compute_comp_intervals_for_week(week_idx)
        return self._comp_cache[week_idx]

    def is_on_comp_day_off(self, surgeon: str, t: int) -> bool:
        """True if t is within any compensatory off interval for surgeon."""
        week_idx = t // WEEK_LENGTH
        # check this week and previous week (Friday night can grant Monday next week)
        for wi in [week_idx, week_idx-1]:
            if wi not in self._comp_cache:
                self._comp_cache[wi] = self._compute_comp_intervals_for_week(wi)
            for a,b in self._comp_cache[wi].get(surgeon, []):
                if a <= t < b:
                    return True
        return False

# -------------------------
# SCHEDULING AVAILABILITY CHECKS
# -------------------------
def surgeon_has_skill_main(surgeon: str, surgery_type: str) -> bool:
    return surgery_type in SURGEONS[surgeon]["can_main"]

def surgeon_has_skill_assist(surgeon: str, surgery_type: str) -> bool:
    return surgery_type in SURGEONS[surgeon]["can_assist"]

def is_resource_free_now(res) -> bool:
    return (res.count < res.capacity) and (len(res.queue) == 0)

def is_team_free_now(team: Tuple[str,str,str], surgeon_res: Dict[str, simpy.PriorityResource]) -> bool:
    return all(is_resource_free_now(surgeon_res[s]) for s in team)

def is_room_free_now(room: int, room_res: Dict[int, simpy.PriorityResource]) -> bool:
    return is_resource_free_now(room_res[room])

def case_overlaps_room(case: ElectiveCase, room: int, start: int, end_room: int) -> bool:
    if case.status not in ("scheduled","executing"):
        return False
    if case.room != room:
        return False
    other_start = case.scheduled_start
    other_end = other_start + case.duration() + case.prep()
    return overlaps(start, end_room, other_start, other_end)

def case_overlaps_surgeon(case: ElectiveCase, surgeon: str, start: int, end_surgeon: int) -> bool:
    if case.status not in ("scheduled","executing"):
        return False
    team = {case.main, case.assist1, case.assist2}
    if surgeon not in team:
        return False
    other_start = case.scheduled_start
    other_end = other_start + case.duration() + REST_TIME_MIN
    return overlaps(start, end_surgeon, other_start, other_end)

def is_slot_feasible_for_elective(
    pid: str,
    start_time: int,
    case: ElectiveCase,
    all_cases: Dict[str, ElectiveCase],
    roster: RosterManager,
    allow_room_change: bool = False,
) -> bool:
    """
    Check if elective can start at start_time.
    - Must be in admin hours Mon-Fri
    - Surgeons must not be on compensatory off day
    - Must not overlap with other elective cases (room and surgeon usage)
    - Room fixed by case.room unless allow_room_change=True (not enabled by default)
    """
    if not is_admin_time(start_time):
        return False

    dur = case.duration()
    end_surgeon = start_time + dur + REST_TIME_MIN
    # Elective must finish surgeon workload within admin hours (C1 policy)
    if not is_admin_time(end_surgeon - 1):
        return False
    # Must remain in the same business day
    if int(start_time // MINUTES_PER_DAY) != int((end_surgeon - 1) // MINUTES_PER_DAY):
        return False

    # Comp day-off rule affects elective duty
    for s in [case.main, case.assist1, case.assist2]:
        if roster.is_on_comp_day_off(s, start_time):
            return False

    # Room busy includes cleaning (prep)
    end_room = start_time + dur + case.prep()

    room_candidates = [case.room] if not allow_room_change else list(range(1, NUM_OPERATING_ROOMS+1))
    for room in room_candidates:
        # check room overlap with other elective cases
        ok_room = True
        for other_pid, other in all_cases.items():
            if other_pid == pid:
                continue
            if case_overlaps_room(other, room, start_time, end_room):
                ok_room = False
                break
        if not ok_room:
            continue

        # check surgeon overlap
        ok_team = True
        for other_pid, other in all_cases.items():
            if other_pid == pid:
                continue
            for s in [case.main, case.assist1, case.assist2]:
                if case_overlaps_surgeon(other, s, start_time, end_surgeon):
                    ok_team = False
                    break
            if not ok_team:
                break

        if ok_team:
            # feasible with this room
            if allow_room_change:
                case.room = room
            return True

    return False

def find_earliest_elective_slot(
    env_now: int,
    case: ElectiveCase,
    all_cases: Dict[str, ElectiveCase],
    roster: RosterManager,
    max_weeks_ahead: int = MAX_RESCHEDULE_WEEKS_AHEAD,
) -> Optional[int]:
    """
    Search earliest feasible elective slot from env_now through:
    - remainder of current week admin windows
    - then next week, etc.
    """
    # start from current absolute time
    start_search = env_now

    for week_offset in range(max_weeks_ahead + 1):
        # Determine week_start for this search window
        base_week_start = ((start_search // WEEK_LENGTH) + week_offset) * WEEK_LENGTH

        # For week_offset==0, start searching from start_search
        # For later weeks, start from Monday 08:00
        search_from = start_search if week_offset == 0 else base_week_start

        # Iterate admin days Mon..Fri
        for day in range(5):
            day_start = admin_day_start_abs(base_week_start, day)
            day_end = admin_day_end_abs(base_week_start, day)
            t = max(day_start, search_from)
            latest_start = day_end - (case.duration() + REST_TIME_MIN)
            if t > latest_start:
                continue
            while t <= latest_start:
                if is_slot_feasible_for_elective(case.pid, t, case, all_cases, roster):
                    return t
                t += 1

    return None

# -------------------------
# MAIN SIMULATION PROCESSES
# -------------------------
def pick_urgent_triad_now(
    surgery_type: str,
    candidate_surgeons: Set[str],
    surgeon_res: Dict[str, simpy.PriorityResource],
) -> Optional[Tuple[str,str,str]]:
    """
    Pick a feasible urgent triad NOW:
    - main: must have can_main
    - assist1: must have can_assist
    - assist2: must be from S7..S10 (no skill check), must be in candidate set
    - All resources must be free now.
    """
    mains = [s for s in candidate_surgeons if surgeon_has_skill_main(s, surgery_type)]
    assists = [s for s in candidate_surgeons if surgeon_has_skill_assist(s, surgery_type)]
    if not mains or not assists:
        return None

    assist2_candidates = [s for s in candidate_surgeons if s in ASSIST2_POOL]
    if not assist2_candidates:
        return None

    # Try combinations (randomized)
    random.shuffle(mains)
    random.shuffle(assists)
    random.shuffle(assist2_candidates)

    for main in mains:
        if not is_resource_free_now(surgeon_res[main]):
            continue
        for a1 in assists:
            if a1 == main:
                continue
            if not is_resource_free_now(surgeon_res[a1]):
                continue
            for a2 in assist2_candidates:
                if a2 in {main, a1}:
                    continue
                if not is_resource_free_now(surgeon_res[a2]):
                    continue
                return (main, a1, a2)

    return None

def pick_room_now(room_res: Dict[int, simpy.PriorityResource]) -> Optional[int]:
    rooms = list(room_res.keys())
    random.shuffle(rooms)
    for r in rooms:
        if is_room_free_now(r, room_res):
            return r
    return None

def preempt_conflicting_electives(
    env_now: int,
    urgent_room: int,
    urgent_team: Tuple[str,str,str],
    urgent_type: str,
    urgent_room_end: int,
    urgent_surgeon_end: int,
    elective_cases: Dict[str, ElectiveCase],
    roster: RosterManager,
    stats: dict,
):
    """
    Proactively reschedule elective cases (status=scheduled) that overlap with urgent usage.
    No preempt of executing cases.
    """
    for pid, case in elective_cases.items():
        if case.status != "scheduled":
            continue

        # overlap check with urgent room interval
        case_room_end = case.scheduled_start + case.duration() + case.prep()
        case_surgeon_end = case.scheduled_start + case.duration() + REST_TIME_MIN

        room_conflict = (case.room == urgent_room) and overlaps(env_now, urgent_room_end, case.scheduled_start, case_room_end)

        team_set = {case.main, case.assist1, case.assist2}
        urgent_set = set(urgent_team)
        surgeon_conflict = False
        if team_set & urgent_set:
            surgeon_conflict = overlaps(env_now, urgent_surgeon_end, case.scheduled_start, case_surgeon_end)

        if room_conflict or surgeon_conflict:
            # reschedule this elective
            old_time = case.scheduled_start
            new_time = find_earliest_elective_slot(env_now, case, elective_cases, roster)
            if new_time is None:
                # push further weeks until found
                # (this should be rare if max_weeks_ahead is large enough)
                stats["elective_unresolved"].append(pid)
                continue

            case.scheduled_start = new_time
            case.reschedule_count += 1
            if new_time // WEEK_LENGTH > 0:
                case.delayed_to_next_week = True

            stats["elective_rescheduled"].append({
                "pid": pid,
                "from": old_time,
                "to": new_time,
                "reason": "Preempted by urgent"
            })

def urgent_generator(env, roster: RosterManager, surgeon_res, room_res, elective_cases, stats, arrival_horizon: int):
    uid = 0
    while True:
        inter = random.expovariate(1.0 / MEAN_INTER_ARRIVAL_URGENT)
        yield env.timeout(inter)
        if env.now >= arrival_horizon:
            break
        uid += 1
        stype = random.choice(list(SURGERY_DURATION.keys()))
        stats["urgent_arrived"] += 1
        env.process(urgent_case(env, f"U{uid:04d}", stype, roster, surgeon_res, room_res, elective_cases, stats))

def urgent_case(env, pid: str, surgery_type: str, roster: RosterManager, surgeon_res, room_res, elective_cases, stats):
    arrival = int(env.now)
    dur = int(SURGERY_DURATION[surgery_type])
    prep = int(prep_time_for_type(surgery_type))
    # Surgeons occupy duration + rest; room occupies duration + prep
    surgeon_end_offset = dur + REST_TIME_MIN
    room_end_offset = dur + prep

    started = False
    while not started:
        now = int(env.now)

        # Determine candidate pool:
        # - admin hours (Mon-Fri 08-16): any surgeon can handle urgent IF not on comp-day-off
        # - outside admin hours: only on-call surgeons from roster
        if is_admin_time(now):
            candidate = set(SURGEONS.keys())
            candidate = {s for s in candidate if not roster.is_on_comp_day_off(s, now)}
        else:
            candidate = roster.oncall_surgeons_at(now)

        triad = pick_urgent_triad_now(surgery_type, candidate, surgeon_res)
        room = pick_room_now(room_res)

        if triad is not None and room is not None:
            main, a1, a2 = triad

            # Priority requests
            req_main = surgeon_res[main].request(priority=PRIORITY_URGENT)
            req_a1   = surgeon_res[a1].request(priority=PRIORITY_URGENT)
            req_a2   = surgeon_res[a2].request(priority=PRIORITY_URGENT)
            req_room = room_res[room].request(priority=PRIORITY_URGENT)

            yield req_main & req_a1 & req_a2 & req_room

            start = int(env.now)
            started = True
            stats["urgent_served"] += 1
            wait = start - arrival

            # Proactively reschedule conflicting electives
            urgent_room_end = start + room_end_offset
            urgent_surgeon_end = start + surgeon_end_offset
            preempt_conflicting_electives(
                env_now=start,
                urgent_room=room,
                urgent_team=triad,
                urgent_type=surgery_type,
                urgent_room_end=urgent_room_end,
                urgent_surgeon_end=urgent_surgeon_end,
                elective_cases=elective_cases,
                roster=roster,
                stats=stats
            )

            # Log
            stats["log"].append({
                "pid": pid,
                "type": "URGENT",
                "surgery_type": surgery_type,
                "arrival": arrival,
                "start": start,
                "end_room": urgent_room_end,
                "end_surgeon": urgent_surgeon_end,
                "room": room,
                "main": main,
                "assist1": a1,
                "assist2": a2,
                "wait": wait,
            })

            # Occupy for surgery duration first
            yield env.timeout(dur)

            # Then cleanup/rest overlap
            extra_room = prep
            extra_surgeon = REST_TIME_MIN

            # After surgery finishes at time = start+dur
            # now we run overlap of extra times
            if extra_room >= extra_surgeon:
                # surgeons free first
                yield env.timeout(extra_surgeon)
                surgeon_res[main].release(req_main)
                surgeon_res[a1].release(req_a1)
                surgeon_res[a2].release(req_a2)
                yield env.timeout(extra_room - extra_surgeon)
                room_res[room].release(req_room)
            else:
                # room free first
                yield env.timeout(extra_room)
                room_res[room].release(req_room)
                yield env.timeout(extra_surgeon - extra_room)
                surgeon_res[main].release(req_main)
                surgeon_res[a1].release(req_a1)
                surgeon_res[a2].release(req_a2)

        else:
            # wait 1 minute and try again
            yield env.timeout(1)

def elective_case_process(env, case: ElectiveCase, roster: RosterManager, surgeon_res, room_res, all_cases: Dict[str, ElectiveCase], stats):
    """
    Manages one elective case through potential reschedules until completion.

    IMPORTANT IMPLEMENTATION NOTE:
    - We intentionally avoid putting elective requests into the Resource queue.
      If resources are not free NOW, we wait/reschedule and try again.
      This prevents "stuck queued requests" when an urgent case preempts.
    """
    while True:
        # Wait until its current scheduled time
        if env.now < case.scheduled_start:
            yield env.timeout(case.scheduled_start - env.now)

        if case.status == "completed":
            return

        now = int(env.now)

        # If current scheduled slot is not feasible (C1 constraints), find a new slot
        if not is_slot_feasible_for_elective(case.pid, now, case, all_cases, roster):
            new_time = find_earliest_elective_slot(now, case, all_cases, roster)
            if new_time is None:
                stats["elective_unresolved"].append(case.pid)
                return
            old = case.scheduled_start
            case.scheduled_start = new_time
            case.reschedule_count += 1
            if new_time // WEEK_LENGTH > 0:
                case.delayed_to_next_week = True
            stats["elective_rescheduled"].append({
                "pid": case.pid, "from": old, "to": new_time, "reason": "Auto-reschedule (infeasible slot)"
            })
            continue  # loop, will wait until new time

        # Check whether all required resources are free NOW.
        # If not, we wait 1 minute (if still within admin hours), otherwise we reschedule across the week.
        main, a1, a2 = case.main, case.assist1, case.assist2
        room = case.room

        resources_free = (
            is_resource_free_now(surgeon_res[main]) and
            is_resource_free_now(surgeon_res[a1]) and
            is_resource_free_now(surgeon_res[a2]) and
            is_resource_free_now(room_res[room])
        )

        if not resources_free:
            # If we are still inside admin time, wait 1 minute and retry.
            # If we are at/after the latest possible start time for today, reschedule.
            dur = case.duration()
            end_surgeon_if_start_now = now + dur + REST_TIME_MIN
            if is_admin_time(now) and is_admin_time(end_surgeon_if_start_now - 1):
                case.scheduled_start = now + 1  # slip forward minute-by-minute
                yield env.timeout(1)
                continue
            else:
                new_time = find_earliest_elective_slot(now, case, all_cases, roster)
                if new_time is None:
                    stats["elective_unresolved"].append(case.pid)
                    return
                old = case.scheduled_start
                case.scheduled_start = new_time
                case.reschedule_count += 1
                if new_time // WEEK_LENGTH > 0:
                    case.delayed_to_next_week = True
                stats["elective_rescheduled"].append({
                    "pid": case.pid, "from": old, "to": new_time, "reason": "Reschedule (resources busy)"
                })
                continue

        # Acquire resources (should be immediate because we checked free-now)
        req_main = surgeon_res[main].request(priority=PRIORITY_ELECTIVE)
        req_a1   = surgeon_res[a1].request(priority=PRIORITY_ELECTIVE)
        req_a2   = surgeon_res[a2].request(priority=PRIORITY_ELECTIVE)
        req_room = room_res[room].request(priority=PRIORITY_ELECTIVE)

        yield req_main & req_a1 & req_a2 & req_room

        start = int(env.now)

        # Re-check feasibility after acquiring (time might have advanced)
        if not is_slot_feasible_for_elective(case.pid, start, case, all_cases, roster):
            # Release and reschedule
            surgeon_res[main].release(req_main)
            surgeon_res[a1].release(req_a1)
            surgeon_res[a2].release(req_a2)
            room_res[room].release(req_room)

            new_time = find_earliest_elective_slot(start, case, all_cases, roster)
            if new_time is None:
                stats["elective_unresolved"].append(case.pid)
                return
            old = case.scheduled_start
            case.scheduled_start = new_time
            case.reschedule_count += 1
            if new_time // WEEK_LENGTH > 0:
                case.delayed_to_next_week = True
            stats["elective_rescheduled"].append({
                "pid": case.pid, "from": old, "to": new_time, "reason": "Reschedule after acquire (slot invalid)"
            })
            continue

        # Execute elective
        case.status = "executing"
        dur = case.duration()
        prep = case.prep()
        end_room = start + dur + prep
        end_surgeon = start + dur + REST_TIME_MIN

        stats["elective_served"] += 1
        stats["log"].append({
            "pid": case.pid,
            "type": "ELECTIVE",
            "surgery_type": case.surgery_type,
            "arrival": case.planned_start,
            "start": start,
            "end_room": end_room,
            "end_surgeon": end_surgeon,
            "room": room,
            "main": main,
            "assist1": a1,
            "assist2": a2,
            "wait": start - case.planned_start,
        })

        # Occupy resources with different release times
        yield env.timeout(dur)

        extra_room = prep
        extra_surgeon = REST_TIME_MIN

        if extra_room >= extra_surgeon:
            yield env.timeout(extra_surgeon)
            surgeon_res[main].release(req_main)
            surgeon_res[a1].release(req_a1)
            surgeon_res[a2].release(req_a2)
            yield env.timeout(extra_room - extra_surgeon)
            room_res[room].release(req_room)
        else:
            yield env.timeout(extra_room)
            room_res[room].release(req_room)
            yield env.timeout(extra_surgeon - extra_room)
            surgeon_res[main].release(req_main)
            surgeon_res[a1].release(req_a1)
            surgeon_res[a2].release(req_a2)

        case.status = "completed"
        return

# -------------------------
# METRICS
# -------------------------
def build_surgeon_duty_intervals(roster: RosterManager, sim_end: int) -> Dict[str, List[Tuple[int,int]]]:
    """
    Duty = admin shifts (Mon-Fri 08-16) EXCLUDING comp-day-off + oncall shifts from roster.
    """
    duty: Dict[str, List[Tuple[int,int]]] = {s: [] for s in SURGEONS.keys()}

    # weeks covered
    weeks = (sim_end // WEEK_LENGTH) + 2  # +2 for safety
    for week_idx in range(weeks):
        week_start = week_idx * WEEK_LENGTH

        # Admin duty windows
        for day in range(5):
            a = admin_day_start_abs(week_start, day)
            b = admin_day_end_abs(week_start, day)
            for s in duty.keys():
                # exclude compensatory off day
                if roster.is_on_comp_day_off(s, a):
                    continue
                duty[s].append((a,b))

        # Oncall duty windows (repeat roster weekly)
        for sh in roster.shifts:
            abs_start = week_start + sh.start_min_week
            abs_end = week_start + sh.end_min_week
            for s in sh.surgeons:
                if s in duty:
                    duty[s].append((abs_start, abs_end))

    # clip to sim_end and merge
    for s, intervals in duty.items():
        clipped = []
        for a,b in intervals:
            if b <= 0 or a >= sim_end:
                continue
            clipped.append((max(0,a), min(sim_end,b)))
        clipped.sort()
        merged = []
        for a,b in clipped:
            if not merged or a > merged[-1][1]:
                merged.append((a,b))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        duty[s] = merged

    return duty

def build_surgeon_busy_intervals(log: List[dict]) -> Dict[str, List[Tuple[int,int]]]:
    busy: Dict[str, List[Tuple[int,int]]] = {s: [] for s in SURGEONS.keys()}
    for rec in log:
        a = rec["start"]
        b = rec["end_surgeon"]
        for s in [rec["main"], rec["assist1"], rec["assist2"]]:
            if s in busy:
                busy[s].append((a,b))
    # merge per surgeon
    for s, intervals in busy.items():
        intervals.sort()
        merged = []
        for a,b in intervals:
            if not merged or a > merged[-1][1]:
                merged.append((a,b))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        busy[s] = merged
    return busy

def interval_total(intervals: List[Tuple[int,int]]) -> int:
    return sum(b-a for a,b in intervals)

def overlap_total(a_intervals: List[Tuple[int,int]], b_intervals: List[Tuple[int,int]]) -> int:
    i = j = 0
    total = 0
    while i < len(a_intervals) and j < len(b_intervals):
        a = a_intervals[i]
        b = b_intervals[j]
        total += interval_intersection_len(a,b)
        if a[1] < b[1]:
            i += 1
        else:
            j += 1
    return total

# -------------------------
# RUN
# -------------------------
def run(roster_csv: str, elective_csv: str, seed: int = 1):
    random.seed(seed)

    # Load data
    shifts = load_oncall_roster(roster_csv)
    roster = RosterManager(shifts)
    elective_list = load_elective_schedule(elective_csv)
    elective_cases: Dict[str, ElectiveCase] = {c.pid: c for c in elective_list}

    # SimPy environment
    env = simpy.Environment()

    # Priority resources
    surgeon_res = {s: simpy.PriorityResource(env, capacity=1) for s in SURGEONS.keys()}
    room_res = {r: simpy.PriorityResource(env, capacity=1) for r in range(1, NUM_OPERATING_ROOMS+1)}

    stats = {
        "urgent_arrived": 0,
        "urgent_served": 0,
        "elective_served": 0,
        "elective_rescheduled": [],
        "elective_unresolved": [],
        "log": [],
    }

    # Start elective case managers
    for case in elective_list:
        env.process(elective_case_process(env, case, roster, surgeon_res, room_res, elective_cases, stats))

    # Start urgent generator: arrivals only over 1 week, but service continues until queue cleared
    arrival_horizon = WEEK_LENGTH
    env.process(urgent_generator(env, roster, surgeon_res, room_res, elective_cases, stats, arrival_horizon=arrival_horizon))

    env.run()  # run until all events finish (arrivals stop after 1 week)

    # Determine sim end time from log
    sim_end = 0
    for rec in stats["log"]:
        sim_end = max(sim_end, rec["end_room"], rec["end_surgeon"])
    sim_end = int(sim_end)

    # Metrics
    duty = build_surgeon_duty_intervals(roster, sim_end)
    busy = build_surgeon_busy_intervals(stats["log"])

    surgeon_kpi = {}
    for s in SURGEONS.keys():
        duty_total = interval_total(duty[s])
        busy_total = interval_total(busy[s])
        busy_in_duty = overlap_total(busy[s], duty[s])
        unproductive = max(0, duty_total - busy_in_duty)
        overtime = max(0, busy_total - busy_in_duty)
        surgeon_kpi[s] = {
            "duty_total_min": duty_total,
            "busy_total_min": busy_total,
            "busy_in_duty_min": busy_in_duty,
            "unproductive_min": unproductive,
            "overtime_min": overtime,
        }

    urgent_waits = [rec["wait"] for rec in stats["log"] if rec["type"]=="URGENT"]
    elective_delays = [rec["wait"] for rec in stats["log"] if rec["type"]=="ELECTIVE"]

    delayed_next_week = [c for c in elective_cases.values() if c.delayed_to_next_week]
    penalty = len(delayed_next_week) * PENALTY_DELAY_NEXT_WEEK

    # Report
    print("="*90)
    print("SIMULATION SUMMARY")
    print("="*90)
    print(f"Urgent arrived:  {stats['urgent_arrived']}")
    print(f"Urgent served:   {stats['urgent_served']}")
    print(f"Elective served: {stats['elective_served']}")
    print(f"Elective pushed to next week: {len(delayed_next_week)} (penalty={penalty})")
    print("-"*90)
    if urgent_waits:
        print(f"Urgent waiting time (min): avg={sum(urgent_waits)/len(urgent_waits):.1f}, max={max(urgent_waits):.0f}")
    if elective_delays:
        print(f"Elective delay vs baseline (min): avg={sum(elective_delays)/len(elective_delays):.1f}, max={max(elective_delays):.0f}")
    print("-"*90)
    print("Top 5 surgeons by overtime:")
    top_ot = sorted(surgeon_kpi.items(), key=lambda kv: kv[1]["overtime_min"], reverse=True)[:5]
    for s, k in top_ot:
        print(f"  {s}: overtime={k['overtime_min']} min, unproductive={k['unproductive_min']} min, duty={k['duty_total_min']} min, busy={k['busy_total_min']} min")

    # Print a compact schedule
    print("="*90)
    print("COMPLETED SURGERY LOG (sorted by start)")
    print("="*90)
    log_sorted = sorted(stats["log"], key=lambda r: r["start"])
    for rec in log_sorted:
        start = rec["start"]
        day = int(start // MINUTES_PER_DAY)
        tod = minutes_to_hhmm(int(start % MINUTES_PER_DAY))
        print(f"{rec['pid']:>6s} {rec['type']:<8s} | day={day} {tod} | room={rec['room']} | "
              f"{rec['surgery_type']:<35.35s} | wait={rec['wait']:>4d} | "
              f"team=({rec['main']},{rec['assist1']},{rec['assist2']})")

    if stats["elective_rescheduled"]:
        print("="*90)
        print("ELECTIVE RESCHEDULE EVENTS (first 20)")
        print("="*90)
        for e in stats["elective_rescheduled"][:20]:
            print(f"{e['pid']} : {e['from']} -> {e['to']} | {e['reason']}")

    if stats["elective_unresolved"]:
        print("="*90)
        print("WARNING: UNRESOLVED ELECTIVES")
        print(stats["elective_unresolved"])

if __name__ == "__main__":
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--roster", default=os.path.join(script_dir, "oncall_roster_test.csv"), help="CSV file of on-call roster")
    parser.add_argument("--elective", default=os.path.join(script_dir, "elective_schedule_test.csv"), help="CSV file of elective schedule")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    run(args.roster, args.elective, seed=args.seed)
