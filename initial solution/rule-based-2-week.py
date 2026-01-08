# -*- coding: utf-8 -*-
import simpy  
import random
import sys
# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# =========================
WORK_HOURS_PER_DAY = 8      # Số giờ làm việc mỗi ngày
WORK_MINUTES_PER_DAY = WORK_HOURS_PER_DAY * 60  # 540 phút
HOURS_PER_DAY = 24          # Tổng số giờ trong 1 ngày
MINUTES_PER_DAY = HOURS_PER_DAY * 60  # 1440 phút
WORK_DAYS = 7               # Số ngày làm việc trong tuần
SIM_DURATION = WORK_DAYS * MINUTES_PER_DAY  # 5 * 1440 = 7200 phút
SHIFT_START_HOUR = 8        # Ca làm việc bắt đầu 8h sáng
SHIFT_END_HOUR = 16         # Ca làm việc kết thúc 5h chiều (17h)
MEAN_INTER_ARRIVAL = 2520
#WAIT_WINDOW = 30
MEAN_REST_TIME = 15
NUM_OPERATING_ROOMS = 2     # Số phòng mổ

# =========================
# CẤU HÌNH DỮ LIỆU 
# =========================
# Dictionary: loại phẫu thuật -> thời lượng (phút)
SURGERY_TYPES = {
    "adenotonsillectomy": 60,
    "microlaryngoscopy": 65,
    "septoplasty": 90,
    "thyroidectomy": 160,
    "buccal mucosa bioppsy": 30,
    "excision of the lymphadenopathy from the lumbar": 30,
    "modified radical mastoidectomy": 100,
    "rhinoplasty": 90,
    "endoscopic sinus": 65,
    "sleep apnea diagnosis test": 30 
}

