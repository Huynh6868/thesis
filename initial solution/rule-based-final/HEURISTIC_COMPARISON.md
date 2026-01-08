# So sánh heuristic_med.py vs heuristic_med_v2.py

## Tóm tắt

| Đặc điểm | heuristic_med.py | heuristic_med_v2.py |
|----------|------------------|---------------------|
| **Số dòng** | 304 dòng | 276 dòng |
| **Kích thước** | 13,150 bytes | 9,775 bytes |
| **Nguồn dữ liệu** | File .DAT (OPL format) | Excel files (.xlsx) |
| **Độ phức tạp** | Cao (cần parse custom format) | Thấp (dùng pandas) |

---

## Chi tiết khác biệt

### 1. **Nguồn dữ liệu đầu vào**

#### heuristic_med.py
```python
# Đọc từ file .DAT (IBM ILOG CPLEX OPL format)
def parse_opl_dat(filename):
    """Parse OPL .dat file với Sets, Arrays, 2D/3D Matrices"""
    # 108 dòng code để parse custom format
    - Đọc NUM_PATIENTS, NUM_SURGEONS, NUM_DAYS, NUM_ROOMS từ Sets
    - Parse Arrays: DurationByType, PrepType, RestingTimeByType, PatientType
    - Parse 2D Matrices: Avail, IsAssistant2
    - Parse 3D Matrices: IsResponsible, IsAssistant1
```

**Input file**: `medium_scale_80p.dat`

#### heuristic_med_v2.py
```python
# Đọc từ Excel files (dễ đọc, dễ maintain)
def load_patient_list(filepath):
    """Load từ Excel với pandas"""
    df = pd.read_excel(filepath)
    # Chỉ 8 dòng code đơn giản

def load_room_config(cap_rank_path):
    """Load từ sheet 'room'"""
    
def load_rest_time_map(cap_rank_path):
    """Load từ sheet 'rest time'"""
```

**Input files**: 
- `patients_80_medium.xlsx` (danh sách bệnh nhân)
- `Cap_Rank.xlsx` (cấu hình hệ thống)

---

### 2. **Dependencies**

#### heuristic_med.py
```python
import re          # Để parse OPL format
import pandas as pd
import numpy as np
import random
import os
```

#### heuristic_med_v2.py
```python
import pandas as pd
import random
import os
import sys
import scale_config  # Sử dụng config chung
```

**Khác biệt**: 
- `heuristic_med.py` cần `re` và `numpy` để parse .dat
- `heuristic_med_v2.py` không cần regex, dùng `scale_config` để quản lý cấu hình

---

### 3. **Cấu trúc code**

#### heuristic_med.py
```
├── parse_opl_dat()                 # 108 dòng - parser phức tạp
│   ├── get_set_size()
│   ├── parse_array()
│   ├── parse_2d_matrix()
│   └── parse_3d_matrix()
├── OPERATION_TO_TYPE (mapping)
├── Resource class
└── solve_heuristic_from_file()     # Hàm chính
```

#### heuristic_med_v2.py
```
├── load_patient_list()             # 8 dòng - đơn giản
├── load_room_config()              # 8 dòng - đơn giản
├── load_rest_time_map()            # 15 dòng - đơn giản
├── Resource class
├── solve_heuristic_excel()         # Hàm chính (có tích hợp scale_config)
└── main()                          # Entry point rõ ràng
```

**Khác biệt**: 
- v2 chia nhỏ các hàm load data, dễ maintain
- v2 có hàm `main()` riêng biệt, dễ import vào module khác
- v2 sử dụng `scale_config` để quản lý paths và parameters

---

### 4. **Capability & Constraints**

#### heuristic_med.py
```python
# Đọc từ 3D matrices trong .dat file
candidate_mains = [s for s in S if 
    data['Avail'][s][d] == 1 and 
    data['IsResponsible'][s][p_type][d] == 1]

candidate_asst1 = [s for s in S if 
    data['Avail'][s][d] == 1 and 
    data['IsAssistant1'][s][p_type][d] == 1]

candidate_asst2 = [s for s in S if 
    data['Avail'][s][d] == 1 and 
    data['IsAssistant2'][s][d] == 1]
```

**Phức tạp**: Cần parse và navigate 3D matrices

