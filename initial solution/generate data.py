import pandas as pd
import random

# ==========================================
# 1. CẤU HÌNH ROLE BÁC SĨ (Dựa trên giả định tối ưu)
# Bạn hãy sửa lại dòng 'role' nếu khác với ảnh
# ==========================================
surgeons_config = {
    # Nhóm Main (Mổ chính/Trưởng kíp trực)
    "S3":  {"role": "Main",   "name": "BS. S3 (Main Types 1-5)"},
    "S4":  {"role": "Main",   "name": "BS. S4 (Main Types 1-5)"},
    "S5":  {"role": "Main",   "name": "BS. S5 (Main Types 8-9)"},
    "S6":  {"role": "Main",   "name": "BS. S6 (Main Types 6-7)"},
    "S11": {"role": "Main",   "name": "BS. S11 (New Main)"}, # Giả định S11 là Main
    "S12": {"role": "Main",   "name": "BS. S12 (New Main)"}, # Giả định S12 là Main

    # Nhóm Assist (Phụ mổ/Bác sĩ trực hỗ trợ)
    "S1":  {"role": "Assist", "name": "BS. S1 (Assist/Main Type 10)"},
    "S2":  {"role": "Assist", "name": "BS. S2 (Assist/Main Type 10)"},
    "S7":  {"role": "Assist", "name": "BS. S7 (Junior)"},
    "S8":  {"role": "Assist", "name": "BS. S8 (Junior)"},
    "S9":  {"role": "Assist", "name": "BS. S9 (Junior)"},
    "S10": {"role": "Assist", "name": "BS. S10 (Junior)"}
}

surgeons_list = list(surgeons_config.keys())
days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]

# Tách nhóm để random
main_pool = [s for s, info in surgeons_config.items() if info["role"] == "Main"]
assist_pool = [s for s, info in surgeons_config.items() if info["role"] == "Assist"]

def generate_schedule():
    # Khởi tạo lịch: Mặc định tất cả đi làm hành chính (HC)
    # T7, CN để trống
    schedule = {s: ["HC" if d < 5 else "" for d in range(7)] for s in surgeons_list}
    
    # Theo dõi số ca trực để chia đều
    shift_counts = {s: 0 for s in surgeons_list}
    
    # Xáo trộn danh sách để ngẫu nhiên hóa mỗi lần chạy
    random.shuffle(main_pool)
    random.shuffle(assist_pool)
    
    # ---------------------------------------------------------
    # BƯỚC 1: XẾP LỊCH TRỰC ĐÊM TRONG TUẦN (T2 -> T6)
    # Yêu cầu: 1 Main + 1 Assist mỗi đêm
    # Hệ quả: Nghỉ bù ngày hôm sau
    # ---------------------------------------------------------
    m_idx = 0
    a_idx = 0
    
    for day_idx in range(5): # 0=T2 ... 4=T6
        # Chọn 1 Main
        current_main = main_pool[m_idx % len(main_pool)]
        m_idx += 1
        
        # Chọn 1 Assist
        current_assist = assist_pool[a_idx % len(assist_pool)]
        a_idx += 1
        
        # Ghi nhận trực đêm
        schedule[current_main][day_idx] += " + TRỰC ĐÊM"
        schedule[current_assist][day_idx] += " + TRỰC ĐÊM"
        
        shift_counts[current_main] += 1
        shift_counts[current_assist] += 1
        
        # Gán nghỉ bù ngày hôm sau (Nếu hôm sau vẫn là trong tuần hoặc T7)
        next_day = day_idx + 1
        if next_day < 7:
            schedule[current_main][next_day] = "NGHỈ BÙ (OFF)"
            schedule[current_assist][next_day] = "NGHỈ BÙ (OFF)"

    # ---------------------------------------------------------
    # BƯỚC 2: XẾP LỊCH TRỰC CUỐI TUẦN (T7, CN)
    # Yêu cầu: Trực 24h. 1 Main + 1 Assist.
    # Điều kiện: Không chọn người vừa trực hôm qua (đang nghỉ bù)
    # ---------------------------------------------------------
    for day_idx in [5, 6]: # T7, CN
        # Tìm ứng viên Main khả thi
        candidates_main = [
            s for s in main_pool 
            if "NGHỈ BÙ" not in schedule[s][day_idx]  # Không đang nghỉ bù
            and shift_counts[s] < 2                   # Chưa trực quá 2 buổi
        ]
        # Fallback: Nếu ai cũng trực rồi thì lấy người ít trực nhất
        if not candidates_main:
            candidates_main = [s for s in main_pool if "NGHỈ BÙ" not in schedule[s][day_idx]]
            
        # Chọn người có số ca trực ít nhất
        candidates_main.sort(key=lambda s: shift_counts[s])
        selected_main = candidates_main[0]
        
        # Tìm ứng viên Assist khả thi
        candidates_assist = [
            s for s in assist_pool 
            if "NGHỈ BÙ" not in schedule[s][day_idx]
            and shift_counts[s] < 2
        ]
        if not candidates_assist:
            candidates_assist = [s for s in assist_pool if "NGHỈ BÙ" not in schedule[s][day_idx]]
            
        candidates_assist.sort(key=lambda s: shift_counts[s])
        selected_assist = candidates_assist[0]
        
        # Ghi nhận trực 24h
        schedule[selected_main][day_idx] = "TRỰC 24H"
        schedule[selected_assist][day_idx] = "TRỰC 24H"
        
        shift_counts[selected_main] += 1
        shift_counts[selected_assist] += 1
        
        # Nếu trực Chủ Nhật -> Nghỉ bù Thứ 2 tuần sau (Ghi chú thôi)
        if day_idx == 6:
            # Note vào ô CN để biết
            schedule[selected_main][day_idx] += " (Nghỉ bù T2 sau)"
            schedule[selected_assist][day_idx] += " (Nghỉ bù T2 sau)"

    return schedule, shift_counts

