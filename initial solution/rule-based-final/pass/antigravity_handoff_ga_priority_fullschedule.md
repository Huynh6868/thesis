# Handoff: GA cải thiện lịch OR bằng Priority Permutation + Team Swap (Fullschedule)

Người dùng: **Kim Ngan Huynh Nguyen**  
Mục tiêu: nâng mức cải thiện GA (hiện ~0.22%) bằng cách thay đổi cách mã hoá/giải mã để tránh kẹt local optima.

---

## 1) Context ngắn gọn (đủ để vào việc)

### Bài toán
- Có lịch **elective** ban đầu (từ Excel/CPLEX).
- Có dòng **urgent arrivals** theo từng scenario_seed: mỗi urgent có `(arrival_time, surgery_type)`.
- Rule-based simulator (v3) dispatch theo thời gian: **urgent ưu tiên**, elective bị delay/reschedule khi xung đột.
- GA hiện tại dùng **delta_by_case** (dịch phút) → khó tạo “bước nhảy lớn” (đổi thứ tự sâu, đổi ngày xa, hoán đổi cụm ca) → cải thiện ít.

### Điều kiện so sánh công bằng (BẮT BUỘC)
**Urgent stream giữa Rule-based và GA phải giống nhau về:**
- số lượng urgents
- arrival times
- surgery type  
=> Tất cả chạy trên **cùng `urgent_list`** tạo từ `scenario_seed`.  
Lưu ý: ta **không yêu cầu** start-time của urgent giống nhau; start-time là kết quả của lịch (phụ thuộc schedule/dispatch). Điều cần “giống” là *scenario input*.

### Hướng giải pháp
1) Cho phép **đổi team cho elective** (main/assist) trong phạm vi năng lực (capability) để mở bottleneck surgeon.
2) Đổi chromosome sang **Priority Permutation**:
   - GA không “đoán delta phút” nữa.
   - GA xuất: *thứ tự ưu tiên elective* (+ lựa chọn team/room).
   - Decoder “first-fit earliest feasible” xếp lịch chặt và luôn feasible.

### Phạm vi đề xuất (khuyến nghị)
- **Urgent**: giữ nguyên logic dispatch như rule-based/lightweight; không gene hoá urgent.
- **Elective**: gene hoá:
  - `priority_list` (permutation elective pids)
  - `team_idx_by_pid` (chọn team hợp lệ theo loại mổ)
  - (tuỳ chọn) `room_by_pid` (gene room; nếu không có, decoder tự chọn room first-fit)

---

## 2) Kiến trúc mới (tách 2 tầng)

### Tầng A — Planner/Decoder (deterministic)
Input:
- elective baseline (pid, planned_start, stype, …)
- `priority_list`, `team_idx_by_pid`, `room_by_pid`
- constraint: số phòng, admin hours, prep/rest, calendars room & surgeon

Output (overrides cho elective):
- `scheduled_start_override[pid]`
- `room_override[pid]`
- `team_override[pid] = (main, a1, a2|None)`

Nguyên tắc:
- Xếp elective theo `priority_list`.
- Với mỗi ca: chọn **slot sớm nhất** `t >= planned_start` thoả:
  - admin time
  - room rảnh (dur+prep)
  - surgeons rảnh (dur+rest)
  - surgeons đủ năng lực theo cap lists

Nếu không tìm được trong tuần hiện tại:
- cho phép đẩy sang tuần tiếp theo tối đa `max_reschedule_weeks` (cấu hình)

### Tầng B — Lightweight simulator (event loop)
- Dùng `urgent_list` cố định (scenario input).
- Dispatch urgent trước, elective sau, theo logic giống rule-based.
- Nhưng elective case sẽ dùng `scheduled_start_override` + `team_override` + `room_override` từ Planner.
- Elective dispatch nên ưu tiên theo `scheduled_start` và tie-break bởi `priority_rank` (để chromosome có tác dụng nhất quán).

---

## 3) Data Prep: Valid Teams

Dữ liệu capability:
- `cap.main_by_type[stype]`
- `cap.a1_by_type[stype]`
- `cap.a2_by_type[stype]` (có thể rỗng)

Sinh `valid_teams_by_type[stype]`:
- Teams 3 người: (main, a1, a2) với 3 người khác nhau.
- Teams 2 người: (main, a1, None) làm fallback.
- Có thể giới hạn số team / ưu tiên team “gần baseline” để search space không nổ.

