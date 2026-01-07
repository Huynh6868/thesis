# -*- coding: utf-8 -*-
try:
    import simpy
except ImportError as e:
    raise ImportError('SimPy is required. Install it with: pip install simpy') from e
import random
import argparse
import sys
import os
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
import pandas as pd


# ------------------------------------------------------------
# GLOBAL CONFIG
# ------------------------------------------------------------
MINUTES_PER_DAY = 24 * 60
WEEK_LENGTH = 7 * MINUTES_PER_DAY

ADMIN_SHIFT_START = 8 * 60 #define thời gian như thế này có đúng không? 
ADMIN_SHIFT_END = 16 * 60

# Parameters
DEFAULT_MEAN_INTERARRIVAL_URGENT = 2520  # có thể cần sửa lại
DEFAULT_REST_TIME_MIN = 15              # cần input thêm data gốc
#DEFAULT_MAX_RESCHEDULE_WEEKS = 4 
DEFAULT_PENALTY_DELAY_NEXT_WEEK = 10000 # nhiêu đây được chưa 


def load_urgent_param_from_excel(cap_rank_path: str, scale: str) -> float:
    """
    Load urgent interarrival time parameter from Cap_Rank.xlsx urgent parameter sheet.
    
    Args:
        cap_rank_path: Path to Cap_Rank.xlsx
        scale: One of 'Small scale', 'Medium scale', 'Large scale'
    
    Returns:
        mean_interarrival_urgent in minutes
    """
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='urgent parameter')
        # Find row matching the scale
        row = df[df.iloc[:, 0].str.strip().str.lower() == scale.lower()]
        if row.empty:
            print(f"Warning: Scale '{scale}' not found in urgent parameter sheet. Using default.")
            return DEFAULT_MEAN_INTERARRIVAL_URGENT
        return float(row.iloc[0]['Inter arrival time'])
    except Exception as e:
        print(f"Error loading urgent parameter: {e}. Using default.")
        return DEFAULT_MEAN_INTERARRIVAL_URGENT


# ------------------------------------------------------------
# SURGERY DURATION & PREP 
# ------------------------------------------------------------
SURGERY_DURATION_MIN = {
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

PREP_TIME_MIN = {k: (15 if SURGERY_DURATION_MIN[k] >= 90 else 10) for k in SURGERY_DURATION_MIN.keys()}

# Map operation number in Cap_Rank.xlsx -> surgery_type string used in schedule
OPERATION_TO_TYPE = {
    1: "adenotonsillectomy",
    2: "microlaryngoscopy",
    3: "buccal mucosa bioppsy",
    4: "excision of the lymphadenopathy from the lumbar",
    5: "septoplasty",
    6: "modified radical mastoidectomy",
    7: "thyroidectomy",
    8: "rhinoplasty",
    9: "endoscopic sinus",
    10: "sleep apnea diagnosis test",
}

# NOTE: ASSIST2_POOL is deprecated - use cap.a2_by_type from Excel instead
# ASSIST2_POOL = {f"S{i}" for i in range(9, 13)}  # S9..S12


def load_room_config(cap_rank_path: str, scale: str = 'small') -> int:
    """Load room configuration from Cap_Rank.xlsx 'room' sheet."""
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='room')
        if 'Room' in df.columns:
            row = df[df.iloc[:, 0].str.strip().str.lower() == scale.lower()]
            if not row.empty:
                return int(row['Room'].iloc[0])
        if 'num_rooms' in df.columns:
            return int(df['num_rooms'].iloc[0])
        return 2  # default for small
    except Exception as e:
        print(f"Warning: Could not load room config from Excel: {e}. Using default (2 rooms)")
        return 2

def load_rest_time_map(cap_rank_path: str) -> Dict[str, Dict[str, int]]:
    """
    Load surgery-type and role-specific rest times from Cap_Rank.xlsx 'rest time' sheet.
    
    Args:
        cap_rank_path: Path to Cap_Rank.xlsx
    
    Returns:
        Dictionary mapping {surgery_type: {'main': X, 'assistant': Y}}
    """
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='rest time')
        rest_map = {}
        
        # Map from Operation number to surgery type
        for _, row in df.iterrows():
            op_num = int(row['Operation'])
            surgery_type = OPERATION_TO_TYPE.get(op_num)
            if surgery_type:
                main_val = None
                asst_val = None
                # Try different column name variations
                for col in df.columns:
                    col_stripped = col.strip()
                    if col_stripped.lower() == 'rest time main':
                        main_val = int(row[col])
                    elif col_stripped.lower() == 'rest time assistant':
                        asst_val = int(row[col])
                
                if main_val is not None and asst_val is not None:
                    rest_map[surgery_type] = {
                        'main': main_val,
                        'assistant': asst_val
                    }
        return rest_map
    except Exception as e:
        print(f"Warning: Could not load rest time map from Excel: {e}. Using default (15 min)")
        # Return default rest times for all surgery types
        return {stype: {'main': 15, 'assistant': 15} for stype in SURGERY_DURATION_MIN.keys()}


# ------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------
def hhmm_to_minutes(hhmm: str) -> int:
    hh, mm = hhmm.strip().split(":")
    return int(hh) * 60 + int(mm)

