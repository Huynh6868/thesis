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