---

## 4) Acceptance tests (bắt buộc trước khi chạy GA dài)

1) **Urgent stream identity**
- `urgent_list` chỉ generate 1 lần bằng `scenario_seed`.
- In ra `hash(str(urgent_list))` cho baseline vs GA; phải trùng.

2) **Identity chromosome**
- priority_list = elective sorted theo baseline planned_start (hoặc theo baseline schedule)
- team_idx = map về đúng team baseline
- room = baseline room
=> Metrics của identity phải xấp xỉ baseline (chênh nhỏ do tie-break).

3) **Feasibility sanity**
- Planner không tạo overlap trong calendars.
- Nếu planner fail (không tìm slot trong max_reschedule_weeks): đánh dấu “delayed next week” đúng quy ước và phạt nặng.

---

## 5) Sườn code (skeleton) — triển khai theo các file hiện có

Bạn có thể implement trực tiếp trong:
- `ga_optimize_per_scenario_patched_v3_fullschedule.py` (GA driver)
- `lightweight_fitness_v3_fullschedule.py` (evaluator)
- (đọc constraint/helpers) `rule_based_or_sim_v3.py`

Bên dưới là skeleton code có TODO rõ ràng.

---

# A) Core data structures

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import random

Team = Tuple[str, str, Optional[str]]  # (main, assist1, assist2_or_None)

@dataclass(frozen=True)
class ElectiveCase:
    pid: int
    surgery_type: str
    planned_start: int          # absolute minutes since week start
    duration: int               # minutes
    baseline_room: int
    baseline_team: Team

@dataclass
class PlannerOverrides:
    scheduled_start_by_pid: Dict[int, int]
    room_by_pid: Dict[int, int]
    team_by_pid: Dict[int, Team]

@dataclass
class GAIndividual:
    priority_list: List[int]                # permutation of elective pids
    team_idx_by_pid: Dict[int, int]         # elective pid -> index in valid_teams_by_type[stype]
    room_by_pid: Optional[Dict[int, int]]   # elective pid -> room (optional)

    fitness: Optional[float] = None
    metrics: Optional[dict] = None
```

---

# B) Build valid teams

```python
def build_valid_teams_by_type(cap) -> Dict[str, List[Team]]:
    """cap is from rule_based_or_sim_v3.load_cap_rank_xlsx"""
    valid: Dict[str, List[Team]] = {}
    for stype in cap.main_by_type.keys():
        mains = list(cap.main_by_type.get(stype, []))
        a1s   = list(cap.a1_by_type.get(stype, []))
        a2s   = list(cap.a2_by_type.get(stype, []))

        teams: List[Team] = []

        # 3-person teams
        for m in mains:
            for a1 in a1s:
                if a1 == m: 
                    continue
                for a2 in a2s:
                    if a2 in (m, a1):
                        continue
                    teams.append((m, a1, a2))

        # 2-person fallback
        for m in mains:
            for a1 in a1s:
                if a1 == m:
                    continue
                teams.append((m, a1, None))

        # TODO: optional dedup + optional cap number of teams (e.g., top K) to control search space.
        valid[stype] = teams
    return valid
```

---

# C) Calendar helpers (interval scheduling)

```python
# intervals as list of (start, end) sorted by start, non-overlapping
def _can_insert(intervals: List[Tuple[int,int]], s: int, e: int) -> bool:
    # TODO: implement via bisect; must ensure no overlap with neighbors
    ...

def _insert(intervals: List[Tuple[int,int]], s: int, e: int) -> None:
    # TODO: insert keeping sorted; assume _can_insert checked
    ...
