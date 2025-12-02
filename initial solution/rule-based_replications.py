# -*- coding: utf-8 -*-
import simpy  
import random
import sys
import json
from collections import defaultdict

# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# =========================
# THAM SỐ MÔ PHỎNG 
# =========================
NUM_REPLICATIONS = 50
SIM_DURATION = 8 * 60 # Tổng thời gian "sinh bệnh nhân": 8 giờ làm việc -> 480 phút
MEAN_INTER_ARRIVAL = 15  # Trung bình 1 bệnh nhân đến mỗi 15 phút (quá trình Poisson)
NUM_OR = 2            # Số phòng mổ 
WAIT_WINDOW = 30      # Time chờ tối đa nếu chưa đủ nguồn lực tại thời điểm đến (phút)
MEAN_REST_TIME = 15

# =========================
# CẤU HÌNH DỮ LIỆU 
# =========================
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
        "can_assist": {"modified radical mastoidectomy", "thyroidectomy", "rhinoplasty"},
        "shift_start": 60,
        "shift_end":   9 * 60,
    },
    "S5": {
        "can_main":   {"rhinoplasty", "endoscopic sinus"},
        "can_assist": set(),
        "shift_start": 60,
        "shift_end":   9 * 60,
    },
    "S6": {
        "can_main":   {"modified radical mastoidectomy", "thyroidectomy"},
        "can_assist": set(),
        "shift_start": 60,
        "shift_end":   9 * 60,
    },
}

