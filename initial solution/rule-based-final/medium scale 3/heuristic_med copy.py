import re
import pandas as pd
import numpy as np
import random

# ==========================================
# 1. DAT FILE PARSER (ĐỌC FILE OPL .DAT)
# ==========================================
def parse_opl_dat(filename):
    """
    Hàm đọc file .dat của OPL và chuyển thành dictionary dữ liệu Python.
    Hỗ trợ đọc Sets, Arrays, và 2D/3D Matrices đơn giản.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # Helper: Loại bỏ comment
    content = re.sub(r'//.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

    data = {}

    # 1. Đọc NUM_PATIENTS (P), NUM_SURGEONS (S), NUM_DAYS (D), NUM_ROOMS (K)
    # Tìm chuỗi P = {1, 2, ...};
    def get_set_size(name):
        match = re.search(f"{name}\s*=\s*\{{([^}}]+)\}};", content)
        if match:
            # Đếm số lượng phần tử ngăn cách bởi dấu phẩy
            items = match.group(1).split(',')
            return len(items)
        return 0

    data['NUM_PATIENTS'] = get_set_size('P')
    data['NUM_SURGEONS'] = get_set_size('S')
    data['NUM_DAYS'] = get_set_size('D')
    data['NUM_ROOMS'] = get_set_size('K')

    # 2. Đọc Arrays 1D (DurationByType, PrepType, RestingTimeByType, PatientType)
    def parse_array(name):
        match = re.search(f"{name}\s*=\s*\[([^\]]+)\];", content, re.DOTALL)
        if match:
            # Xóa xuống dòng, khoảng trắng thừa
            clean_str = match.group(1).replace('\n', '').replace(' ', '')
            return [int(x) for x in clean_str.split(',') if x]
        return []

    data['DurationByType'] = parse_array('DurationByType')
    data['PrepType'] = parse_array('PrepType')
    data['RestingTimeByType'] = parse_array('RestingTimeByType')
    data['PatientType'] = parse_array('PatientType')
    
    # Lưu ý: Trong OPL index bắt đầu từ 1, nhưng giá trị PatientType thường là loại phẫu thuật.
    # Nếu PatientType trong dat file là 1..10, ta cần -1 để về index 0..9 cho Python
    # Kiểm tra xem min(PatientType) là 0 hay 1.
    if data['PatientType'] and min(data['PatientType']) == 1:
        data['PatientType'] = [x - 1 for x in data['PatientType']]

    # 3. Đọc 2D Matrix (Avail, IsAssistant2)
    # Cấu trúc: Name = [ [1,0], [0,1] ];
    def parse_2d_matrix(name, rows, cols):
        matrix = np.zeros((rows, cols), dtype=int)
        # Tìm đoạn text chứa matrix
        # Regex tìm: Name = [ ... ]; (non-greedy)
        match = re.search(f"{name}\s*=\s*\[(.*?)\];", content, re.DOTALL)
        if match:
            body = match.group(1)
            # Tách các dòng [ ... ]
            row_strs = re.findall(r'\[([^\]]+)\]', body)
            for r, row_str in enumerate(row_strs):
                if r >= rows: break
                vals = [int(x) for x in row_str.replace('\n','').split(',') if x.strip()]
                for c, val in enumerate(vals):
                    if c < cols:
                        matrix[r][c] = val
        return matrix

    data['Avail'] = parse_2d_matrix('Avail', data['NUM_SURGEONS'], data['NUM_DAYS'])
    data['IsAssistant2'] = parse_2d_matrix('IsAssistant2', data['NUM_SURGEONS'], data['NUM_DAYS'])

    # 4. Đọc 3D Matrix (IsResponsible, IsAssistant1)
    # Cấu trúc OPL: [ [ [..], [..] ], [ [..], [..] ] ]
    # Surgeon -> Type -> Day
    def parse_3d_matrix(name, dim1, dim2, dim3):
        matrix = np.zeros((dim1, dim2, dim3), dtype=int)
        # Regex tìm toàn bộ khối dữ liệu
        match = re.search(f"{name}\s*=\s*\[(.*?)\];", content, re.DOTALL)
        if match:
            body = match.group(1)
            # Tách theo Surgeon (dim1)
            # Pattern: Cụm bắt đầu bằng [ và kết thúc ], có thể lồng nhau.
            # Cách đơn giản: split theo "], [" hoặc cấu trúc tương tự.
            # Ở đây dùng logic đếm ngoặc để tách surgeon
            
            surgeons_data = []
            balance = 0
            current_chunk = []
            
            # Xóa các ký tự không cần thiết để dễ parse, chỉ giữ [ ] , 0-9
            # Nhưng cẩn thận không xóa cấu trúc.
            # Tạm thời dùng regex findall các cụm con cấp 2
            
            # Cách tiếp cận clean: Parse toàn bộ chuỗi thành list phẳng rồi reshape
            clean_nums = re.findall(r'\d+', body)
            all_nums = [int(x) for x in clean_nums]
            
            # Kiểm tra số lượng
            expected = dim1 * dim2 * dim3
            if len(all_nums) >= expected:
                # Reshape
                matrix = np.array(all_nums[:expected]).reshape((dim1, dim2, dim3))
                
        return matrix

    data['IsResponsible'] = parse_3d_matrix('IsResponsible', data['NUM_SURGEONS'], 10, data['NUM_DAYS'])
    data['IsAssistant1'] = parse_3d_matrix('IsAssistant1', data['NUM_SURGEONS'], 10, data['NUM_DAYS'])

    return data

# ==========================================
# CONSTANTS & MAPPINGS
# ==========================================
ADMIN_HOURS = 480  # Daily working hours in minutes (8 hours)

# Map operation number (1-10) to surgery type string
# This matches OPERATION_TO_TYPE in rule-based v3
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

def minutes_to_hhmm(minutes):
    """Convert minutes (int) to HH:MM string format."""
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"

# ==========================================
# 2. HEURISTIC LOGIC (ĐÃ CÓ TỪ TRƯỚC)
# ==========================================
class Resource:
    def __init__(self, id, type_res, num_days):
        self.id = id
        self.type = type_res
        self.schedule = {d: [] for d in range(num_days)}
        self.workload = 0 

    def is_available(self, day, start, end):
        for s, e in self.schedule[day]:
            if not (end <= s or start >= e):
                return False
        return True

    def book(self, day, start, end):
        self.schedule[day].append((start, end))
        self.schedule[day].sort()
        self.workload += (end - start)

def solve_heuristic_from_file(dat_file):
    print(f"Reading data from {dat_file}...")
    data = parse_opl_dat(dat_file)
    
    # Unpack data
    P = range(data['NUM_PATIENTS'])
    S = range(data['NUM_SURGEONS'])
    D = range(data['NUM_DAYS'])
    K = range(data['NUM_ROOMS'])
    
    # Init Resources
    surgeons = [Resource(s, 'Surgeon', data['NUM_DAYS']) for s in S]
    rooms = [Resource(k, 'Room', data['NUM_DAYS']) for k in K]
    
    assignments = []
    unassigned = []
    
    # --- PRIORITY SORTING ---
    # Ưu tiên ca dài xếp trước (Bin Packing logic)
    sorted_patients = sorted(
        P, 
        key=lambda p: data['DurationByType'][data['PatientType'][p]], 
        reverse=True
    )
    
    print(f"Solving for {len(P)} patients, {len(S)} surgeons, {len(K)} rooms...")
    
    for p in sorted_patients:
        p_type = data['PatientType'][p]
        duration = data['DurationByType'][p_type]
        prep = data['PrepType'][p_type]
        rest = data['RestingTimeByType'][p_type] # Có thể bị lỗi index nếu data không đủ
        
        dur_room = duration + prep
        dur_surgeon = duration + rest
        
        is_scheduled = False
        
        # Duyệt Ngày -> Phòng
        for d in D:
            if is_scheduled: break
            
            # Shuffle phòng
            room_indices = list(K)
            random.shuffle(room_indices)
            
            for k in room_indices:
                if is_scheduled: break
                
                # Tìm Team
                # Check Avail & Skill
                # Lưu ý IsResponsible là 3D [S][Type][Day]
                candidate_mains = [s for s in S if data['Avail'][s][d] == 1 and data['IsResponsible'][s][p_type][d] == 1]
                candidate_asst1 = [s for s in S if data['Avail'][s][d] == 1 and data['IsAssistant1'][s][p_type][d] == 1]
                candidate_asst2 = [s for s in S if data['Avail'][s][d] == 1 and data['IsAssistant2'][s][d] == 1]
                
                # Sort by workload
                candidate_mains.sort(key=lambda s: surgeons[s].workload)
                candidate_asst1.sort(key=lambda s: surgeons[s].workload)
                candidate_asst2.sort(key=lambda s: surgeons[s].workload)
                
                # Chọn Team & Time Slot
                for m in candidate_mains:
                    if is_scheduled: break
                    for a1 in candidate_asst1:
                        if m == a1: continue
                        if is_scheduled: break
                        for a2 in candidate_asst2:
                            if a2 == m or a2 == a1: continue
                            
                            # Tìm slot
                            # Quét từ 0 -> 480 (8 tiếng hành chính)
                            for t in range(0, ADMIN_HOURS - int(max(dur_room, dur_surgeon)), 15):
                                t_end_room = t + dur_room
                                t_end_surg = t + dur_surgeon
                                
                                if not rooms[k].is_available(d, t, t_end_room): continue
                                if not surgeons[m].is_available(d, t, t_end_surg): continue
                                if not surgeons[a1].is_available(d, t, t_end_surg): continue
                                if not surgeons[a2].is_available(d, t, t_end_surg): continue
                                
                                # Book
                                rooms[k].book(d, t, t_end_room)
                                surgeons[m].book(d, t, t_end_surg)
                                surgeons[a1].book(d, t, t_end_surg)
                                surgeons[a2].book(d, t, t_end_surg)
                                
                                # Get surgery type name (p_type is already 0-indexed after line 55-56 conversion)
                                # But OPERATION_TO_TYPE uses 1-indexed keys (1-10)
                                surgery_type_name = OPERATION_TO_TYPE.get(p_type + 1, "unknown")
                                
                                assignments.append({
                                    'pid': f"P{p+1:03d}",  # P001, P002, ...
                                    'surgery_type': surgery_type_name,  # Full surgery name
                                    'day': d,  # 0-indexed (0=Monday, ..., 4=Friday)
                                    'time_hhmm': minutes_to_hhmm(t),  # HH:MM format
                                    'room': k + 1,  # 1-indexed room number
                                    'main': f"S{m+1}",  # S1, S2, ...
                                    'assist1': f"S{a1+1}",
                                    'assist2': f"S{a2+1}"
                                })
                                is_scheduled = True
                                break
                            
                            # CRITICAL: Break out of a2 loop if scheduled
                            if is_scheduled: break
        
        # Track unassigned patients
        if not is_scheduled:
            unassigned.append(p)
    
    # --- REPORT ---
    print(f"\nKẾT QUẢ MEDIUM SCALE:")
    print(f"- Xếp thành công: {len(assignments)}/{len(P)} ({len(assignments)/len(P)*100:.1f}%)")
    print(f"- Không xếp được: {len(unassigned)}")
    
    if assignments:
        df = pd.DataFrame(assignments)
        df.sort_values(by=['day', 'room', 'time_hhmm'], inplace=True)
        print("\nDemo 10 ca đầu tiên:")
        print(df.head(10))
        df.to_excel("medium_scale_result.xlsx", index=False)
        print("\nĐã xuất file 'medium_scale_result.xlsx'")

# ==========================================
# MAIN RUN
# ==========================================
if __name__ == "__main__":
    # Đảm bảo bạn đã chạy file medium_data_test.py trước để có file .dat
    try:
        solve_heuristic_from_file("medium_scale_50p.dat")
    except FileNotFoundError:
        print("Lỗi: Không tìm thấy file 'medium_scale_50p.dat'.")
        print("Hãy chạy script 'medium_data_test.py' trong thư mục rule-based-final trước!")