```

---

# D) Planner: first-fit earliest feasible

```python
def build_elective_plan(
    elective_cases: Dict[int, ElectiveCase],
    priority_list: List[int],
    team_idx_by_pid: Dict[int, int],
    room_by_pid: Optional[Dict[int, int]],
    valid_teams_by_type: Dict[str, List[Team]],
    n_rooms: int,
    prep_time: int,
    rest_time: int,
    admin_start_min: int,
    admin_end_min: int,
    week_length: int,
    max_reschedule_weeks: int = 1,
    time_step: int = 5,
) -> PlannerOverrides:
    """
    Returns overrides for elective schedule.
    - elective start times can move across days/weeks (up to max_reschedule_weeks)
    - ensures feasibility wrt room and surgeon calendars
    """

    room_cal: Dict[int, List[Tuple[int,int]]] = {r: [] for r in range(1, n_rooms+1)}
    surg_cal: Dict[str, List[Tuple[int,int]]] = {}  # surgeon -> intervals

    def ensure_surg(s: str):
        if s not in surg_cal:
            surg_cal[s] = []

    scheduled_start: Dict[int, int] = {}
    assigned_room: Dict[int, int] = {}
    assigned_team: Dict[int, Team] = {}

    for pid in priority_list:
        c = elective_cases[pid]
        teams = valid_teams_by_type[c.surgery_type]
        if not teams:
            raise ValueError(f"No valid teams for type={c.surgery_type}")

        team = teams[team_idx_by_pid[pid] % len(teams)]
        main, a1, a2 = team
        ensure_surg(main); ensure_surg(a1)
        if a2: ensure_surg(a2)

        dur_room = c.duration + prep_time
        dur_surg = c.duration + rest_time

        # Determine candidate rooms
        if room_by_pid is None:
            room_candidates = list(range(1, n_rooms+1))
        else:
            room_candidates = [room_by_pid[pid]]

        found = False
        # Search from planned_start forward in steps (time_step)
        search_start = c.planned_start
        search_end = c.planned_start + (max_reschedule_weeks+1) * week_length

        t = search_start
        while t < search_end and not found:
            # Admin window constraint: must start within admin hours of that day
            # TODO: convert t -> day-of-week and minute-in-day; enforce admin_start_min <= minute_in_day <= admin_end_min
            # TODO: optionally require end <= admin_end_min for room
            for r in room_candidates:
                s_room = t
                e_room = t + dur_room

                if not _can_insert(room_cal[r], s_room, e_room):
                    continue

                # surgeons: block [t, t+dur_surg]
                s_surg = t
                e_surg = t + dur_surg

                if not _can_insert(surg_cal[main], s_surg, e_surg): 
                    continue
                if not _can_insert(surg_cal[a1], s_surg, e_surg): 
                    continue
                if a2 and (not _can_insert(surg_cal[a2], s_surg, e_surg)):
                    continue

                # Feasible -> commit
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

            t += time_step

        if not found:
            # TODO: mark delayed next week / apply special override convention
            # Option: scheduled_start[pid] = None and evaluator counts as delayed_next_week
            # But better: set to week boundary + planned minute-in-day
            scheduled_start[pid] = c.planned_start + week_length * (max_reschedule_weeks+1)
            assigned_room[pid] = room_candidates[0]
            assigned_team[pid] = team

    return PlannerOverrides(scheduled_start, assigned_room, assigned_team)
```

---

# E) Lightweight evaluator: accept overrides + priority rank

## Required changes (lightweight_fitness_v3_fullschedule.py)
1) Add params:
- `overrides: PlannerOverrides`
- `priority_rank: Dict[int,int]` (pid -> rank)

2) When building elective cases:
- keep `planned_start` from baseline
- set `scheduled_start` = overrides.scheduled_start_by_pid[pid]
- set room/team from overrides

3) When picking eligible electives at time `now`, sort:
- `scheduled_start`, then `priority_rank`, then `planned_start`, then pid

Skeleton patch:

```python
def simulate_fixed_urgent_lightweight(
    elective_input_df,
    urgent_list,
    cap,
    work,
    n_rooms: int,
    prep_time: int,
    rest_time: int,
    overrides: PlannerOverrides,
    priority_rank: Dict[int,int],
    # ... existing args
):
    # Build elective cases
    elective_cases = []
    for row in elective_input_df.itertuples(index=False):
        pid = int(row.pid)
        planned_start = int(row.planned_abs)  # or reconstruct
        stype = row.surgery_type
        dur = int(row.duration_min)

        # apply overrides
        sched_start = int(overrides.scheduled_start_by_pid.get(pid, planned_start))
        room = int(overrides.room_by_pid.get(pid, row.room))
        team = overrides.team_by_pid.get(pid, (row.main, row.assist1, getattr(row,'assist2',None)))
        main, a1, a2 = team

        # TODO: create lightweight Case object with planned_start + scheduled_start + team + room

    # In dispatch elective:
    eligible = [c for c in elective_cases if c.status=='waiting' and c.scheduled_start <= now]
    eligible.sort(key=lambda c: (c.scheduled_start, priority_rank.get(c.pid, 10**9), c.planned_start, c.pid))
    # ... proceed with existing feasibility checks + reschedule if needed
