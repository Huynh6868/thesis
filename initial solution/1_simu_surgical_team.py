import simpy          # Thư viện mô phỏng sự kiện rời rạc (Discrete-Event Simulation)
import random         # Dùng để sinh số ngẫu nhiên (chọn bác sĩ, thời điểm đến, v.v.)

# =========================
# THAM SỐ MÔ PHỎNG 
# =========================
#RANDOM_SEED = 42      # Seed cho random -> tái lập kết quả (reproducible)
SIM_DURATION = 8 * 60 # Tổng thời gian "sinh bệnh nhân": 8 giờ làm việc -> 480 phút
MEAN_INTER_ARRIVAL = 15  # Trung bình 1 bệnh nhân đến mỗi 15 phút (quá trình Poisson)
NUM_OR = 2            # Số phòng mổ 
WAIT_WINDOW = 30      # Time chờ tối đa nếu chưa đủ nguồn lực tại thời điểm đến (phút)
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

# Danh sách bác sĩ (SURGEONS) dưới dạng dict:
# - can_main: tập phẫu thuật có thể làm chính
# - can_assist: tập phẫu thuật có thể làm trợ lý (cả Assist1 & Assist2 dùng chung tập này)
# - shift_start, shift_end: khoảng làm việc (tính bằng phút kể từ mốc 0)
#   Ví dụ: nếu coi mốc 0 = 08:00 thì 8*60 = 480 tương ứng 16:00, 60 = 09:00, 9*60 = 17:00.
SURGEONS = {
    "S1": {
        "can_main":   {"sleep apnea diagnosis test"},
        "can_assist": {"adenotonsillectomy", "microlaryngoscopy", "excision of the lymphadenopathy from the lumbar", "septoplasty", "endoscopic sinus"},
        "shift_start": 0,         # ca 08:00–16:00 <=> [0, 480]
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
        "shift_start": 60,        # 09:00–17:00 <=> [60, 540]
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

# HÀM TIỆN ÍCH
# =========================
def minutes_to_hhmm(t):
    """Đổi số phút kể từ mốc 0 -> chuỗi HH:MM (chỉ để in đẹp)."""
    h = int(t // 60)   # số giờ
    m = int(t % 60)    # số phút lẻ
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

# =========================
# CHỌN NGẪU NHIÊN BỘ 3 BÁC SĨ RẢNH "NGAY LÚC NÀY"
# =========================
def pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources):
    """
    Mục tiêu: nếu có thể bắt đầu mổ ngay thời điểm env.now thì chọn:
      - 1 Main từ nhóm main rảnh & trong ca
      - 2 Assist từ nhóm assist rảnh & trong ca (khác Main và khác nhau)
    Trả về tuple (main, a1, a2) hoặc None nếu không có tổ hợp hợp lệ ngay lúc này.
    """
    mains, assists = eligible_sets(surgery_type, surgeons_meta)

    # Lọc main rảnh + đủ ca làm cho cả thời gian mổ nếu bắt đầu ngay
    main_free = [
        s for s in mains
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]
    # Lọc assist rảnh + đủ ca làm
    assist_free = [
        s for s in assists
        if res_free_now(surgeon_resources[s]) and in_shift(surgeons_meta[s], env.now, duration)
    ]

    if not main_free or len(assist_free) < 2:
        return None

    # Chọn ngẫu nhiên 1 main
    main = random.choice(main_free)

    # Hai trợ lý phải khác main và khác nhau
    assist_pool = [a for a in assist_free if a != main]
    if len(assist_pool) < 2:
        return None

    a1, a2 = random.sample(assist_pool, 2)  # lấy 2 người khác nhau
    return main, a1, a2

# =========================
# PROCESS CHO TỪNG BỆNH NHÂN (mỗi bệnh nhân là 1 "process" trong SimPy)
# =========================
def patient_process(env, pid, surgery_type, surgeons_meta, surgeon_resources, or_resource, stats):
    """
    env: môi trường mô phỏng
    pid: mã bệnh nhân (P1, P2, ...)
    surgery_type: loại mổ cần thực hiện
    surgeons_meta: metadata bác sĩ (SURGEONS)
    surgeon_resources: map tên bác sĩ -> simpy.Resource(capacity=1)
    or_resource: simpy.Resource cho phòng mổ (capacity=NUM_OR)
    stats: dict lưu thống kê
    """
    arrival_time = env.now                     # thời điểm bệnh nhân đến
    duration = SURGERY_TYPES[surgery_type]     # tra thời lượng mổ theo loại

    # Kiểm tra tối thiểu về skill toàn cục (bất kể rảnh hay không): cần >=1 main & >=2 assist có skill
    mains_all, assists_all = eligible_sets(surgery_type, surgeons_meta)
    if len(mains_all) < 1 or len(assists_all) < 2:
        stats["rejected_no_skill"] += 1        # loại ngay nếu không đủ năng lực hệ thống
        return

    # Bệnh nhân chờ tối đa WAIT_WINDOW phút để tìm đủ OR + 3 bác sĩ cùng rảnh tại một thời điểm
    deadline = arrival_time + WAIT_WINDOW
    assigned = False                           # cờ: đã xếp được ca hay chưa

    # Vòng lặp chờ: mỗi lần nhích 1 phút để "nghe ngóng" tài nguyên rảnh
    while env.now <= deadline:
        # Điều kiện đủ để bắt đầu NGAY LÚC NÀY:
        # 1) có ít nhất 1 OR rảnh
        # 2) pick được bộ 1 main + 2 assist đều rảnh & trong ca
        if res_free_now(or_resource):
            triad = pick_triad_now(env, surgery_type, duration, surgeons_meta, surgeon_resources)
            if triad is not None:
                main, a1, a2 = triad

                # "Giữ chỗ" đồng thời 4 resource: OR, main, assist1, assist2
                # Dùng context 'with' để tự động release khi thoát khối
                with or_resource.request() as or_req, \
                     surgeon_resources[main].request() as main_req, \
                     surgeon_resources[a1].request() as a1_req, \
                     surgeon_resources[a2].request() as a2_req:

                    # Vì đã kiểm tra rảnh, 4 request sẽ được cấp ngay (AllOf nổ tức thì)
                    yield or_req & main_req & a1_req & a2_req

                    start_time = env.now  # thời điểm bắt đầu mổ (khi cuối cùng trong 4 request được cấp)
                    # Kiểm tra lại ca làm (phòng trường hợp cạnh tranh trong cùng "tick")
                    if not (in_shift(SURGEONS[main], start_time, duration) and
                            in_shift(SURGEONS[a1], start_time, duration) and
                            in_shift(SURGEONS[a2], start_time, duration)):
                        # Nếu không đáp ứng ca làm thì KHÔNG mổ, thoát 'with' sẽ trả tài nguyên, rồi tiếp tục chờ
                        pass
                    else:
                        # Ghi log: ai mổ, loại gì, chờ bao lâu, v.v.
                        stats["served"] += 1
                        stats["log"].append({
                            "patient": pid,
                            "surgery_type": surgery_type,
                            "arrival": arrival_time,
                            "start": start_time,
                            "end": start_time + duration + MEAN_REST_TIME,
                            "wait": start_time - arrival_time,
                            "main": main,
                            "assist1": a1,
                            "assist2": a2,
                        })
                        # Thực hiện ca mổ (chiếm dụng tất cả tài nguyên trong 'duration' phút)
                        yield env.timeout(duration + MEAN_REST_TIME)
                        assigned = True  # đánh dấu đã xếp được ca
                        break            # xong bệnh nhân này -> thoát vòng chờ

        # Nếu chưa đủ điều kiện, đợi thêm 1 phút rồi thử lại (tối đa đến 'deadline')
        yield env.timeout(1)

    # Hết cửa sổ chờ mà vẫn chưa xếp được
    if not assigned:
        stats["rejected_wait_timeout"] += 1    # hủy do chờ 30' không đủ tài nguyên

# =========================
# GENERATOR: SINH BỆNH NHÂN THEO QUÁ TRÌNH POISSON
# =========================
def patient_generator(env, surgeons_meta, surgeon_resources, or_resource, stats):
    """
    Liên tục sinh bệnh nhân với khoảng cách thời gian giữa 2 người ~ Exponential(MEAN_INTER_ARRIVAL).
    Khi quá thời gian làm việc (SIM_DURATION), dừng sinh mới.
    """
    pid = 0
    while True:
        # Sinh khoảng cách đến tiếp theo theo phân phối mũ: mean = MEAN_INTER_ARRIVAL
        inter_arrival = random.expovariate(1.0 / MEAN_INTER_ARRIVAL)
        yield env.timeout(inter_arrival)  # đợi đến khi bệnh nhân tiếp theo tới

        # Nếu đã quá thời gian "sinh bệnh nhân" trong ngày thì dừng
        if env.now > SIM_DURATION:
            break

        pid += 1
        # Chọn ngẫu nhiên loại phẫu thuật cho bệnh nhân
        surgery_type = random.choice(list(SURGERY_TYPES.keys()))
        stats["arrived"] += 1  # tăng bộ đếm bệnh nhân đến

        # Mỗi bệnh nhân là một process riêng
        env.process(
            patient_process(
                env, pid, surgery_type,
                surgeons_meta, surgeon_resources, or_resource, stats
            )
        )

# =========================
# CHẠY MÔ PHỎNG
# =========================
def run_simulation():
    #random.seed(RANDOM_SEED)       # cố định hạt giống ngẫu nhiên
    env = simpy.Environment()     # tạo "thế giới" mô phỏng

    # Tạo resource cho từng bác sĩ (mỗi bác sĩ capacity=1 -> một thời điểm chỉ ở 1 ca)
    surgeon_resources = {name: simpy.Resource(env, capacity=1) for name in SURGEONS}

    # Tạo resource OR với sức chứa NUM_OR phòng mổ chạy song song
    or_resource = simpy.Resource(env, capacity=NUM_OR)

    # Biến thống kê
    stats = {
        "arrived": 0,
        "served": 0,
        "rejected_no_skill": 0,
        "rejected_wait_timeout": 0,
        "log": [],
    }

    # Khởi động process sinh bệnh nhân
    env.process(patient_generator(env, SURGEONS, surgeon_resources, or_resource, stats))

    # Chạy cho đến khi KHÔNG còn sự kiện nào: generator dừng sau SIM_DURATION,
    # nhưng các ca đang mổ vẫn tiếp tục cho đến khi kết thúc.
    env.run()

    # ======= BÁO CÁO KẾT QUẢ =======
    print("=" * 70)
    print("KẾT QUẢ MÔ PHỎNG (1 ngày)")
    print(f"Tổng số bệnh nhân đến:         {stats['arrived']}")
    print(f"Số ca mổ thực hiện được:       {stats['served']}")
    print(f"Hủy (không đủ năng lực):       {stats['rejected_no_skill']}")
    print(f"Hủy (chờ 30' vẫn không đủ):    {stats['rejected_wait_timeout']}")
    print()

    # Sắp xếp lịch theo thời điểm bắt đầu
    schedule = sorted(stats["log"], key=lambda x: x["start"])
    print("Lịch mổ (sắp theo giờ bắt đầu):")
    for rec in schedule:
        print(
            f"P{rec['patient']:02d} | {rec['surgery_type']:17s} | "
            f"{minutes_to_hhmm(rec['start'])} - {minutes_to_hhmm(rec['end'])} | "
            f"Main: {rec['main']} | A1: {rec['assist1']} | A2: {rec['assist2']} | "
            f"Wait: {rec['wait']:>3.0f}'"
        )

# "Lệnh chạy chính": khi file được chạy trực tiếp (python file.py) thì gọi run_simulation()
if __name__ == "__main__":
    run_simulation()