#### heuristic_med_v2.py
```python
# Simplified: Giả định tất cả surgeons có thể làm tất cả
# (TODO: Parse capabilities from Excel properly)

available_surgeons = sorted(surgeons, key=lambda s: s.workload)
main = available_surgeons[0]
assist1 = available_surgeons[1]
assist2 = available_surgeons[2]
```

**Đơn giản hơn nhưng chưa hoàn chỉnh**: 
- Chưa implement capability checking từ Excel
- Chọn surgeons dựa trên workload thấp nhất, không quan tâm đến capabilities

---

### 5. **Rest Time Handling**

#### heuristic_med.py
```python
# Đọc từ array RestingTimeByType trong .dat
rest = data['RestingTimeByType'][p_type]
```

#### heuristic_med_v2.py
```python
# Đọc từ Excel sheet 'rest time'
rest_time_map = load_rest_time_map(cap_rank_file)
rest = rest_time_map.get(surgery_name, {}).get('main', 15)
```

**Khác biệt**: v2 có fallback mặc định (15 phút) nếu không tìm thấy

---

### 6. **Output**

#### Cả 2 file đều output giống nhau:
- Excel file: `medium_scale_result.xlsx`
- Chứa: pid, surgery_type, day, time_hhmm, room, main, assist1, assist2

---

### 7. **Error Handling**

#### heuristic_med.py
```python
try:
    solve_heuristic_from_file("medium_scale_80p.dat")
except FileNotFoundError:
    print("ERROR: File 'medium_scale_80p.dat' not found.")
    print("Please run 'data med 80.py' first to generate data!")
```

#### heuristic_med_v2.py
```python
try:
    import scale_config
    config = scale_config.get_scale_config(SCALE)
except ImportError:
    config = {'patient_file': '../patients_80_medium.xlsx', 
              'capability_sheet': 'capabilities med'}
```

**Khác biệt**: 
- v1 chỉ handle FileNotFoundError
- v2 có fallback config nếu không import được `scale_config`

---

## Ưu/Nhược điểm

### heuristic_med.py

**Ưu điểm:**
- ✅ Tích hợp hoàn chỉnh với OPL/CPLEX workflow
- ✅ Implement đầy đủ capabilities và constraints
- ✅ Kiểm tra chi tiết availability và skills

**Nhược điểm:**
- ❌ Code phức tạp (108 dòng chỉ để parse data)
- ❌ Khó maintain (custom parser)
- ❌ Phụ thuộc vào .dat file format cụ thể
- ❌ Cần chạy script tạo .dat trước

### heuristic_med_v2.py

**Ưu điểm:**
- ✅ Code đơn giản, dễ đọc
- ✅ Sử dụng Excel - dễ edit và maintain data
- ✅ Tích hợp với `scale_config` - quản lý tốt hơn
- ✅ Có hàm `main()` riêng - dễ import và test

**Nhược điểm:**
- ❌ **Chưa implement capability checking** (TODO)
- ❌ Simplified logic - chọn surgeon theo workload (chưa đúng)
- ❌ Chưa check availability và skills

---

## Khuyến nghị

### Nên dùng file nào?

**Hiện tại**: Nếu cần chạy ngay → **heuristic_med.py** (đầy đủ tính năng)

**Tương lai**: Sau khi fix → **heuristic_med_v2.py** (maintainable hơn)

### TODO cho heuristic_med_v2.py

1. ✅ Implement capability loading từ Excel ✅ (Đã có trong rule-based)
2. ✅ Parse surgeon availability from work schedules
3. ✅ Add proper skill checking logic
4. Sync logic với rule-based để consistency

### Liên kết với rule-based

Chú ý: `rule_based_or_sim_v3.py` đã có các hàm:
- `load_cap_rank_xlsx()` - Load capabilities đầy đủ
- `WorkSchedule` class - Quản lý availability
- `choose_urgent_team()` - Logic chọn team đúng

→ **Nên copy logic từ rule-based sang heuristic_med_v2.py**

---

## Kết luận

**heuristic_med_v2.py** là phiên bản hiện đại hóa của **heuristic_med.py**:
- Thay .DAT bằng Excel
- Code đơn giản hơn
- Dễ maintain hơn
- **Nhưng chưa hoàn thiện** (capabilities chưa implement)

Sau khi hoàn thiện, v2 sẽ tốt hơn v1 về mặt maintainability.