# Danh sách bác sĩ (SURGEONS)
SURGEONS = {
    "S1": {
        "can_main":   {"sleep apnea diagnosis test"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar", "septoplasty", "endoscopic sinus"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S2": {
        "can_main":   {"sleep apnea diagnosis test"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar", "septoplasty", "endoscopic sinus"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S3": {
        "can_main":   {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy", "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy", "rhinoplasty"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S4": {
        "can_main":   {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy", "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "can_assist": {"modified radical mastoidectomy","thyroidectomy", "rhinoplasty"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S5": {
        "can_main":   {"rhinoplasty", "endoscopic sinus"},
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S6": {
        "can_main":   {"modified radical mastoidectomy", "thyroidectomy"},
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S7": {
        "can_main":   set(),
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S8": {
        "can_main":   set(),
        "can_assist": {"rhinoplasty", "endoscopic sinus"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S9": {
        "can_main":   set(),
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy", "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
    "S10": {
        "can_main":   set(),
        "can_assist":  {"sleep apnea diagnosis test"},
        "shift_start": 0,
        "shift_end":   9 * 60,
    },
}

# =========================
# DỮ LIỆU LỊCH MỔ PHIÊN (ELECTIVE)
# =========================
ELECTIVE_PATIENTS = [
    {"pid": "E01", "surgery_type": "modified radical mastoidectomy", "scheduled_time": 480, "room": 2},
    {"pid": "E02", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 730, "room": 1},
    {"pid": "E03", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 740, "room": 2},
    {"pid": "E04", "surgery_type": "thyroidectomy", "scheduled_time": 480, "room": 1},
    {"pid": "E05", "surgery_type": "modified radical mastoidectomy", "scheduled_time": 580, "room": 2},
    {"pid": "E06", "surgery_type": "buccal mucosa bioppsy", "scheduled_time": 760, "room": 1},
    {"pid": "E07", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 770, "room": 2},
    {"pid": "E08", "surgery_type": "adenotonsillectomy", "scheduled_time": 680, "room": 2},
    {"pid": "E09", "surgery_type": "rhinoplasty", "scheduled_time": 640, "room": 1},
    {"pid": "E10", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 790, "room": 1},

    {"pid": "E11", "surgery_type": "microlaryngoscopy", "scheduled_time": 2110, "room": 2},
    {"pid": "E12", "surgery_type": "septoplasty", "scheduled_time": 2020, "room": 2},
    {"pid": "E13", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 2175, "room": 2},
    {"pid": "E14", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 2205, "room": 2},
    {"pid": "E15", "surgery_type": "adenotonsillectomy", "scheduled_time": 2170, "room": 1},
    {"pid": "E16", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 2230, "room": 1},
    {"pid": "E17", "surgery_type": "thyroidectomy", "scheduled_time": 1920, "room": 1},
    {"pid": "E18", "surgery_type": "rhinoplasty", "scheduled_time": 2080, "room": 1},
    {"pid": "E19", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 2235, "room": 2},
    {"pid": "E20", "surgery_type": "modified radical mastoidectomy", "scheduled_time": 1920, "room": 2},

    {"pid": "E21", "surgery_type": "adenotonsillectomy", "scheduled_time": 3605, "room": 2},
    {"pid": "E22", "surgery_type": "rhinoplasty", "scheduled_time": 3360, "room": 2},
    {"pid": "E23", "surgery_type": "septoplasty", "scheduled_time": 3450, "room": 2},
    {"pid": "E24", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 3665, "room": 2},
    {"pid": "E25", "surgery_type": "adenotonsillectomy", "scheduled_time": 3650, "room": 1},
    {"pid": "E26", "surgery_type": "thyroidectomy", "scheduled_time": 3360, "room": 1},
    {"pid": "E27", "surgery_type": "endoscopic sinus", "scheduled_time": 3520, "room": 1},
    {"pid": "E28", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 3695, "room": 2},
    {"pid": "E29", "surgery_type": "endoscopic sinus", "scheduled_time": 3540, "room": 2},
    {"pid": "E30", "surgery_type": "microlaryngoscopy", "scheduled_time": 3585, "room": 1},

    {"pid": "E31", "surgery_type": "endoscopic sinus", "scheduled_time": 4960, "room": 1},
    {"pid": "E32", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 5110, "room": 2},
    {"pid": "E33", "surgery_type": "buccal mucosa bioppsy", "scheduled_time": 5140, "room": 2},
    {"pid": "E34", "surgery_type": "endoscopic sinus", "scheduled_time": 4980, "room": 2},
    {"pid": "E35", "surgery_type": "septoplasty", "scheduled_time": 4800, "room": 2},
    {"pid": "E36", "surgery_type": "adenotonsillectomy", "scheduled_time": 5090, "room": 1},
    {"pid": "E37", "surgery_type": "microlaryngoscopy", "scheduled_time": 5025, "room": 1},
    {"pid": "E38", "surgery_type": "thyroidectomy", "scheduled_time": 4800, "room": 1},
    {"pid": "E39", "surgery_type": "microlaryngoscopy", "scheduled_time": 5045, "room": 2},
    {"pid": "E40", "surgery_type": "rhinoplasty", "scheduled_time": 4890, "room": 2},

    {"pid": "E41", "surgery_type": "endoscopic sinus", "scheduled_time": 6430, "room": 2},
    {"pid": "E42", "surgery_type": "microlaryngoscopy", "scheduled_time": 6490, "room": 1},
    {"pid": "E43", "surgery_type": "buccal mucosa bioppsy", "scheduled_time": 6555, "room": 1},
    {"pid": "E44", "surgery_type": "septoplasty", "scheduled_time": 6340, "room": 2},
    {"pid": "E45", "surgery_type": "buccal mucosa bioppsy", "scheduled_time": 6555, "room": 2},
    {"pid": "E46", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 6585, "room": 1},
    {"pid": "E47", "surgery_type": "adenotonsillectomy", "scheduled_time": 6495, "room": 2},
    {"pid": "E48", "surgery_type": "thyroidectomy", "scheduled_time": 6240, "room": 1},
    {"pid": "E49", "surgery_type": "modified radical mastoidectomy", "scheduled_time": 6240, "room": 2},
    {"pid": "E50", "surgery_type": "septoplasty", "scheduled_time": 6400, "room": 1},
]

# =========================
# HÀM TIỆN ÍCH
# =========================
def minutes_to_hhmm(t):
    """Đổi số phút -> Ngày X, HH:MM"""
    day = int(t // MINUTES_PER_DAY) + 1  # Ngày 1-5
    time_in_day = t % MINUTES_PER_DAY
    h = int(time_in_day // 60)
    m = int(time_in_day % 60)
    return f"Ngày {day}, {h:02d}:{m:02d}"

def is_work_time(t):
    """
    Kiểm tra xem thời điểm t có nằm trong giờ làm việc không.
    Giờ làm việc: 8h-18h mỗi ngày, 5 ngày/tuần
    """
    # Tính ngày trong tuần (0-6, trong đó 0-4 là ngày làm việc)
    day_of_week = int(t // MINUTES_PER_DAY)
    
    # Nếu vượt quá ngày làm việc thứ 5
    if day_of_week >= WORK_DAYS:
        return False
    
    # Tính giờ trong ngày (0-23)
    time_in_day = t % MINUTES_PER_DAY
    hour_in_day = time_in_day / 60
    
    # Kiểm tra trong khoảng 8h-17h
    return SHIFT_START_HOUR <= hour_in_day < SHIFT_END_HOUR
def get_work_time_in_day(t):
    """
    Trả về số phút kể từ đầu ca làm việc trong ngày.
    Ví dụ: nếu t = 1440 + 480 = 1920 (ngày 2, 8h sáng)
           -> trả về 60 (8h - 7h = 1 tiếng)
    """
    time_in_day = t % MINUTES_PER_DAY
    return time_in_day - (SHIFT_START_HOUR * 60)

def in_shift(meta, start_time, duration): 
    """
    Kiểm tra ca mổ [start_time, start_time + duration] có nằm trọn 
    trong ca làm việc không.
    """
    # Kiểm tra thời điểm bắt đầu có trong giờ làm việc không
    if not is_work_time(start_time):
        return False
    
    # Kiểm tra thời điểm kết thúc có trong giờ làm việc không
    end_time = start_time + duration
    if not is_work_time(end_time - 1):  # -1 để tránh lỗi biên
        return False
    
    # Kiểm tra ca mổ có nằm trong cùng 1 ngày không
    start_day = int(start_time // MINUTES_PER_DAY)
    end_day = int((end_time - 1) // MINUTES_PER_DAY)
    
    if start_day != end_day:
        return False  # Ca mổ không được kéo dài qua ngày
    
    # Kiểm tra với shift cụ thể của bác sĩ: khi các bác sĩ có ca làm việc khác nhau thì có thể dùng hàm này để check 
    work_time_start = get_work_time_in_day(start_time)
    work_time_end = get_work_time_in_day(end_time)
    
    return (meta["shift_start"] <= work_time_start) and \
           (work_time_end <= meta["shift_end"])

def res_free_now(resource):
    """
    Kiểm tra resource rảnh NGAY LÚC NÀY:
    - count < capacity: còn slot trống
    - len(queue) == 0: không có người xếp hàng chờ trước
    """
    return (resource.count < resource.capacity) and (len(resource.queue) == 0)

def eligible_sets(surgery_type, surgeons_meta):
    """
    Lọc các bác sĩ có skill phù hợp với loại phẫu thuật:
    - mains: có trong can_main
    - assists: có trong can_assist
    """
    mains = [name for name, meta in surgeons_meta.items() if surgery_type in meta["can_main"]]
    assists = [name for name, meta in surgeons_meta.items() if surgery_type in meta["can_assist"]]
    return mains, assists

def find_preemptable_surgeries(env, required_surgeons, required_room, duration, scheduled_surgeries):
    """
    Tìm các ca elective có thể bị dời để nhường chỗ cho urgent.
    
    Tiêu chí:
    - Status == "scheduled" (chưa bắt đầu thực hiện)
    - Sử dụng một trong các bác sĩ cần thiết HOẶC phòng cần thiết
    - Thời gian lên lịch chồng lấn với [env.now, env.now + duration]
    
    Returns: Danh sách surgeries sắp theo thời gian bắt đầu (muộn nhất trước)
    """
    preemptable = []
    urgent_start = env.now
    urgent_end = env.now + duration
    
    for pid, surgery in scheduled_surgeries.items():
        if surgery["status"] != "scheduled":
            continue
            
        surgery_start = surgery["scheduled_time"]
        surgery_end = surgery_start + surgery["duration"]
        
        # Kiểm tra thời gian có chồng lấn không
        if surgery_start >= urgent_end or surgery_end <= urgent_start:
            continue  # Không chồng lấn
            
        # Kiểm tra có dùng chung resource không
        team = surgery.get("team", {})
        if team is None:
            team = {}
        surgeons_used = {team.get("main"), team.get("assist1"), team.get("assist2")} - {None}
        room_used = surgery.get("room")
        
        if surgeons_used & required_surgeons or room_used == required_room:
            preemptable.append(surgery)
    
    # Sắp xếp theo thời gian bắt đầu muộn nhất trước (dời ca muộn trước)
    preemptable.sort(key=lambda x: x["scheduled_time"], reverse=True)
    return preemptable

def is_available_at_time(surgeon, start_time, duration, surgeons_meta, scheduled_surgeries):
    """Kiểm tra bác sĩ có rảnh trong khoảng [start_time, start_time + duration] không"""
    end_time = start_time + duration
    
    # Kiểm tra ca làm việc
    if not in_shift(surgeons_meta[surgeon], start_time, duration):
        return False
    
    # Kiểm tra có ca nào đã lên lịch chồng lấn không
    for surgery in scheduled_surgeries.values():
        if surgery["status"] not in ["scheduled", "executing"]:
            continue
            
        team = surgery.get("team", {})
        if surgeon not in {team.get("main"), team.get("assist1"), team.get("assist2")}:
            continue
            
        surgery_start = surgery["scheduled_time"]
        surgery_end = surgery_start + surgery["duration"]
        
        # Kiểm tra chồng lấn
        if not (end_time <= surgery_start or start_time >= surgery_end):
            return False
    
    return True

def is_room_available_at_time(room_num, start_time, duration, scheduled_surgeries):
    """Kiểm tra phòng có rảnh trong khoảng [start_time, start_time + duration] không"""
    end_time = start_time + duration
    
    for surgery in scheduled_surgeries.values():
        if surgery["status"] not in ["scheduled", "executing"]:
            continue
            
        if surgery.get("room") != room_num:
            continue
            
        surgery_start = surgery["scheduled_time"]
        surgery_end = surgery_start + surgery["duration"]
        
        # Kiểm tra chồng lấn
        if not (end_time <= surgery_start or start_time >= surgery_end):
            return False
    
    return True

def find_earliest_slot(env, surgery_type, duration, start_search_time, end_search_time, 
                       surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries):
    """
    Tìm slot sớm nhất để xếp lịch một ca mổ.
    
    Returns: (slot_time, room_number, team) hoặc None nếu không tìm được
    """
    current_time = start_search_time
    
    # Lấy danh sách bác sĩ có skill phù hợp
    mains, assists = eligible_sets(surgery_type, surgeons_meta)
    if not mains or not assists:
        return None
    
    assist2_pool = [f"S{i}" for i in range(7, 11)]
    
    # Thử từng phút cho đến end_search_time
    while current_time <= end_search_time - duration:
        if not is_work_time(current_time):
            current_time += 1
            continue
            
        # Thử tìm team + room rảnh tại thời điểm này
        for main in mains:
            if not is_available_at_time(main, current_time, duration, surgeons_meta, scheduled_surgeries):
                continue
                
            for a1 in assists:
                if a1 == main:
                    continue
                if not is_available_at_time(a1, current_time, duration, surgeons_meta, scheduled_surgeries):
                    continue
                    
                for a2 in assist2_pool:
                    if a2 in {main, a1}:
                        continue
                    if not is_available_at_time(a2, current_time, duration, surgeons_meta, scheduled_surgeries):
                        continue
                        
                    # Tìm được team, giờ tìm phòng
                    for room_num in room_resources.keys():
                        if is_room_available_at_time(room_num, current_time, duration, scheduled_surgeries):
                            return (current_time, room_num, {"main": main, "assist1": a1, "assist2": a2})
        
        current_time += 1
    
    return None

def reschedule_surgery(env, surgery, scheduled_surgeries, surgeons_meta, surgeon_resources, room_resources, stats):
    """
    Cố gắng xếp lại lịch cho ca mổ bị dời.
    
    Thứ tự ưu tiên:
    1. Cuối ngày hiện tại
    2. Ngày tiếp theo (tìm slot sớm nhất)
    
    Returns: True nếu xếp lại thành công, False nếu delay
    """
    surgery_type = surgery["surgery_type"]
    duration = surgery["duration"]
    pid = surgery["pid"]
    original_time = surgery["scheduled_time"]
    
    # Tính ngày hiện tại
    current_day = int(env.now // MINUTES_PER_DAY)
    end_of_today = (current_day + 1) * MINUTES_PER_DAY - (24 - SHIFT_END_HOUR) * 60
    
    # Thử 1: Cuối ngày hôm nay
    result = find_earliest_slot(env, surgery_type, duration, env.now, end_of_today,
                               surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries)
    
    if result:
        new_time, new_room, new_team = result
        surgery["scheduled_time"] = new_time
        surgery["room"] = new_room
        surgery["team"] = new_team
        surgery["status"] = "scheduled"
        
        stats["preempted_electives"].append({
            "pid": pid,
            "original_time": original_time,
            "new_time": new_time,
            "reason": "Preempted by urgent patient, rescheduled same day"
        })
        return True
    
    # Thử 2: Ngày tiếp theo
    next_day_start = (current_day + 1) * MINUTES_PER_DAY + SHIFT_START_HOUR * 60
    next_day_end = (current_day + 1) * MINUTES_PER_DAY + SHIFT_END_HOUR * 60
    
    if next_day_start < SIM_DURATION:
        result = find_earliest_slot(env, surgery_type, duration, next_day_start, next_day_end,
                                   surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries)
        
        if result:
            new_time, new_room, new_team = result
            surgery["scheduled_time"] = new_time
            surgery["room"] = new_room
            surgery["team"] = new_team
            surgery["status"] = "scheduled"
            
            stats["preempted_electives"].append({
                "pid": pid,
                "original_time": original_time,
                "new_time": new_time,
                "reason": "Preempted by urgent patient, rescheduled next day"
            })
            return True
    
    # Không xếp được lại -> delay
    surgery["status"] = "delayed"
    stats["delayed_elective_patients"].append({
        "patient": pid,
        "surgery_type": surgery_type,
        "scheduled_time": original_time,
        "reason": "Preempted by urgent and cannot reschedule"
    })
    return False

def pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources):
    """
    Chọn ngẫu nhiên bộ ba bác sĩ rảnh NGAY BÂY GIỜ:
      - 1 Main từ nhóm main rảnh & trong ca
      - 1 Assist1 từ nhóm assist rảnh & trong ca (khác Main)
      - 1 Assist2 từ S7-S10 rảnh & trong ca (khác Main và Assist1)
    Trả về tuple (main, a1, a2) hoặc None nếu không có tổ hợp hợp lệ.
    """
    mains, assists = eligible_sets(surgery_type, surgeons_meta)
    
    # Danh sách assist2: S7-S10
    assist2_pool_names = [f"S{i}" for i in range(7, 10)]

    # Lọc main rảnh + đủ ca làm
    main_free = [
        s for s in mains
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]
    
    # Lọc assist1 rảnh + đủ ca làm
    assist1_free = [
        s for s in assists
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]
    
    # Lọc assist2 (từ S7-S10) rảnh + đủ ca làm
    assist2_free = [
        s for s in assist2_pool_names
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]

    if not main_free or len(assist1_free) < 1 or len(assist2_free) < 1:
        return None

    # Chọn ngẫu nhiên 1 main
    main = random.choice(main_free)
    
    # Chọn assist1 (khác main)
    assist1_pool = [a for a in assist1_free if a != main]
    if len(assist1_pool) < 1:
        return None
    a1 = random.choice(assist1_pool)
    
    # Chọn assist2 từ S7-S10 (khác main và khác assist1)
    assist2_pool = [a for a in assist2_free if a != main and a != a1]
    if len(assist2_pool) < 1:
        return None
    a2 = random.choice(assist2_pool)

    return main, a1, a2

# =========================
# PROCESS CHO BỆNH NHÂN URGENT
# =========================
def urgent_patient_process(env, pid, surgery_type, surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries, stats):
    """
    Process cho bệnh nhân urgent (cấp cứu):
    - Đến ngẫu nhiên, có ưu tiên tuyệt đối.
    - Có thể preempt (dời) các ca elective đã lên lịch nhưng chưa thực hiện.
    - Chờ tối đa WAIT_WINDOW (30 phút).
    - Có thể lố giờ làm việc (ghi nhận overtime).
    """
    arrival_time = env.now
    duration = SURGERY_TYPES[surgery_type]

    mains_all, assists_all = eligible_sets(surgery_type, surgeons_meta)
    if len(mains_all) < 1 or len(assists_all) < 1:
        stats["rejected_no_skill_urgent"] += 1
        return

    deadline = arrival_time + WAIT_WINDOW
    assigned = False
    
    while env.now <= deadline:
        # Bước 1: Thử tìm team + room rảnh ngay
        triad = pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources)
        
        # Chọn phòng
        selected_room = None
        if triad is not None:
            # Tìm phòng rảnh
            for room_num in room_resources.keys():
                if res_free_now(room_resources[room_num]):
                    # Kiểm tra phòng có bị chồng lịch với elective scheduled không
                    if is_room_available_at_time(room_num, env.now, duration, scheduled_surgeries):
                        selected_room = room_num
                        break
            
            # Nếu không có phòng hoàn toàn rảnh, chọn phòng kết thúc sớm nhất
            if selected_room is None:
                earliest_room = None
                earliest_time = float('inf')
                for room_num in room_resources.keys():
                    # Tìm ca đang dùng room này
                    room_finish_time = env.now
                    for surgery in scheduled_surgeries.values():
                        if surgery["status"] == "executing" and surgery.get("room") == room_num:
                            surgery_end = surgery["scheduled_time"] + surgery["duration"]
                            room_finish_time = max(room_finish_time, surgery_end)
                    
                    if room_finish_time < earliest_time:
                        earliest_time = room_finish_time
                        earliest_room = room_num
                
                selected_room = earliest_room
        
        # Bước 2: Nếu không có team rảnh, thử preempt electives
        if triad is None or selected_room is None:
            # Tìm team cần thiết
            main_needed = random.choice(mains_all) if mains_all else None
            a1_needed = random.choice([a for a in assists_all if a != main_needed]) if assists_all else None
            assist2_pool = [f"S{i}" for i in range(7, 11)]
            a2_needed = random.choice([a for a in assist2_pool if a not in {main_needed, a1_needed}]) if assist2_pool else None
            
            if main_needed and a1_needed and a2_needed:
                required_surgeons = {main_needed, a1_needed, a2_needed}
                
                # Tìm electives có thể preempt
                preemptable = find_preemptable_surgeries(env, required_surgeons, selected_room, duration, scheduled_surgeries)
                
                if preemptable:
                    # Preempt các ca cần thiết (đã sắp xếp theo thời gian muộn trước)
                    for surgery_to_preempt in preemptable:
                        surgery_to_preempt["status"] = "preempted"
                        # Reschedule
                        reschedule_surgery(env, surgery_to_preempt, scheduled_surgeries, surgeons_meta, surgeon_resources, room_resources, stats)
                    
                    # Sau khi preempt, thử lại
                    triad = (main_needed, a1_needed, a2_needed)
        
        # Bước 3: Nếu có team + room, thực hiện
        if triad is not None and selected_room is not None:
            main, a1, a2 = triad

            with surgeon_resources[main].request() as main_req, \
                 surgeon_resources[a1].request() as a1_req, \
                 surgeon_resources[a2].request() as a2_req, \
                 room_resources[selected_room].request() as room_req:

                yield main_req & a1_req & a2_req & room_req

                start_time = env.now
                
                # Urgent CÓ THỂ lố giờ, nhưng ghi nhận
                overtime_surgeons = []
                for surgeon in [main, a1, a2]:
                    if not in_shift(surgeons_meta[surgeon], start_time, duration):
                        # Tính overtime
                        shift_end = surgeons_meta[surgeon]["shift_end"]
                        work_end = get_work_time_in_day(start_time) + duration
                        if work_end > shift_end:
                            overtime_minutes = work_end - shift_end
                            overtime_surgeons.append({
                                "surgeon": surgeon,
                                "overtime_minutes": overtime_minutes
                            })
                
                # Ghi nhận overtime
                if overtime_surgeons:
                    stats["urgent_overtime"].append({
                        "patient": f"U{pid:03d}",
                        "surgeons": overtime_surgeons
                    })
                
                # Thực hiện ca mổ
                stats["served_urgent"] += 1 
                stats["log"].append({
                    "patient": f"U{pid:03d}",
                    "type": "URGENT",
                    "surgery_type": surgery_type,
                    "arrival": arrival_time,
                    "start": start_time,
                    "end": start_time + duration + MEAN_REST_TIME,
                    "wait": start_time - arrival_time,
                    "main": main,
                    "assist1": a1,
                    "assist2": a2,
                    "room": selected_room,
                })
                
                yield env.timeout(duration + MEAN_REST_TIME)
                assigned = True
                break

        # Chờ 1 phút rồi thử lại
        yield env.timeout(1)

    if not assigned:
        stats["rejected_wait_timeout"] += 1

# =========================
# PROCESS CHO BỆNH NHÂN ELECTIVE
# =========================
def elective_patient_process(env, pid, surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries, stats):
    """
    Process cho bệnh nhân elective (mổ phiên):
    - Đã được lên lịch trước (thời gian và phòng).
    - Chọn team động (main, assist1, assist2) khi đến giờ lên lịch.
    - Có thể bị preempt bởi urgent.
    - Không được lố giờ làm việc.
    """
    surgery = scheduled_surgeries[pid]
    
    # Kiểm tra surgery có bị preempt hoặc delay trước khi bắt đầu không
    if surgery["status"] in ["preempted", "delayed"]:
        return  # Đã bị xử lý rồi
    
    arrival_time = surgery["scheduled_time"]
    surgery_type = surgery["surgery_type"]
    duration = surgery["duration"]
    assigned_room = surgery["room"]
    
    # Kiểm tra xem có đủ bác sĩ có skill phù hợp không
    mains_all, assists_all = eligible_sets(surgery_type, surgeons_meta)
    if len(mains_all) < 1 or len(assists_all) < 1:
        stats["rejected_no_skill_elective"] += 1
        surgery["status"] = "delayed"
        stats["delayed_elective_patients"].append({
            "patient": pid,
            "surgery_type": surgery_type,
            "scheduled_time": arrival_time,
            "reason": "No surgeons with required skills",
        })
        return

    # Deadline: hết ngày làm việc hoặc hết mô phỏng
    deadline = min(SIM_DURATION, arrival_time + MINUTES_PER_DAY)
    assigned = False

    while env.now <= deadline:
        # Kiểm tra lại status (có thể bị preempt trong lúc chờ)
        if surgery["status"] in ["preempted", "delayed"]:
            return
            
        # Thử chọn team rảnh ngay bây giờ
        triad = pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources)
        if triad is not None:
            main, a1, a2 = triad

            # Acquire surgeons and room
            with surgeon_resources[main].request() as main_req, \
                 surgeon_resources[a1].request() as a1_req, \
                 surgeon_resources[a2].request() as a2_req, \
                 room_resources[assigned_room].request() as room_req:

                yield main_req & a1_req & a2_req & room_req

                start_time = env.now
                
                # Kiểm tra lại status sau khi acquire (có thể bị preempt)
                if surgery["status"] in ["preempted", "delayed"]:
                    return
                
                # Kiểm tra ca làm việc - Elective KHÔNG ĐƯỢC lố giờ
                if not (in_shift(surgeons_meta[main], start_time, duration) and
                        in_shift(surgeons_meta[a1], start_time, duration) and
                        in_shift(surgeons_meta[a2], start_time, duration)):
                    # Lỗ giờ làm, bỏ qua và thử lại
                    pass
                else:
                    # Tiến hành mổ
                    surgery["status"] = "executing"
                    surgery["team"] = {"main": main, "assist1": a1, "assist2": a2}
                    
                    stats["served_elective"] += 1
                    stats["log"].append({
                        "patient": pid,
                        "type": "ELECTIVE",
                        "surgery_type": surgery_type,
                        "arrival": arrival_time,
                        "start": start_time,
                        "end": start_time + duration + MEAN_REST_TIME,
                        "wait": start_time - arrival_time,
                        "main": main,
                        "assist1": a1,
                        "assist2": a2,
                        "room": assigned_room,
                    })
                    
                    yield env.timeout(duration + MEAN_REST_TIME)
                    surgery["status"] = "completed"
                    assigned = True
                    break

        # Nếu chưa tìm được team hoặc bị lố giờ, chờ 1 phút rồi thử lại
        yield env.timeout(1)

    # Nếu hết thời hạn mà chưa được mổ
    if not  assigned and surgery["status"] not in ["preempted", "delayed"]:
        surgery["status"] = "delayed"
        stats["delayed_elective_patients"].append({
            "patient": pid,
            "surgery_type": surgery_type,
            "scheduled_time": arrival_time,
            "reason": "Suitable team not found",
        })

# =========================
# GENERATOR: SINH BỆNH NHÂN URGENT
# =========================
def urgent_patient_generator(env, surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries, stats):
    """
    Liên tục sinh bệnh nhân urgent, CHỈ TRONG GIỜ LÀM VIỆC.
    """
    pid = 0
    while True:
        inter_arrival = random.expovariate(1.0 / MEAN_INTER_ARRIVAL)
        yield env.timeout(inter_arrival)
        if env.now > SIM_DURATION:
            break
        
        # BỎ QUA nếu không phải giờ làm việc
        if not is_work_time(env.now):
            continue
        pid += 1
        surgery_type = random.choice(list(SURGERY_TYPES.keys()))
        stats["arrived_urgent"] += 1
        env.process(
            urgent_patient_process(
                env, pid, surgery_type,
                surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries, stats
            )
        )

# =========================
# GENERATOR: ĐỌC LỊCH BỆNH NHÂN ELECTIVE
# =========================
def elective_scheduler(env, schedule_list, surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries, stats):
    """
    Đọc danh sách ELECTIVE_SCHEDULE và đưa bệnh nhân vào hệ thống đúng thời gian.
    Populate scheduled_surgeries tracker cho preemption.
    """
    for surgery_details in schedule_list:
        pid = surgery_details["pid"]
        surgery_type = surgery_details["surgery_type"]
        scheduled_time = surgery_details["scheduled_time"]
        room = surgery_details["room"]
        duration = SURGERY_TYPES[surgery_type]
        
        # Populate scheduled_surgeries tracker
        scheduled_surgeries[pid] = {
            "pid": pid,
            "surgery_type": surgery_type,
            "scheduled_time": scheduled_time,
            "room": room,
            "duration": duration,
            "status": "scheduled",  # scheduled, executing, completed, preempted, delayed
            "team": None  # Sẽ được gán  khi chọn team
        }
        
        if env.now < scheduled_time:
            yield env.timeout(scheduled_time - env.now)
            
        stats["arrived_elective"] += 1
        
        env.process(
            elective_patient_process(
                env, pid,
                surgeons_meta, surgeon_resources, room_resources, scheduled_surgeries, stats
            )
        )

# =========================
# CHẠY MÔ PHỎNG
# =========================
def run_simulation():
    env = simpy.Environment()

    surgeon_resources = {name: simpy.Resource(env, capacity=1) for name in SURGEONS}
    room_resources = {i: simpy.Resource(env, capacity=1) for i in range(1, NUM_OPERATING_ROOMS + 1)}
    
    # Track scheduled surgeries for preemption
    scheduled_surgeries = {}

    stats = {
        "arrived_urgent": 0,
        "arrived_elective": 0,
        "served_urgent": 0,
        "served_elective": 0,
        "rejected_no_skill_urgent": 0,
        "rejected_no_skill_elective": 0,
        "rejected_wait_timeout": 0,
        "rejected_shift_ended": 0,
        "delayed_elective_patients": [],
        "preempted_electives": [],
        "urgent_overtime": [],
        "log": [],
    }

    # Khởi động generators
    env.process(elective_scheduler(env, ELECTIVE_PATIENTS, SURGEONS, surgeon_resources, room_resources, scheduled_surgeries, stats))
    env.process(urgent_patient_generator(env, SURGEONS, surgeon_resources, room_resources, scheduled_surgeries, stats))

    env.run()

    # ======= BÁO CÁO KẾT QUẢ =======
    print("=" * 80)
    print("KẾT QUẢ MÔ PHỎNG (1 tuần)")
    print("=" * 80)
    print(f"Tổng số bệnh nhân đến (Urgent):     {stats['arrived_urgent']}")
    print(f"Tổng số bệnh nhân đến (Elective):   {stats['arrived_elective']}")
    print("-" * 40)
    print(f"Số ca mổ thực hiện (Urgent):        {stats['served_urgent']}")
    print(f"Số ca mổ thực hiện (Elective):      {stats['served_elective']}")
    print(f"→ TỔNG SỐ CA MỔ THỰC HIỆN:          {stats['served_urgent'] + stats['served_elective']}")
    print("-" * 40)
    print(f"Hủy (Urgent - không đủ skill):      {stats['rejected_no_skill_urgent']}")
    print(f"Hủy (Urgent - chờ > 30'):           {stats['rejected_wait_timeout']}")
    print(f"Hủy (Elective - không đủ skill):    {stats['rejected_no_skill_elective']}")
    print(f"Hủy (Elective - lố giờ làm):        {stats['rejected_shift_ended']}")
    print(f"Bệnh nhân Elective bị trễ:          {len(stats['delayed_elective_patients'])}")
    print()

    # In danh sách bệnh nhân bị trễ
    if stats["delayed_elective_patients"]:
        print("=" * 80)
        print("DANH SÁCH BỆNH NHÂN ELECTIVE BỊ TRỄ (DELAYED)")
        print("=" * 80)
        for delayed in stats["delayed_elective_patients"]:
            print(f"  {delayed['patient']:>5s} | {delayed['surgery_type']:45s}")
            print(f"        Lý do: {delayed['reason']}")
        print()
    
    # In danh sách bệnh nhân bị preempt
    if stats["preempted_electives"]:
        print("=" * 80)
        print("DANH SÁCH CA MỔ ELECTIVE BỊ DỜI (PREEMPTED)")
        print("=" * 80)
        for preempted in stats["preempted_electives"]:
            print(f"  {preempted['pid']:>5s} | {minutes_to_hhmm(preempted['original_time']):20s} → {minutes_to_hhmm(preempted['new_time']):20s}")
            print(f"        Lý do: {preempted['reason']}")
        print()
    
    # In danh sách urgent overtime
    if stats["urgent_overtime"]:
        print("=" * 80)
        print("DANH SÁCH CA URGENT LÁM VƯỢT GIỜ (OVERTIME)")
        print("=" * 80)
        for overtime in stats["urgent_overtime"]:
            print(f"  {overtime['patient']:>8s}")
            for surgeon_ot in overtime["surgeons"]:
                print(f"        {surgeon_ot['surgeon']}: {surgeon_ot['overtime_minutes']} phút vượt giờ")
        print()

    # Sắp xếp và in lịch mổ
    schedule = sorted(stats["log"], key=lambda x: x["start"])
    print("=" * 80)
    print("LỊCH MỔ THỰC HIỆN (sắp theo giờ bắt đầu)")
    print("=" * 80)
    for rec in schedule:
        print(
            f"{rec['patient']:>8s} ({rec['type']:8s}) | {rec['surgery_type']:45s} | "
            f"{minutes_to_hhmm(rec['start'])} - {minutes_to_hhmm(rec['end'])} | "
            f"Room: {rec.get('room', 'N/A')} | "
            f"Main: {rec['main']} | A1: {rec['assist1']} | A2: {rec['assist2']} | "
            f"Wait: {rec['wait']:>3.0f}'"
        )

if __name__ == "__main__":
    run_simulation()
