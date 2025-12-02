# -*- coding: utf-8 -*-
import simpy  
import random
import sys
# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# =========================
# THAM SỐ MÔ PHỎNG 
# =========================
#RANDOM_SEED = 42      # Seed cho random -> tái lập kết quả (reproducible)
SIM_DURATION = 8 * 60 # Tổng thời gian "sinh bệnh nhân": 8 giờ làm việc -> 480 phút
MEAN_INTER_ARRIVAL = 150 # Trung bình 1 bệnh nhân đến mỗi 150 phút (quá trình Poisson)
# NUM_OR = 2          
WAIT_WINDOW = 30    # Time chờ tối đa nếu chưa đủ nguồn lực tại thời điểm đến (phút)
MEAN_REST_TIME = 15

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
        "shift_end":   8 * 60,
    },
    "S2": {
        "can_main":   {"septoplasty", "thyroidectomy"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar", "septoplasty", "endoscopic sinus"},
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S3": {
        "can_main":   {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy", "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy", "rhinoplasty"},
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S4": {
        "can_main":   {"adenotonsillectomy", "microlaryngoscopy", "buccal mucosa bioppsy", "excision of the lymphadenopathy from the lumbar", "septoplasty"},
        "can_assist": {"modified radical mastoidectomy", "rhinoplasty"},
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S5": {
        "can_main":   {"rhinoplasty", "endoscopic sinus"},
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S6": {
        "can_main":   {"modified radical mastoidectomy", "thyroidectomy"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar", "septoplasty", "endoscopic sinus"},
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S7": {
        "can_main":   {"rhinoplasty", "thyroidectomy"},
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S8": {
        "can_main":   {"modified radical mastoidectomy", "thyroidectomy", "sleep apnea diagnosis test"},
        "can_assist": {"rhinoplasty"},
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S9": {
        "can_main":   {"buccal mucosa bioppsy", "excision of the lymphadenopathy from the lumbar", "sleep apnea diagnosis test"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy"},
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S10": {
        "can_main":   {"modified radical mastoidectomy", "thyroidectomy", "rhinoplasty", "endoscopic sinus"},
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    # Phụ mổ 2 (Assist2) - S11 đến S20
    "S11": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S12": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S13": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S14": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S15": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S16": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S17": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S18": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S19": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    },
    "S20": {
        "can_main":   set(),
        "can_assist": set(),
        "shift_start": 0,
        "shift_end":   8 * 60,
    }
}

# =========================
# DỮ LIỆU LỊCH MỔ PHIÊN (ELECTIVE)
# =========================
ELECTIVE_SCHEDULE = [
    {"pid": "E01", "surgery_type": "thyroidectomy", "scheduled_time": 60},
    {"pid": "E02", "surgery_type": "septoplasty", "scheduled_time": 90},
    {"pid": "E03", "surgery_type": "rhinoplasty", "scheduled_time": 180},
    {"pid": "E04", "surgery_type": "adenotonsillectomy", "scheduled_time": 240},
    {"pid": "E05", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 160},
    {"pid": "E06", "surgery_type": "adenotonsillectomy", "scheduled_time": 100},
    {"pid": "E07", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 300},
    {"pid": "E08", "surgery_type": "septoplasty", "scheduled_time": 350},
    {"pid": "E09", "surgery_type": "adenotonsillectomy", "scheduled_time": 250},
    {"pid": "E10", "surgery_type": "thyroidectomy", "scheduled_time": 400},
    {"pid": "E11", "surgery_type": "thyroidectomy", "scheduled_time": 325},
    {"pid": "E12", "surgery_type": "rhinoplasty", "scheduled_time": 420},
    {"pid": "E13", "surgery_type": "endoscopic sinus", "scheduled_time": 195},
    {"pid": "E14", "surgery_type": "modified radical mastoidectomy", "scheduled_time": 365},
    {"pid": "E15", "surgery_type": "buccal mucosa bioppsy", "scheduled_time": 180},
    {"pid": "E16", "surgery_type": "endoscopic sinus", "scheduled_time": 405},
    {"pid": "E17", "surgery_type": "buccal mucosa bioppsy", "scheduled_time": 120},
    {"pid": "E18", "surgery_type": "modified radical mastoidectomy", "scheduled_time": 45},
    {"pid": "E19", "surgery_type": "excision of the lymphadenopathy from the lumbar", "scheduled_time": 415},
    {"pid": "E20", "surgery_type": "sleep apnea diagnosis test", "scheduled_time": 460},
]

# =========================
# HÀM TIỆN ÍCH
# =========================
def minutes_to_hhmm(t):
    """Đổi số phút kể từ mốc 0 -> chuỗi HH:MM (chỉ để in đẹp)."""
    h = int(t // 60)
    m = int(t % 60)
    return f"{h:02d}:{m:02d}"

def in_shift(meta, start_time, duration):
    """Kiểm tra ca mổ [start_time, start_time + duration] có nằm trọn trong ca làm của bác sĩ không."""
    return (meta["shift_start"] <= start_time) and (start_time + duration <= meta["shift_end"])

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

def pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources):
    """
    Chọn ngẫu nhiên bộ ba bác sĩ rảnh NGAY BÂY GIỜ:
      - 1 Main từ nhóm main rảnh & trong ca
      - 1 Assist1 từ nhóm assist rảnh & trong ca (khác Main)
      - 1 Assist2 từ S11-S20 rảnh & trong ca (khác Main và Assist1)
    Trả về tuple (main, a1, a2) hoặc None nếu không có tổ hợp hợp lệ.
    """
    mains, assists = eligible_sets(surgery_type, surgeons_meta)
    
    # Danh sách assist2: S11-S20
    assist2_pool_names = [f"S{i}" for i in range(11, 21)]

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
    
    # Lọc assist2 (từ S11-S20) rảnh + đủ ca làm
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
    
    # Chọn assist2 từ S11-S20 (khác main và khác assist1)
    assist2_pool = [a for a in assist2_free if a != main and a != a1]
    if len(assist2_pool) < 1:
        return None
    a2 = random.choice(assist2_pool)

    return main, a1, a2

# =========================
# PROCESS CHO BỆNH NHÂN URGENT
# =========================
def urgent_patient_process(env, pid, surgery_type, surgeons_meta, surgeon_resources, stats):
    """
    Process cho bệnh nhân urgent (cấp cứu):
    - Đến ngẫu nhiên.
    - Chờ tối đa WAIT_WINDOW (30 phút), liên tục "thăm dò" tài nguyên rảnh.
    - Nếu không được mổ sau WAIT_WINDOW, sẽ bị "hủy".
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
        triad = pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources)
        if triad is not None:
            main, a1, a2 = triad

            with surgeon_resources[main].request() as main_req, \
                 surgeon_resources[a1].request() as a1_req, \
                 surgeon_resources[a2].request() as a2_req:

                yield main_req & a1_req & a2_req

                start_time = env.now
                if not (in_shift(surgeons_meta[main], start_time, duration) and
                        in_shift(surgeons_meta[a1], start_time, duration) and
                        in_shift(surgeons_meta[a2], start_time, duration)):
                    pass
                else:
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
                    })
                    
                    yield env.timeout(duration + MEAN_REST_TIME)
                    assigned = True
                    break

        yield env.timeout(1)

    if not assigned:
        stats["rejected_wait_timeout"] += 1

# =========================
# PROCESS CHO BỆNH NHÂN ELECTIVE
# =========================
def elective_patient_process(env, surgery_details, surgeons_meta, surgeon_resources, stats):
    """
    Process cho bệnh nhân elective (mổ phiên):
    - Đã được lên lịch trước (thời gian).
    - Chọn team động (main, assist1, assist2) khi đến giờ lên lịch.
    - Thăm dò (poll) liên tục cho đến hết ngày làm việc.
    - Nếu không tìm được team phù hợp đến hết ngày → delayed.
    """
    arrival_time = env.now
    pid = surgery_details["pid"]
    surgery_type = surgery_details["surgery_type"]
    duration = SURGERY_TYPES[surgery_type]
    
    # Kiểm tra xem có đủ bác sĩ có skill phù hợp không
    mains_all, assists_all = eligible_sets(surgery_type, surgeons_meta)
    if len(mains_all) < 1 or len(assists_all) < 1:
        stats["rejected_no_skill_elective"] += 1
        stats["delayed_elective_patients"].append({
            "patient": pid,
            "surgery_type": surgery_type,
            "scheduled_time": arrival_time,
            "reason": "Không có bác sĩ có skill phù hợp",
        })
        return

    deadline = SIM_DURATION  # Hết ngày làm việc
    assigned = False

    while env.now <= deadline:
        # Thử chọn team rảnh ngay bây giờ
        triad = pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources)
        if triad is not None:
            main, a1, a2 = triad

            with surgeon_resources[main].request() as main_req, \
                 surgeon_resources[a1].request() as a1_req, \
                 surgeon_resources[a2].request() as a2_req:

                yield main_req & a1_req & a2_req

                start_time = env.now
                
                # Kiểm tra ca làm việc (có thể đã thay đổi do chờ)
                if not (in_shift(surgeons_meta[main], start_time, duration) and
                        in_shift(surgeons_meta[a1], start_time, duration) and
                        in_shift(surgeons_meta[a2], start_time, duration)):
                    # Lỗ giờ làm, bỏ qua và thử lại
                    pass
                else:
                    # Tiến hành mổ
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
                    })
                    
                    yield env.timeout(duration + MEAN_REST_TIME)
                    assigned = True
                    break

        # Nếu chưa tìm được team hoặc bị lố giờ, chờ 1 phút rồi thử lại
        yield env.timeout(1)

    # Nếu hết ngày mà chưa được mổ
    if not assigned:
        stats["delayed_elective_patients"].append({
            "patient": pid,
            "surgery_type": surgery_type,
            "scheduled_time": arrival_time,
            "reason": "Không tìm được team phù hợp trong ngày làm việc",
        })

# =========================
# GENERATOR: SINH BỆNH NHÂN URGENT
# =========================
def urgent_patient_generator(env, surgeons_meta, surgeon_resources, stats):
    """
    Liên tục sinh bệnh nhân urgent với khoảng cách theo phân phối Exponential.
    """
    pid = 0
    while True:
        inter_arrival = random.expovariate(1.0 / MEAN_INTER_ARRIVAL)
        yield env.timeout(inter_arrival)

        if env.now > SIM_DURATION:
            break

        pid += 1
        surgery_type = random.choice(list(SURGERY_TYPES.keys()))
        stats["arrived_urgent"] += 1

        env.process(
            urgent_patient_process(
                env, pid, surgery_type,
                surgeons_meta, surgeon_resources, stats
            )
        )

# =========================
# GENERATOR: ĐỌC LỊCH BỆNH NHÂN ELECTIVE
# =========================
def elective_scheduler(env, schedule_list, surgeons_meta, surgeon_resources, stats):
    """
    Đọc danh sách ELECTIVE_SCHEDULE và đưa bệnh nhân vào hệ thống đúng thời gian.
    """
    for surgery_details in schedule_list:
        scheduled_time = surgery_details["scheduled_time"]
        
        if env.now < scheduled_time:
            yield env.timeout(scheduled_time - env.now)
            
        stats["arrived_elective"] += 1
        
        env.process(
            elective_patient_process(
                env, surgery_details, 
                surgeons_meta, surgeon_resources, stats
            )
        )

# =========================
# CHẠY MÔ PHỎNG
# =========================
def run_simulation():
    env = simpy.Environment()

    surgeon_resources = {name: simpy.Resource(env, capacity=1) for name in SURGEONS}
    # Không còn sử dụng or_resource

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
        "log": [],
    }

    # Khởi động generators
    env.process(elective_scheduler(env, ELECTIVE_SCHEDULE, SURGEONS, surgeon_resources, stats))
    env.process(urgent_patient_generator(env, SURGEONS, surgeon_resources, stats))

    env.run()

    # ======= BÁO CÁO KẾT QUẢ =======
    print("=" * 80)
    print("KẾT QUẢ MÔ PHỎNG (1 ngày)")
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

    # Sắp xếp và in lịch mổ
    schedule = sorted(stats["log"], key=lambda x: x["start"])
    print("=" * 80)
    print("LỊCH MỔ THỰC HIỆN (sắp theo giờ bắt đầu)")
    print("=" * 80)
    for rec in schedule:
        print(
            f"{rec['patient']:>8s} ({rec['type']:8s}) | {rec['surgery_type']:45s} | "
            f"{minutes_to_hhmm(rec['start'])} - {minutes_to_hhmm(rec['end'])} | "
            f"Main: {rec['main']} | A1: {rec['assist1']} | A2: {rec['assist2']} | "
            f"Wait: {rec['wait']:>3.0f}'"
        )

if __name__ == "__main__":
    run_simulation()