```

---

# F) GA loop: new operators

```python
def ox_crossover(p1: List[int], p2: List[int], rng: random.Random) -> Tuple[List[int], List[int]]:
    # TODO: implement order crossover
    ...

def mutate_priority(priority: List[int], rng: random.Random, p_swap=0.4, p_insert=0.4, p_scramble=0.2) -> None:
    # TODO: implement 1 of these mutations each call (or multiple)
    ...

def mutate_team(team_idx_by_pid: Dict[int,int], elective_cases: Dict[int, ElectiveCase],
                valid_teams_by_type: Dict[str, List[Team]], rng: random.Random, rate=0.2) -> None:
    # For random subset of pids, change team index to another valid team
    for pid in team_idx_by_pid.keys():
        if rng.random() < rate:
            stype = elective_cases[pid].surgery_type
            n = max(1, len(valid_teams_by_type.get(stype, [])))
            team_idx_by_pid[pid] = rng.randrange(n)
```

---

# G) Evaluate() wiring

```python
def evaluate(ind: GAIndividual, elective_cases, valid_teams_by_type, urgent_list, cap, work, params):
    overrides = build_elective_plan(
        elective_cases=elective_cases,
        priority_list=ind.priority_list,
        team_idx_by_pid=ind.team_idx_by_pid,
        room_by_pid=ind.room_by_pid,
        valid_teams_by_type=valid_teams_by_type,
        n_rooms=params.n_rooms,
        prep_time=params.prep_time,
        rest_time=params.rest_time,
        admin_start_min=params.admin_start,
        admin_end_min=params.admin_end,
        week_length=params.week_length,
        max_reschedule_weeks=params.max_reschedule_weeks,
        time_step=params.time_step,
    )

    priority_rank = {pid: i for i, pid in enumerate(ind.priority_list)}

    metrics = simulate_fixed_urgent_lightweight(
        elective_input_df=params.elective_input_df,
        urgent_list=urgent_list,
        cap=cap,
        work=work,
        n_rooms=params.n_rooms,
        prep_time=params.prep_time,
        rest_time=params.rest_time,
        overrides=overrides,
        priority_rank=priority_rank,
        # ...
    )

    # objective (TODO: decide weights)
    obj = (
        params.w_urgent * metrics["urgent_wait_weighted"]
        + params.w_elective_delay * metrics["elective_delay_total"]
        + params.w_overtime * metrics["overtime_total"]
        + params.w_next_week * (metrics["elective_delayed_next_week"] * params.penalty_next_week)
    )

    # optional shift penalty: only elective
    # TODO: define baseline_planned_start_by_pid
    if params.w_shift > 0:
        shift = 0
        for pid, c in elective_cases.items():
            shift += abs(overrides.scheduled_start_by_pid[pid] - c.planned_start)
        obj += params.w_shift * shift

    ind.fitness = obj
    ind.metrics = metrics
    return obj
```

---

## 6) Notes quan trọng (để tránh lỗi logic)

- Nếu planner “set scheduled_start vượt tuần” để biểu diễn delayed-next-week, evaluator phải count đúng vào `elective_delayed_next_week` và/hoặc `elective_delay_total`.
- Đừng để case “treo” không được scheduled mà lại không bị phạt.
- Nếu vẫn giữ decoder cũ ở đâu đó: đảm bảo calendars được update cho cả các case copy baseline (tránh overlap ảo).

---

## 7) Deliverables checklist (antigravity)

1) Implement `_can_insert`, `_insert` (bisect-based) + unit tests.
2) Implement `build_valid_teams_by_type(cap)` + optional cap teams.
3) Implement `build_elective_plan(...)` + test “no-overlap”.
4) Patch lightweight simulator to accept overrides + priority_rank + verify urgent invariants.
5) Patch GA driver to use new chromosome + operators + evaluate pipeline.
6) Add scenario test harness: run baseline vs GA(identity) vs GA(best) on same urgent_list seed.

---

**End.**