# ==========================================
# 3. CHẠY VÀ KIỂM TRA (VALIDATION)
# ==========================================
def validate_and_export():
    best_schedule = None
    best_score = -1
    
    # Chạy thử 50 lần để tìm lịch phân bổ đều nhất
    for _ in range(50):
        sch, counts = generate_schedule()
        
        # Kiểm tra điều kiện cứng: T2-T6 phải còn đủ người làm HC
        valid = True
        min_main_hc = 100
        min_assist_hc = 100
        
        for d in range(5):
            main_working = 0
            assist_working = 0
            for s in surgeons_list:
                status = sch[s][d]
                if "HC" in status and "NGHỈ BÙ" not in status:
                    if surgeons_config[s]["role"] == "Main":
                        main_working += 1
                    else:
                        assist_working += 1
            
            if main_working < 1 or assist_working < 1:
                valid = False
                break
            
            min_main_hc = min(min_main_hc, main_working)
            min_assist_hc = min(min_assist_hc, assist_working)
        
        if valid:
            # Điểm càng cao nếu số người làm HC còn lại càng nhiều (cân bằng tốt)
            score = min_main_hc + min_assist_hc
            if score > best_score:
                best_score = score
                best_schedule = sch

    if best_schedule:
        # Xuất Excel
        df = pd.DataFrame.from_dict(best_schedule, orient='index', columns=days)
        # Thêm cột thông tin
        df.insert(0, "Vai Trò", [surgeons_config[s]["role"] for s in df.index])
        df.insert(0, "Tên Bác Sĩ", [surgeons_config[s]["name"] for s in df.index])
        
        file_name = "Lich_Truc_12_Bac_Si_Final.xlsx"
        df.to_excel(file_name)
        print(f"Đã tạo file: {file_name}")
        print("Lịch đảm bảo mỗi ngày hành chính luôn có ít nhất:")
        print(f"- {best_score//2} Bác sĩ Main trực chiến.")
        print(f"- {best_score//2} Bác sĩ Assist trực chiến.")
        print("\nXem trước 5 dòng đầu:")
        print(df.head())
    else:
        print("Không tìm được lịch thỏa mãn (Quá tải). Hãy kiểm tra lại số lượng nhân sự.")

if __name__ == "__main__":
    validate_and_export()