ELECTIVE_SCHEDULE = [
    {
        "pid": "E01",
        "surgery_type": "thyroidectomy",
        "scheduled_time": 60,
        "main": "S6",
        "assist1": "S3",
        "assist2": "S4",
    },
    {
        "pid": "E02",
        "surgery_type": "septoplasty",
        "scheduled_time": 90,
        "main": "S2",
        "assist1": "S1",
        "assist2": "S3",
    },
    {
        "pid": "E03",
        "surgery_type": "rhinoplasty",
        "scheduled_time": 180,
        "main": "S5",
        "assist1": "S3",
        "assist2": "S4",
    }
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
    Mục tiêu: nếu có thể bắt đầu mổ ngay thời điểm env.now thì chọn:
      - 1 Main từ nhóm main rảnh & trong ca
      - 2 Assist từ nhóm assist rảnh & trong ca (khác Main và khác nhau)
    Trả về tuple (main, a1, a2) hoặc None nếu không có tổ hợp hợp lệ ngay lúc này.
    """
    mains, assists = eligible_sets(surgery_type, surgeons_meta)

    main_free = [
        s for s in mains
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]
    assist_free = [
        s for s in assists
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]

    if not main_free or len(assist_free) < 2:
        return None

    main = random.choice(main_free)
    assist_pool = [a for a in assist_free if a != main]
    if len(assist_pool) < 2:
        return None

    a1, a2 = random.sample(assist_pool, 2)
    return main, a1, a2

# =========================
# SINH TRƯỚC DANH SÁCH BỆNH NHÂN URGENT
# =========================
def generate_patient_arrivals(seed=42):
    """
    Sinh trước danh sách bệnh nhân urgent với seed cố định.
    Trả về danh sách: [(arrival_time, pid, surgery_type), ...]
    """
    random.seed(seed)  # Seed cố định để tạo cùng tệp bệnh nhân
    
    patients = []
    current_time = 0
    pid = 0
    
    while True:
        # Sinh khoảng cách đến tiếp theo
        inter_arrival = random.expovariate(1.0 / MEAN_INTER_ARRIVAL)
        current_time += inter_arrival
        
        # Nếu quá thời gian sinh bệnh nhân thì dừng
        if current_time > SIM_DURATION:
            break
        
        pid += 1
        # Chọn loại phẫu thuật ngẫu nhiên
        surgery_type = random.choice(list(SURGERY_TYPES.keys()))
        
        patients.append({
            'arrival_time': current_time,
            'pid': pid,
            'surgery_type': surgery_type
        })
    
    return patients

# =========================
# PROCESS CHO BỆNH NHÂN
# =========================
def urgent_patient_process(env, pid, surgery_type, surgeons_meta, surgeon_resources, or_resource, stats):
    arrival_time = env.now
    duration = SURGERY_TYPES[surgery_type]

    mains_all, assists_all = eligible_sets(surgery_type, surgeons_meta)
    if len(mains_all) < 1 or len(assists_all) < 2:
        stats["rejected_no_skill"] += 1
        return

    deadline = arrival_time + WAIT_WINDOW
    assigned = False

    while env.now <= deadline:
        if res_free_now(or_resource):
            triad = pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources)
            if triad is not None:
                main, a1, a2 = triad

                with or_resource.request() as or_req, \
                     surgeon_resources[main].request() as main_req, \
                     surgeon_resources[a1].request() as a1_req, \
                     surgeon_resources[a2].request() as a2_req:

                    yield or_req & main_req & a1_req & a2_req

                    start_time = env.now
                    if not (in_shift(SURGEONS[main], start_time, duration) and
                            in_shift(SURGEONS[a1], start_time, duration) and
                            in_shift(SURGEONS[a2], start_time, duration)):
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

def elective_patient_process(env, surgery_details, surgeons_meta, surgeon_resources, or_resource, stats):
    arrival_time = env.now
    pid = surgery_details["pid"]
    surgery_type = surgery_details["surgery_type"]
    duration = SURGERY_TYPES[surgery_type]
    
    main = surgery_details["main"]
    a1 = surgery_details["assist1"]
    a2 = surgery_details["assist2"]

    with or_resource.request() as or_req, \
         surgeon_resources[main].request() as main_req, \
         surgeon_resources[a1].request() as a1_req, \
         surgeon_resources[a2].request() as a2_req:
        
        yield or_req & main_req & a1_req & a2_req
        start_time = env.now

        if not (in_shift(surgeons_meta[main], start_time, duration) and
                in_shift(surgeons_meta[a1], start_time, duration) and
                in_shift(surgeons_meta[a2], start_time, duration)):
            
            stats["rejected_shift_ended"] += 1
            return

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

def urgent_patient_generator(env, patient_list, surgeons_meta, surgeon_resources, or_resource, stats):
    """
    Đọc từ danh sách bệnh nhân đã sinh trước và đưa vào hệ thống đúng thời điểm.
    """
    for patient in patient_list:
        arrival_time = patient['arrival_time']
        
        # Đợi đến đúng thời điểm bệnh nhân đến
        if env.now < arrival_time:
            yield env.timeout(arrival_time - env.now)
        
        pid = patient['pid']
        surgery_type = patient['surgery_type']
        stats["arrived_urgent"] += 1

        env.process(
            urgent_patient_process(
                env, pid, surgery_type,
                surgeons_meta, surgeon_resources, or_resource, stats
            )
        )

def elective_scheduler(env, schedule_list, surgeons_meta, surgeon_resources, or_resource, stats):
    for surgery_details in schedule_list:
        scheduled_time = surgery_details["scheduled_time"]
        
        if env.now < scheduled_time:
            yield env.timeout(scheduled_time - env.now)
            
        stats["arrived_elective"] += 1
        
        env.process(
            elective_patient_process(
                env, surgery_details, 
                surgeons_meta, surgeon_resources, or_resource, stats
            )
        )

# =========================
# CHẠY MỘT LẦN MÔ PHỎNG
# =========================
def run_single_simulation(patient_list, seed):
    """
    Chạy một lần mô phỏng với:
    - patient_list: danh sách bệnh nhân urgent đã sinh trước (cố định)
    - seed: chỉ dùng cho việc chọn surgeon (khác nhau giữa các replication)
    """
    random.seed(seed)  # Chỉ ảnh hưởng việc chọn surgeon
    env = simpy.Environment()

    surgeon_resources = {name: simpy.Resource(env, capacity=1) for name in SURGEONS}
    or_resource = simpy.Resource(env, capacity=NUM_OR)

    stats = {
        "arrived_urgent": 0,
        "arrived_elective": 0,
        "served_urgent": 0,
        "served_elective": 0,
        "rejected_no_skill": 0,
        "rejected_wait_timeout": 0,
        "rejected_shift_ended": 0,
        "log": [],
    }

    env.process(elective_scheduler(env, ELECTIVE_SCHEDULE, SURGEONS, surgeon_resources, or_resource, stats))
    env.process(urgent_patient_generator(env, patient_list, SURGEONS, surgeon_resources, or_resource, stats))

    env.run()
    
    return stats

# =========================
# TẠO SIGNATURE CHO KẾT QUẢ
# =========================
def create_schedule_signature(stats):
    """
    Tạo một signature duy nhất cho kết quả mô phỏng.
    Signature dựa trên lịch mổ cuối cùng (danh sách ca mổ, thời gian, và team).
    """
    # Sắp xếp theo thời gian bắt đầu
    schedule = sorted(stats["log"], key=lambda x: x["start"])
    
    # Tạo signature từ các thông tin quan trọng
    signature_parts = []
    for rec in schedule:
        # Bao gồm: patient, surgery_type, start time, main, assist1, assist2
        signature_parts.append(
            f"{rec['patient']}|{rec['surgery_type']}|{rec['start']}|"
            f"{rec['main']}|{rec['assist1']}|{rec['assist2']}"
        )
    
    return "||".join(signature_parts)

# =========================
# CHẠY NHIỀU REPLICATION
# =========================
def run_multiple_replications(num_reps=NUM_REPLICATIONS):
    """Chạy nhiều replication và lọc kết quả trùng lặp"""
    
    print("=" * 70)
    print(f"CHẠY {num_reps} REPLICATIONS")
    print("=" * 70)
    
    # BƯỚC 1: Sinh trước danh sách bệnh nhân urgent (CỐ ĐỊNH cho tất cả replication)
    print("\nĐang sinh danh sách bệnh nhân urgent (cố định)...")
    patient_list = generate_patient_arrivals(seed=42)  # Seed cố định = 42
    print(f"Đã sinh {len(patient_list)} bệnh nhân urgent")
    print("Danh sách này sẽ GIỐNG HỆT NHAU cho tất cả {0} replication".format(num_reps))
    print("Chỉ việc chọn Main/Assistant surgeon sẽ khác nhau\n")
    
    all_results = []
    signatures_seen = {}  # signature -> first replication number
    unique_results = []
    duplicate_count = 0
    
    # BƯỚC 2: Chạy các replication với CÙNG danh sách bệnh nhân
    for rep in range(1, num_reps + 1):
        print(f"\rĐang chạy replication {rep}/{num_reps}...", end="", flush=True)
        
        # Sử dụng seed khác nhau CHỈ CHO VIỆC CHỌN SURGEON
        stats = run_single_simulation(patient_list, seed=rep * 1000)
        
        # Tạo signature cho kết quả
        signature = create_schedule_signature(stats)
        
        # Kiểm tra xem signature đã tồn tại chưa
        if signature in signatures_seen:
            duplicate_count += 1
            # Kết quả trùng với replication nào
            original_rep = signatures_seen[signature]
        else:
            # Kết quả unique
            signatures_seen[signature] = rep
            unique_results.append({
                "replication": rep,
                "stats": stats,
                "signature": signature
            })
        
        all_results.append({
            "replication": rep,
            "stats": stats,
            "signature": signature
        })
    
    print()  # Xuống dòng sau progress indicator
    
    return all_results, unique_results, duplicate_count, patient_list

# =========================
# IN BÁO CÁO
# =========================
def print_summary_report(all_results, unique_results, duplicate_count, patient_list):
    """In báo cáo tổng hợp"""
    
    print("\n" + "=" * 70)
    print("BÁO CÁO KẾT QUẢ REPLICATIONS")
    print("=" * 70)
    
    print(f"\n📋 THÔNG TIN DANH SÁCH BỆNH NHÂN (CỐ ĐỊNH):")
    print(f"   Số bệnh nhân urgent:           {len(patient_list)}")
    print(f"   Số bệnh nhân elective:         {len(ELECTIVE_SCHEDULE)}")
    print(f"   → Danh sách này GIỐNG HỆT NHAU cho tất cả replication")
    
    print(f"\n📊 KẾT QUẢ REPLICATION:")
    print(f"   Tổng số replication chạy:      {len(all_results)}")
    print(f"   Số kết quả unique:             {len(unique_results)}")
    print(f"   Số kết quả trùng lặp:          {duplicate_count}")
    print(f"   Tỷ lệ unique:                  {len(unique_results)/len(all_results)*100:.2f}%")
    
    # Thống kê chung từ các kết quả unique
    print("\n" + "-" * 70)
    print("THỐNG KÊ CÁC KẾT QUẢ UNIQUE:")
    print("-" * 70)
    
    for i, result in enumerate(unique_results, 1):
        stats = result["stats"]
        rep = result["replication"]
        
        print(f"\n[Unique #{i}] - Replication #{rep}:")
        print(f"  Bệnh nhân đến (Urgent):          {stats['arrived_urgent']}")
        print(f"  Bệnh nhân đến (Elective):        {stats['arrived_elective']}")
        print(f"  Ca mổ thực hiện (Urgent):        {stats['served_urgent']}")
        print(f"  Ca mổ thực hiện (Elective):      {stats['served_elective']}")
        print(f"  TỔNG CA MỔ:                      {stats['served_urgent'] + stats['served_elective']}")
        print(f"  Hủy (không đủ năng lực):         {stats['rejected_no_skill']}")
        print(f"  Hủy (chờ > 30'):                 {stats['rejected_wait_timeout']}")
        print(f"  Hủy (lố giờ làm):                {stats['rejected_shift_ended']}")

def print_detailed_schedule(result):
    """In lịch mổ chi tiết cho một replication"""
    stats = result["stats"]
    rep = result["replication"]
    
    print("\n" + "=" * 70)
    print(f"LỊCH MỔ CHI TIẾT - Replication #{rep}")
    print("=" * 70)
    
    schedule = sorted(stats["log"], key=lambda x: x["start"])
    for rec in schedule:
        print(
            f"{rec['patient']:>8s} ({rec['type']:8s}) | {rec['surgery_type']:45s} | "
            f"{minutes_to_hhmm(rec['start'])} - {minutes_to_hhmm(rec['end'])} | "
            f"Main: {rec['main']} | A1: {rec['assist1']} | A2: {rec['assist2']} | "
            f"Wait: {rec['wait']:>3.0f}'"
        )

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    # Chạy các replication
    all_results, unique_results, duplicate_count, patient_list = run_multiple_replications(NUM_REPLICATIONS)
    
    # In báo cáo tổng hợp
    print_summary_report(all_results, unique_results, duplicate_count, patient_list)
    
    # In lịch mổ chi tiết cho 3 kết quả unique đầu tiên (nếu có)
    print("\n" + "=" * 70)
    print("LỊCH MỔ CHI TIẾT CỦA CÁC KẾT QUẢ UNIQUE")
    print("=" * 70)
    
    for i, result in enumerate(unique_results[:3], 1):
        print_detailed_schedule(result)
    
    if len(unique_results) > 3:
        print(f"\n(Còn {len(unique_results) - 3} kết quả unique khác...)")
    
    # Tùy chọn: Lưu kết quả vào file JSON
    print("\n" + "=" * 70)
    print("LƯU KẾT QUẢ VÀO FILE...")
    
    # Chuẩn bị dữ liệu để lưu
    output_data = {
        "num_replications": len(all_results),
        "num_unique": len(unique_results),
        "num_duplicates": duplicate_count,
        "patient_list": patient_list,  # Danh sách bệnh nhân cố định
        "unique_results": [
            {
                "replication": r["replication"],
                "stats": {
                    "arrived_urgent": r["stats"]["arrived_urgent"],
                    "arrived_elective": r["stats"]["arrived_elective"],
                    "served_urgent": r["stats"]["served_urgent"],
                    "served_elective": r["stats"]["served_elective"],
                    "rejected_no_skill": r["stats"]["rejected_no_skill"],
                    "rejected_wait_timeout": r["stats"]["rejected_wait_timeout"],
                    "rejected_shift_ended": r["stats"]["rejected_shift_ended"],
                    "total_surgeries": r["stats"]["served_urgent"] + r["stats"]["served_elective"],
                },
                "schedule": sorted(r["stats"]["log"], key=lambda x: x["start"])
            }
            for r in unique_results
        ]
    }
    
    output_file = "replication_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"Đã lưu kết quả vào file: {output_file}")
    print("=" * 70)