def minutes_to_hhmm(m: float) -> str:
    m_int = int(m)
    hh = (m_int // 60) % 24
    mm = m_int % 60
    return f"{hh:02d}:{mm:02d}"

def day_of_week(t: float) -> int:
    return int(math.floor(t) // MINUTES_PER_DAY) % 7  # 0=Mon..6=Sun

def time_in_day(t: float) -> int:
    return int(math.floor(t) % MINUTES_PER_DAY)

def is_admin_time(t: float) -> bool:
    wd = day_of_week(t)
    tod = time_in_day(t)
    return (0 <= wd <= 4) and (ADMIN_SHIFT_START <= tod < ADMIN_SHIFT_END)

def same_calendar_day(a: float, b: float) -> bool:
    return int(math.floor(a) // MINUTES_PER_DAY) == int(math.floor(b) // MINUTES_PER_DAY)

def merge_intervals(intervals: List[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for a,b in intervals[1:]:
        if a > merged[-1][1]:
            merged.append((a,b))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
    return merged

def interval_total(intervals: List[Tuple[int,int]]) -> int:
    return sum(b-a for a,b in intervals)

def intersection_len(a: Tuple[int,int], b: Tuple[int,int]) -> int:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    return max(0, e - s)

def overlap_total(a_intervals: List[Tuple[int,int]], b_intervals: List[Tuple[int,int]]) -> int:
    i = j = 0
    total = 0
    while i < len(a_intervals) and j < len(b_intervals):
        total += intersection_len(a_intervals[i], b_intervals[j])
        if a_intervals[i][1] < b_intervals[j][1]:
            i += 1
        else:
            j += 1
    return total

def normalize_cell(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).replace("\n", " ").strip()
    # normalize multiple spaces
    s = " ".join(s.split())
    return s

def parse_surgeon_code(x: str) -> Optional[str]:
    """
    Accepts formats like:
      "Surgeon 10" -> "S10"
      "S10" -> "S10"
      10 -> "S10"
    """
    if x is None:
        return None
    if isinstance(x, (int, float)) and not math.isnan(float(x)):
        return f"S{int(x)}"
    s = str(x).strip()
    if not s:
        return None
    if s.upper().startswith("S"):
        # S10
        return s.upper()
    # Surgeon 10
    m = None
    try:
        import re
        m = re.search(r"(\d+)", s)
    except Exception:
        m = None
    if m:
        return f"S{int(m.group(1))}"
    return None


# ------------------------------------------------------------
# DATA CLASSES
# ------------------------------------------------------------
@dataclass
class CapabilityModel:
    main_by_type: Dict[str, Set[str]] = field(default_factory=dict)
    a1_by_type: Dict[str, Set[str]] = field(default_factory=dict)
    a2_by_type: Dict[str, Set[str]] = field(default_factory=dict)
    rank_by_type: Dict[str, int] = field(default_factory=dict)

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
    status: str = "scheduled"  # scheduled/executing/completed
    delayed_weeks: int = 0

    def duration(self) -> int:
        return int(SURGERY_DURATION_MIN[self.surgery_type])

    def prep(self) -> int:
        return int(PREP_TIME_MIN[self.surgery_type])

@dataclass
class UrgentCase:
    uid: str
    surgery_type: str
    arrival_time: float
    arrival_bucket: int
    rank: int
    status: str = "waiting"    # waiting/executing/completed
    start_time: Optional[float] = None
    team: Optional[Tuple[str,str,Optional[str]]] = None
    room: Optional[int] = None
    used_team_size: int = 0

    def duration(self) -> int:
        return int(SURGERY_DURATION_MIN[self.surgery_type])

    def prep(self) -> int:
        return int(PREP_TIME_MIN[self.surgery_type])


# ------------------------------------------------------------
# WORK SCHEDULE (supports multi-week schedules)
# ------------------------------------------------------------
class WorkSchedule:
    """
    Provides duty availability for:
      - elective (admin time Mon-Fri)
      - urgent (admin time + on-call intervals)
    based on weekly schedule in Excel.
    Supports multi-week schedules.
    """
    def __init__(self, df_weeks: List[pd.DataFrame], surgeons: List[str]):
        """
        Args:
            df_weeks: List of DataFrames, one per week
            surgeons: List of surgeon IDs
        """
        self.surgeons = surgeons
        self.num_weeks = len(df_weeks)
        
        # Store schedule for each week separately
        # status_by_week_day[week][surgeon][day] = status
        self.status_by_week_day: Dict[int, Dict[str, Dict[int, str]]] = {}
        
        day_cols = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        
        # Process each week's DataFrame
        for week_idx, df_week in enumerate(df_weeks):
            self.status_by_week_day[week_idx] = {s: {} for s in surgeons}
            
            # Build mapping from excel doctor names to S-codes
            for _, row in df_week.iterrows():
                doc = row.get("Doctor", None)
                code = parse_surgeon_code(doc)
                if code is None or code not in self.status_by_week_day[week_idx]:
                    continue
                for d, col in enumerate(day_cols):
                    self.status_by_week_day[week_idx][code][d] = normalize_cell(row.get(col, ""))

        # Precompute duty intervals for each week and surgeon
        # week_duty_intervals[week][surgeon] = [(start, end), ...]
        self.week_duty_intervals: Dict[int, Dict[str, List[Tuple[int,int]]]] = {}
        self.week_oncall_intervals: Dict[int, Dict[str, List[Tuple[int,int]]]] = {}
        self.week_day_off: Dict[int, Dict[str, Set[int]]] = {}
        
        for week_idx in range(self.num_weeks):
            self.week_duty_intervals[week_idx] = {s: [] for s in surgeons}
            self.week_oncall_intervals[week_idx] = {s: [] for s in surgeons}
            self.week_day_off[week_idx] = {s: set() for s in surgeons}
            
            for s in surgeons:
                for d in range(7):
                    st = self.status_by_week_day[week_idx][s].get(d, "")
                    if "Day Off" in st:
                        self.week_day_off[week_idx][s].add(d)
                        continue

                    # Regular day duty 08:00-16:00
                    if ("Regular Hours" in st) or ("On-call" in st):
                        a = d * MINUTES_PER_DAY + ADMIN_SHIFT_START
                        b = d * MINUTES_PER_DAY + ADMIN_SHIFT_END
                        self.week_duty_intervals[week_idx][s].append((a,b))

                    # On-call evening: 16:00 -> next day 08:00
                    if "On-call (Evening)" in st:
                        a = d * MINUTES_PER_DAY + ADMIN_SHIFT_END
                        b = (d+1) * MINUTES_PER_DAY + ADMIN_SHIFT_START
                        self.week_duty_intervals[week_idx][s].append((a,b))
                        self.week_oncall_intervals[week_idx][s].append((a,b))

                    # On-call full day: 08:00 -> next day 08:00 (24h)
                    if "On-call (Full Day)" in st:
                        a = d * MINUTES_PER_DAY + ADMIN_SHIFT_START
                        b = (d+1) * MINUTES_PER_DAY + ADMIN_SHIFT_START
                        self.week_duty_intervals[week_idx][s].append((a,b))
                        self.week_oncall_intervals[week_idx][s].append((a,b))

                self.week_duty_intervals[week_idx][s] = merge_intervals(self.week_duty_intervals[week_idx][s])
                self.week_oncall_intervals[week_idx][s] = merge_intervals(self.week_oncall_intervals[week_idx][s])

    def is_day_off(self, surgeon: str, t: float) -> bool:
        """Check if surgeon is off on day at time t (uses correct week's schedule)"""
        week_idx = int(t // WEEK_LENGTH) % self.num_weeks
        d = day_of_week(t)
        return d in self.week_day_off.get(week_idx, {}).get(surgeon, set())

    def _in_intervals_week_specific(self, surgeon: str, t: float, use_oncall_only: bool = False) -> bool:
        """Check if surgeon is in duty/oncall intervals at time t using week-specific schedule"""
        week_idx = int(t // WEEK_LENGTH) % self.num_weeks
        intervals_rel = self.week_oncall_intervals.get(week_idx, {}).get(surgeon, []) if use_oncall_only else self.week_duty_intervals.get(week_idx, {}).get(surgeon, [])
        
        # Convert to absolute time for this specific week
        week_start = (t // WEEK_LENGTH) * WEEK_LENGTH
        for a_rel, b_rel in intervals_rel:
            a = week_start + a_rel
            b = week_start + b_rel
            if a <= t < b:
                return True
        
        # Check spillover from previous day (e.g., evening on-call ending next morning)
        if week_start > 0:
            for a_rel, b_rel in intervals_rel:
                a = week_start + a_rel
                b = week_start + b_rel
                if a < week_start and b > week_start and a <= t < b:
                    return True
        return False

    def on_duty_for_urgent(self, surgeon: str, t: float) -> bool:
        """
        Check if surgeon can handle urgent case at time t.
        - During admin time (Mon-Fri 08:00-16:00): Any non-day-off surgeon available
        - Outside admin time: ONLY on-call surgeons available
        """
        # During admin time, any surgeon who is NOT day off is considered available (day staff)
        if is_admin_time(t):
            return not self.is_day_off(surgeon, t)

        # Outside admin time (including evenings after 16:00), STRICTLY require on-call duty
        # This prevents assigning surgeons to urgent cases starting after 16:00 if they don't have on-call
        return self._in_intervals_week_specific(surgeon, t, use_oncall_only=True)

    def on_duty_for_elective(self, surgeon: str, t: float) -> bool:
        """Elective only in admin time; day off means not available"""
        return is_admin_time(t) and (not self.is_day_off(surgeon, t))

    def duty_intervals_abs(self, surgeon: str, sim_end: int) -> List[Tuple[int,int]]:
        """
        Build absolute duty intervals for surgeon, repeating weekly, clipped to [0, sim_end].
        Uses week-specific schedules correctly.
        """
        intervals: List[Tuple[int,int]] = []
        total_weeks = (sim_end // WEEK_LENGTH) + 2
        
        for week_iter in range(total_weeks):
            # Use the correct week's schedule (cycling through available weeks)
            week_idx = week_iter % self.num_weeks
            rel = self.week_duty_intervals.get(week_idx, {}).get(surgeon, [])
            ws = week_iter * WEEK_LENGTH  # Absolute start of this simulation week
            
            for a_rel, b_rel in rel:
                a = ws + a_rel
                b = ws + b_rel
                if b <= 0 or a >= sim_end:
                    continue
                intervals.append((max(0, a), min(sim_end, b)))
        return merge_intervals(intervals)


# ------------------------------------------------------------
# LOADING INPUT FILES
# ------------------------------------------------------------
def load_work_schedule_xlsx(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    # keep only rows with a valid doctor name
    df = df[df["Doctor"].notna()].copy()
    return df

def load_cap_rank_xlsx(path: str) -> CapabilityModel:
    df_cap = pd.read_excel(path, sheet_name="Capabilities")
    df_rank = pd.read_excel(path, sheet_name="Ranking")

    cap = CapabilityModel()

    def parse_list(s) -> Set[str]:
        if pd.isna(s):
            return set()
        txt = str(s).strip()
        if not txt:
            return set()
        parts = [p.strip() for p in txt.split(";") if p.strip()]
        out = set()
        for p in parts:
            try:
                out.add(f"S{int(p)}")
            except Exception:
                # allow S10 format too
                out.add(parse_surgeon_code(p))
        return {x for x in out if x}

    for _, row in df_cap.iterrows():
        op = int(row["Operation"])
        stype = OPERATION_TO_TYPE.get(op, None)
        if stype is None:
            continue
        cap.main_by_type[stype] = parse_list(row.get("Main surgeon", ""))
        cap.a1_by_type[stype] = parse_list(row.get("Assistant 1", ""))
        cap.a2_by_type[stype] = parse_list(row.get("Assistant 2", ""))

    for _, row in df_rank.iterrows():
        op = int(row["Operation"])
        stype = OPERATION_TO_TYPE.get(op, None)
        if stype is None:
            continue
        cap.rank_by_type[stype] = int(row["Ranking"])

    # sanity: ensure all types have rank (fallback large)
    for stype in SURGERY_DURATION_MIN.keys():
        if stype not in cap.rank_by_type:
            cap.rank_by_type[stype] = 999

    return cap

def load_elective_schedule_xlsx(path: str, return_df: bool = False):
    """
    Load elective schedule from Excel.
    """
    df = pd.read_excel(path, sheet_name=0)
    if return_df:
        # Return DataFrame for GA optimizer
        return df
    
    # Return List[ElectiveCase] for simulator (backward compatible)
    cases: List[ElectiveCase] = []
    for _, row in df.iterrows():
        pid = str(row["pid"]).strip()
        stype = str(row["surgery_type"]).strip()
        day = int(row["day"])
        hhmm = str(row["time_hhmm"]).strip()
        room = int(row["room"])
        main = parse_surgeon_code(row["main"])
        a1 = parse_surgeon_code(row["assist1"])
        a2 = parse_surgeon_code(row["assist2"])

        planned = day * MINUTES_PER_DAY + hhmm_to_minutes(hhmm)
        cases.append(ElectiveCase(
            pid=pid,
            surgery_type=stype,
            planned_start=planned,
            scheduled_start=planned,
            room=room,
            main=main,
            assist1=a1,
            assist2=a2,
        ))
    cases.sort(key=lambda c: c.planned_start)
    return cases


# ------------------------------------------------------------
# ELECTIVE SLOT SEARCH (admin time only)
# ------------------------------------------------------------
def elective_overlaps(case_a: ElectiveCase, case_b: ElectiveCase, rest_time_map: Dict[str, Dict[str, int]]) -> bool:
    """
    Overlap if:
      - same room overlaps on room interval (duration+prep)
      - any shared surgeon overlaps on surgeon interval (duration+rest)
    """
    if case_a.status == "completed" or case_b.status == "completed":
        return False
    a_start = case_a.scheduled_start
    b_start = case_b.scheduled_start

    a_room_end = a_start + case_a.duration() + case_a.prep()
    b_room_end = b_start + case_b.duration() + case_b.prep()

    # Get rest time from map based on surgery type (use 'main' surgeon rest time)
    a_rest = rest_time_map.get(case_a.surgery_type, {}).get('main', 15)
    b_rest = rest_time_map.get(case_b.surgery_type, {}).get('main', 15)
    
    a_surg_end = a_start + case_a.duration() + a_rest
    b_surg_end = b_start + case_b.duration() + b_rest

    # room overlap
    if case_a.room == case_b.room:
        if not (a_room_end <= b_start or b_room_end <= a_start):
            return True

    # surgeon overlap
    team_a = {case_a.main, case_a.assist1, case_a.assist2}
    team_b = {case_b.main, case_b.assist1, case_b.assist2}
    if team_a & team_b:
        if not (a_surg_end <= b_start or b_surg_end <= a_start):
            return True

    return False

def is_elective_slot_feasible(
    cand_start: int,
    case: ElectiveCase,
    all_cases: Dict[str, ElectiveCase],
    work: WorkSchedule,
    rest_time_map: Dict[str, Dict[str, int]],
) -> bool:
    # must start in admin time Mon-Fri
    if not is_admin_time(cand_start):
        return False
    # must finish surgeon workload within admin time and same day
    rest_time = rest_time_map.get(case.surgery_type, {}).get('main', 15)
    end_surg = cand_start + case.duration() + rest_time
    if not is_admin_time(end_surg - 1):
        return False
    if not same_calendar_day(cand_start, end_surg - 1):
        return False

    # surgeons must be on duty for elective (not day off)
    for s in [case.main, case.assist1, case.assist2]:
        if not work.on_duty_for_elective(s, cand_start):
            return False

    # conflicts with other elective cases (planned schedule)
    tmp = ElectiveCase(
        pid=case.pid, surgery_type=case.surgery_type,
        planned_start=case.planned_start, scheduled_start=cand_start,
        room=case.room, main=case.main, assist1=case.assist1, assist2=case.assist2,
        status=case.status, delayed_weeks=case.delayed_weeks
    )
    for pid2, other in all_cases.items():
        if pid2 == case.pid:
            continue
        if elective_overlaps(tmp, other, rest_time_map):
            return False

    return True

def find_earliest_elective_slot(
    from_time: int,
    case: ElectiveCase,
    all_cases: Dict[str, ElectiveCase],
    work: WorkSchedule,
    rest_time_map: Dict[str, Dict[str, int]],
) -> Optional[int]:
    """
    Search earliest feasible start time for this elective case starting from from_time.
    Only searches within the CURRENT WEEK (Mon-Fri admin hours).
    If no slot found in current week, returns None (will be marked as delayed).
    """
    start_search = from_time
    start_week_idx = start_search // WEEK_LENGTH
    
    # Get rest time for this surgery type
    rest_time = rest_time_map.get(case.surgery_type, {}).get('main', 15)
    
    # Only search current week (w_off = 0)
    w_idx = start_week_idx
    w_start = w_idx * WEEK_LENGTH
    search_from = max(start_search, w_start)
    
    for day in range(5):  # Mon-Fri only
        day_start = w_start + day * MINUTES_PER_DAY + ADMIN_SHIFT_START
        day_end = w_start + day * MINUTES_PER_DAY + ADMIN_SHIFT_END
        t = max(day_start, search_from)
        
        latest = day_end - (case.duration() + rest_time)
        if t > latest:
            continue
        
        while t <= latest:
            if is_elective_slot_feasible(t, case, all_cases, work, rest_time_map):
                return t
            t += 1
    
    return None  # No slot found in current week


# ------------------------------------------------------------
# URGENT TEAM SELECTION
# ------------------------------------------------------------
def choose_urgent_team(
    surgery_type: str,
    available_surgeons: Set[str],
    cap: CapabilityModel,
    prefer_three: bool = True,
) -> Optional[Tuple[str, str, Optional[str], int]]:
    """
    Return (main, a1, a2_or_none, team_size) using only available_surgeons.
    Deterministic: lowest surgeon-number first.
    
    Uses capability data from Excel (cap.a2_by_type) for Assistant 2 selection.
    """
    mains = sorted(cap.main_by_type.get(surgery_type, set()) & available_surgeons,
                   key=lambda x: int(x[1:]))
    a1s = sorted(cap.a1_by_type.get(surgery_type, set()) & available_surgeons,
                 key=lambda x: int(x[1:]))
    # Use capability-based Assistant 2 pool from Excel instead of hardcoded ASSIST2_POOL
    a2s = sorted(cap.a2_by_type.get(surgery_type, set()) & available_surgeons, key=lambda x: int(x[1:]))

    # Try 3-person
    if prefer_three:
        for m in mains:
            for a1 in a1s:
                if a1 == m:
                    continue
                for a2 in a2s:
                    if a2 in {m, a1}:
                        continue
                    return (m, a1, a2, 3)

    # Fallback 2-person
    for m in mains:
        for a1 in a1s:
            if a1 == m:
                continue
            return (m, a1, None, 2)

    return None


# ------------------------------------------------------------
# SURGERY EXECUTION PROCESS
# ------------------------------------------------------------
def execute_surgery(
    env: simpy.Environment,
    pid: str,
    surgery_type: str,
    is_urgent: bool,
    room: int,
    team: Tuple[str, str, Optional[str]],
    room_res: Dict[int, simpy.Resource],
    surg_res: Dict[str, simpy.Resource],
    rest_time: int,
    log: List[dict],
    active_counter: Dict[str, int],
    arrival_time: float,
    start_time: float,
    case_obj=None,
):
    """
    Holds:
      - room for duration+prep
      - surgeons in team for duration+rest_time
    """
    duration = SURGERY_DURATION_MIN[surgery_type]
    prep = PREP_TIME_MIN[surgery_type]

    # Build requests (no queue expected because scheduler only starts if free)
    # But we still request to "lock" them.
    reqs = []
    req_room = room_res[room].request()
    reqs.append(req_room)

    main, a1, a2 = team
    req_main = surg_res[main].request()
    req_a1 = surg_res[a1].request()
    reqs.extend([req_main, req_a1])
    req_a2 = None
    if a2 is not None:
        req_a2 = surg_res[a2].request()
        reqs.append(req_a2)

    # acquire
    yield simpy.events.AllOf(env, reqs)

    active_counter["active"] += 1

    end_surgeon = start_time + duration + rest_time
    end_room = start_time + duration + prep

    log.append({
        "pid": pid,
        "type": "URGENT" if is_urgent else "ELECTIVE",
        "surgery_type": surgery_type,
        "arrival": arrival_time,
        "start": start_time,
        "end_surgeon": end_surgeon,
        "end_room": end_room,
        "room": room,
        "main": main,
        "assist1": a1,
        "assist2": a2 if a2 is not None else "",
        "team_size": 3 if a2 is not None else 2,
        "wait": start_time - arrival_time,
        "priority_rank": "",  # filled for urgent in summary
    })

    # run surgery duration
    yield env.timeout(duration)

    # release by min(extra times)
    extra_room = prep
    extra_surg = rest_time
    if extra_room >= extra_surg:
        yield env.timeout(extra_surg)
        # surgeons free
        surg_res[main].release(req_main)
        surg_res[a1].release(req_a1)
        if req_a2 is not None:
            surg_res[a2].release(req_a2)
        yield env.timeout(extra_room - extra_surg)
        room_res[room].release(req_room)
    else:
        yield env.timeout(extra_room)
        room_res[room].release(req_room)
        yield env.timeout(extra_surg - extra_room)
        surg_res[main].release(req_main)
        surg_res[a1].release(req_a1)
        if req_a2 is not None:
            surg_res[a2].release(req_a2)

    if case_obj is not None:
        try:
            case_obj.status = "completed"
        except Exception:
            pass

    active_counter["active"] -= 1


# ------------------------------------------------------------
# MAIN SIMULATION
# ------------------------------------------------------------
def run_sim(
    work_schedule_paths: List[str],
    cap_rank_path: str,
    elective_sched_path: str,
    mean_interarrival_urgent: float,
    rest_time: int,  # NOTE: This parameter is kept for backward compatibility but rest_time_map from Excel is used
    penalty_next_week: int,
    seed: int,
):
    random.seed(seed)

    # ---- Load inputs (multi-week schedules)
    df_weeks = [load_work_schedule_xlsx(p) for p in work_schedule_paths]
    surgeons = [f"S{i}" for i in range(1, 13)]  # S1..S12
    work = WorkSchedule(df_weeks, surgeons)

    cap = load_cap_rank_xlsx(cap_rank_path)
    elective_list = load_elective_schedule_xlsx(elective_sched_path)
    elective_cases: Dict[str, ElectiveCase] = {c.pid: c for c in elective_list}

    # Determine number of rooms from elective schedule
    n_rooms = max(1, max(c.room for c in elective_list))
    rooms = list(range(1, n_rooms+1))
    
    # Load rest time map from Excel (surgery-type and role-specific)
    rest_time_map = load_rest_time_map(cap_rank_path)

    # ---- SimPy environment
    env = simpy.Environment()
    room_res = {r: simpy.Resource(env, capacity=1) for r in rooms}
    surg_res = {s: simpy.Resource(env, capacity=1) for s in surgeons}

    # ---- State
    urgent_cases: List[UrgentCase] = []
    urgent_seq = {"i": 0}

    log: List[dict] = []
    active_counter = {"active": 0}

    stats = {
        "urgent_arrived": 0,
        "urgent_started": 0,
        "elective_started": 0,
        "elective_rescheduled": [],
        "elective_delayed_next_week": 0,
        "urgent_waiting_by_rank": {},  # rank -> list waits
        "urgent_backlog_end": 0,
    }

    # ---- Urgent generator (arrives 24/24)
    arrival_horizon = WEEK_LENGTH  # generate urgents for 1 week
    def urgent_generator():
        while True:
            inter = random.expovariate(1.0 / mean_interarrival_urgent)
            yield env.timeout(inter)
            if env.now >= arrival_horizon:
                break
            urgent_seq["i"] += 1
            uid = f"U{urgent_seq['i']:04d}"
            stype = random.choice(list(SURGERY_DURATION_MIN.keys()))
            arr = float(env.now)
            bucket = int(math.floor(arr))
            rank = cap.rank_by_type.get(stype, 999)
            urgent_cases.append(UrgentCase(uid=uid, surgery_type=stype, arrival_time=arr,
                                           arrival_bucket=bucket, rank=rank))
            stats["urgent_arrived"] += 1

    # ---- Scheduler (every minute boundary)
    def scheduler():
        # run until: no more arrivals, no waiting urgents, all electives done, no active surgeries
        # Allow up to 2 weeks simulation time for electives to complete (even if delayed to next week)
        max_sim_time = WEEK_LENGTH * 2
        while True:
            # advance to next whole minute (including from time 0)
            next_min = int(math.floor(env.now)) + 1
            yield env.timeout(max(0.0, next_min - env.now))
            now = float(env.now)
            now_int = int(math.floor(now))

            # stop condition
            all_elective_done = all(c.status == "completed" for c in elective_cases.values())
            waiting_urgent = [u for u in urgent_cases if u.status == "waiting"]
            if (now >= arrival_horizon and not waiting_urgent and active_counter["active"] == 0 and all_elective_done):
                break
            if now >= max_sim_time:
                # stop by time limit
                break

            # ---------- Build free resource sets
            free_rooms = {r for r in rooms if room_res[r].count == 0}
            free_surgeons = {s for s in surgeons if surg_res[s].count == 0}

            # ---------- 1) URGENT dispatch
            # Order: arrival_bucket, rank, arrival_time, uid
            waiting_urgent_sorted = sorted(
                [u for u in urgent_cases if u.status == "waiting" and u.arrival_time <= now],
                key=lambda u: (u.arrival_bucket, u.rank, u.arrival_time, u.uid)
            )

            # Available surgeons for urgent at this time
            available_urgent_surgeons = {s for s in free_surgeons if work.on_duty_for_urgent(s, now)}

            for u in waiting_urgent_sorted:
                if not free_rooms:
                    break
                # Try team 3 first, then 2
                team_choice = choose_urgent_team(u.surgery_type, available_urgent_surgeons, cap, prefer_three=True)
                if team_choice is None:
                    continue
                main, a1, a2, team_size = team_choice

                # allocate a room (deterministic)
                room = min(free_rooms)

                # remove used resources from availability sets for this minute
                free_rooms.remove(room)
                available_urgent_surgeons.discard(main)
                available_urgent_surgeons.discard(a1)
                free_surgeons.discard(main)
                free_surgeons.discard(a1)
                if a2 is not None:
                    available_urgent_surgeons.discard(a2)
                    free_surgeons.discard(a2)

                # mark started and spawn execution
                u.status = "executing"
                u.start_time = now
                u.team = (main, a1, a2)
                u.room = room
                u.used_team_size = team_size
                stats["urgent_started"] += 1

                env.process(execute_surgery(
                    env=env,
                    pid=u.uid,
                    surgery_type=u.surgery_type,
                    is_urgent=True,
                    room=room,
                    team=(main, a1, a2),
                    room_res=room_res,
                    surg_res=surg_res,
                    rest_time=rest_time_map.get(u.surgery_type, {}).get('main', 15),
                    log=log,
                    active_counter=active_counter,
                    arrival_time=u.arrival_time,
                    start_time=now,
                    case_obj=u,
                ))

            # ---------- 2) ELECTIVE dispatch (admin time only)
            # Consider electives that are due (scheduled_start <= now_int) and not completed
            due_electives = sorted(
                [c for c in elective_cases.values() if c.status == "scheduled" and c.scheduled_start <= now_int],
                key=lambda c: (c.scheduled_start, c.planned_start, c.pid)
            )

            for c in due_electives:
                # If not admin time, reschedule to next feasible slot
                if not is_admin_time(now_int):
                    new_start = find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time_map)
                    if new_start is None:
                        # No slot in current week -> mark as delayed to next week
                        c.status = "completed"  # skip further scheduling attempts
                        current_week = now_int // WEEK_LENGTH
                        c.delayed_weeks = current_week + 1  # mark as delayed to next week
                        stats["elective_delayed_next_week"] += 1
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": f"week_{c.delayed_weeks}", "reason": "Not admin time - no slot in current week"})
                        continue
                    old = c.scheduled_start
                    c.scheduled_start = new_start
                    c.delayed_weeks = max(c.delayed_weeks, new_start // WEEK_LENGTH)
                    stats["elective_rescheduled"].append({"pid": c.pid, "from": old, "to": new_start, "reason": "Not admin time"})
                    continue

                # Check surgeons on duty for elective at this time
                if not (work.on_duty_for_elective(c.main, now) and work.on_duty_for_elective(c.assist1, now) and work.on_duty_for_elective(c.assist2, now)):
                    new_start = find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time_map)
                    if new_start is None:
                        # No slot in current week -> mark as delayed to next week
                        c.status = "completed"
                        current_week = now_int // WEEK_LENGTH
                        c.delayed_weeks = current_week + 1
                        stats["elective_delayed_next_week"] += 1
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": f"week_{c.delayed_weeks}", "reason": "Surgeon day off - no slot in current week"})
                        continue
                    old = c.scheduled_start
                    c.scheduled_start = new_start
                    c.delayed_weeks = max(c.delayed_weeks, new_start // WEEK_LENGTH)
                    stats["elective_rescheduled"].append({"pid": c.pid, "from": old, "to": new_start, "reason": "Surgeon day off"})
                    continue

                # Resource free now?
                if c.room not in free_rooms:
                    # reschedule rather than waiting minute-by-minute 
                    new_start = find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time_map)
                    if new_start is None:
                        # No slot in current week -> mark as delayed to next week
                        c.status = "completed"
                        current_week = now_int // WEEK_LENGTH
                        c.delayed_weeks = current_week + 1
                        stats["elective_delayed_next_week"] += 1
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": f"week_{c.delayed_weeks}", "reason": "Room busy - no slot in current week"})
                        continue
                    old = c.scheduled_start
                    c.scheduled_start = new_start
                    c.delayed_weeks = max(c.delayed_weeks, new_start // WEEK_LENGTH)
                    stats["elective_rescheduled"].append({"pid": c.pid, "from": old, "to": new_start, "reason": "Room busy"})
                    continue

                needed = {c.main, c.assist1, c.assist2}
                if not needed.issubset(free_surgeons):
                    new_start = find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time_map)
                    if new_start is None:
                        # No slot in current week -> mark as delayed to next week
                        c.status = "completed"
                        current_week = now_int // WEEK_LENGTH
                        c.delayed_weeks = current_week + 1
                        stats["elective_delayed_next_week"] += 1
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": f"week_{c.delayed_weeks}", "reason": "Surgeon busy - no slot in current week"})
                        continue
                    old = c.scheduled_start
                    c.scheduled_start = new_start
                    c.delayed_weeks = max(c.delayed_weeks, new_start // WEEK_LENGTH)
                    stats["elective_rescheduled"].append({"pid": c.pid, "from": old, "to": new_start, "reason": "Surgeon busy"})
                    continue

                # If starting now would exceed admin time (surgeon workload), reschedule
                elective_rest = rest_time_map.get(c.surgery_type, {}).get('main', 15)
                end_surg = now + c.duration() + elective_rest
                if (not is_admin_time(end_surg - 1)) or (not same_calendar_day(now, end_surg - 1)):
                    new_start = find_earliest_elective_slot(now_int, c, elective_cases, work, rest_time_map)
                    if new_start is None:
                        # No slot in current week -> mark as delayed to next week
                        c.status = "completed"
                        current_week = now_int // WEEK_LENGTH
                        c.delayed_weeks = current_week + 1
                        stats["elective_delayed_next_week"] += 1
                        stats["elective_rescheduled"].append({"pid": c.pid, "from": c.scheduled_start, "to": f"week_{c.delayed_weeks}", "reason": "Would exceed admin hours - no slot in current week"})
                        continue
                    old = c.scheduled_start
                    c.scheduled_start = new_start
                    c.delayed_weeks = max(c.delayed_weeks, new_start // WEEK_LENGTH)
                    stats["elective_rescheduled"].append({"pid": c.pid, "from": old, "to": new_start, "reason": "Would exceed admin hours"})
                    continue

                # allocate resources in this minute
                free_rooms.remove(c.room)
                free_surgeons -= needed

                # start surgery
                c.scheduled_start = now_int  # actual start time
                c.status = "executing"
                stats["elective_started"] += 1
                env.process(execute_surgery(
                    env=env,
                    pid=c.pid,
                    surgery_type=c.surgery_type,
                    is_urgent=False,
                    room=c.room,
                    team=(c.main, c.assist1, c.assist2),
                    room_res=room_res,
                    surg_res=surg_res,
                    rest_time=rest_time_map.get(c.surgery_type, {}).get('main', 15),
                    log=log,
                    active_counter=active_counter,
                    arrival_time=float(c.planned_start),
                    start_time=now,
                    case_obj=c,
                ))

    # ---- Start processes
    env.process(urgent_generator())
    env.process(scheduler())

    env.run()

    # ---- Post-processing
    sim_end = 0
    for rec in log:
        sim_end = max(sim_end, int(math.ceil(rec["end_room"])), int(math.ceil(rec["end_surgeon"])))
    sim_end = max(sim_end, int(math.ceil(env.now)))

    # Surgeon KPI: duty vs busy
    busy_by_surgeon: Dict[str, List[Tuple[int,int]]] = {s: [] for s in surgeons}
    for rec in log:
        a = int(math.floor(rec["start"]))
        b = int(math.ceil(rec["end_surgeon"]))
        for s in [rec["main"], rec["assist1"]]:
            busy_by_surgeon[s].append((a,b))
        if rec.get("assist2", ""):
            busy_by_surgeon[rec["assist2"]].append((a,b))

    for s in surgeons:
        busy_by_surgeon[s] = merge_intervals(busy_by_surgeon[s])

    duty_by_surgeon: Dict[str, List[Tuple[int,int]]] = {s: work.duty_intervals_abs(s, sim_end) for s in surgeons}

    surgeon_kpi = {}
    for s in surgeons:
        duty_total = interval_total(duty_by_surgeon[s])
        busy_total = interval_total(busy_by_surgeon[s])
        busy_in_duty = overlap_total(busy_by_surgeon[s], duty_by_surgeon[s])
        unproductive = max(0, duty_total - busy_in_duty)
        overtime = max(0, busy_total - busy_in_duty)
        surgeon_kpi[s] = {
            "duty_total_min": duty_total,
            "busy_total_min": busy_total,
            "busy_in_duty_min": busy_in_duty,
            "unproductive_min": unproductive,
            "overtime_min": overtime,
        }

    # Waiting times
    urgent_recs = [r for r in log if r["type"] == "URGENT"]
    elective_recs = [r for r in log if r["type"] == "ELECTIVE"]

    # Fill priority rank in urgent log + aggregate by rank
    urgent_wait_by_rank: Dict[int, List[float]] = {}
    for r in urgent_recs:
        rank = cap.rank_by_type.get(r["surgery_type"], 999)
        r["priority_rank"] = rank
        urgent_wait_by_rank.setdefault(rank, []).append(r["wait"])

    # Elective delayed to next week count
    delayed_next_week = sum(1 for c in elective_cases.values() if c.delayed_weeks >= 1)
    penalty = delayed_next_week * penalty_next_week

    # backlog urgent at end (if any)
    backlog_urgent = sum(1 for u in urgent_cases if u.status == "waiting")
    stats["urgent_backlog_end"] = backlog_urgent

    # ---- Print summary
    print("=" * 100)
    print("SIMULATION SUMMARY")
    print("=" * 100)
    print(f"Rooms: {n_rooms} | Surgeons: {len(surgeons)} (Assist2 pool: S9-S12)")
    print(f"Urgent arrived:  {stats['urgent_arrived']}")
    print(f"Urgent started:  {stats['urgent_started']}  | backlog (not started): {backlog_urgent}")
    print(f"Elective started:{stats['elective_started']} / {len(elective_cases)}")
    print(f"Elective delayed to next week: {delayed_next_week} (penalty={penalty})")
    print("-" * 100)

    if urgent_recs:
        waits = [r["wait"] for r in urgent_recs]
        print(f"Urgent waiting time (min): avg={sum(waits)/len(waits):.2f}, max={max(waits):.2f}")
        print("Urgent waiting time by PRIORITY RANK (smaller=more urgent):")
        for rank in sorted(urgent_wait_by_rank.keys()):
            ws = urgent_wait_by_rank[rank]
            print(f"  rank={rank:>3d} | n={len(ws):>3d} | avg={sum(ws)/len(ws):6.2f} | max={max(ws):6.2f}")

    if elective_recs:
        delays = [r["wait"] for r in elective_recs]  # start - planned_start
        print(f"Elective delay vs baseline (min): avg={sum(delays)/len(delays):.2f}, max={max(delays):.2f}")

    print("-" * 100)
    print("Top 5 surgeons by overtime:")
    top_ot = sorted(surgeon_kpi.items(), key=lambda kv: kv[1]["overtime_min"], reverse=True)[:5]
    for s, k in top_ot:
        print(f"  {s}: overtime={k['overtime_min']:>5d} | unproductive={k['unproductive_min']:>5d} | duty={k['duty_total_min']:>5d} | busy={k['busy_total_min']:>5d}")

    # Print schedule log (compact)
    print("=" * 100)
    print("SURGERY LOG (sorted by start time)")
    print("=" * 100)
    for r in sorted(log, key=lambda x: x["start"]):
        d = int(math.floor(r["start"]) // MINUTES_PER_DAY)
        tod = minutes_to_hhmm(r["start"])
        print(f"{r['pid']:>6s} {r['type']:<8s} | day={d} {tod} | room={r['room']} | "
              f"{r['surgery_type']:<45.45s} | team_size={r['team_size']} | wait={r['wait']:.2f} | "
              f"team=({r['main']},{r['assist1']},{r.get('assist2','')}) | rank={r.get('priority_rank','')}")

    if stats["elective_rescheduled"]:
        print("=" * 100)
        print("ELECTIVE RESCHEDULE EVENTS (first 30)")
        print("=" * 100)
        for e in stats["elective_rescheduled"][:30]:
            print(f"{e['pid']}: {e['from']} -> {e['to']} | {e['reason']}")

    print("=" * 100)
    
    # Export schedule if output path provided
    return log, stats, surgeon_kpi


def export_schedule_from_log(log: List[dict], output_path: str):
    """Convert simulation log to combined schedule DataFrame and save to Excel."""
    import pandas as pd
    
    rows = []
    for rec in log:
        # Convert start time to day + time_hhmm
        start_abs = int(rec["start"])
        day = start_abs // MINUTES_PER_DAY
        time_hhmm = minutes_to_hhmm(start_abs % MINUTES_PER_DAY)
        
        rows.append({
            "pid": rec["pid"],
            "patient_type": rec["type"],  # URGENT or ELECTIVE
            "surgery_type": rec["surgery_type"],
            "arrival": rec["arrival"],
            "wait": rec["wait"],
            "day": day,
            "time_hhmm": time_hhmm,
            "actual_start": start_abs,
            "room": rec["room"],
            "main": rec["main"],
            "assist1": rec["assist1"],
            "assist2": rec.get("assist2", ""),
            "team_size": rec.get("team_size", 0),
        })
    
    df = pd.DataFrame(rows)
    df = df.sort_values("actual_start")  # Sort by start time
    df.to_excel(output_path, index=False)
    print(f"\nSchedule exported to: {output_path}")
    
    return df


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
def main():
    # Fix UTF-8 output in Windows console
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Get script directory for default file paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--work_schedule", nargs="+", 
        default=[os.path.join(script_dir, "lich_lam_viec_tuan1.xlsx"), 
                 os.path.join(script_dir, "lich_lam_viec_tuan2.xlsx")], 
        help="Weekly doctor work schedule files (.xlsx), one per week")
    parser.add_argument("--cap_rank", default=os.path.join(script_dir, "Cap_Rank.xlsx"), help="Capabilities + ranking (.xlsx)")
    parser.add_argument("--elective_sched", default=os.path.join(script_dir, "surgery_schedule.xlsx"), help="Fixed elective schedule (.xlsx)")
    parser.add_argument("--mean_urgent", type=float, default=None, help="Mean inter-arrival time for urgent (minutes)")
    parser.add_argument("--rest_time", type=int, default=DEFAULT_REST_TIME_MIN, help="Surgeon rest time after surgery (minutes)")
    parser.add_argument("--penalty_next_week", type=int, default=DEFAULT_PENALTY_DELAY_NEXT_WEEK, help="Penalty per elective pushed to next week")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", type=str, default=None, help="Output path for schedule Excel file")
    args = parser.parse_args()
    # Load urgent parameter from Excel based on scale
    if args.mean_urgent is None:
        args.mean_urgent = load_urgent_param_from_excel(args.cap_rank, 'Small scale')
    print(f"Using mean_interarrival_urgent: {args.mean_urgent} (Small scale)")
    print(f"Using work schedule files: {args.work_schedule}")


    log, stats, surgeon_kpi = run_sim(
        work_schedule_paths=args.work_schedule,
        cap_rank_path=args.cap_rank,
        elective_sched_path=args.elective_sched,
        mean_interarrival_urgent=args.mean_urgent,
        rest_time=args.rest_time,
        penalty_next_week=args.penalty_next_week,
        seed=args.seed,
    )
    
    # Export schedule - auto-export by default, or to custom path if specified
    default_output = os.path.join(script_dir, "small_rulebased_output.xlsx")
    output_path = args.output if args.output else default_output
    export_schedule_from_log(log, output_path)
    
    print("Done.")

if __name__ == "__main__":
    main()