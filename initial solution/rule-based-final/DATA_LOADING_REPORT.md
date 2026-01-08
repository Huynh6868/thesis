# Báo cáo kiểm tra Data Loading cho Rule-Based Simulation

## Tổng quan

Đã kiểm tra và sửa chữa các hàm load data trong `rule_based_or_sim_v3.py` ở cả hai folder:
- `medium_scale_v2`
- `large_scale_v2`

## Kết quả kiểm tra

### ✅ MEDIUM SCALE V2

#### 1. Số lượng phòng mổ (ORs)
- **Kết quả**: **3 phòng**
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'room', row 'medium')

#### 2. Rest time cho ca mổ Adenotonsillectomy (loại 1)
- **Main surgeon**: **15 phút**
- **Assistant**: **10 phút**
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'rest time', Operation = 1)

#### 3. Tham số urgent patient
- **Mean inter-arrival time**: **210 phút** (3.5 giờ)
- **Arrival rate**: **0.004762 bệnh nhân/phút**
- **Distribution**: Exponential
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'urgent parameter')

#### 4. Matrix năng lực bác sĩ (Capabilities)
- **Số loại ca mổ**: 10
- **Adenotonsillectomy capabilities**:
  - Main surgeons: S3, S4, S13
  - Assistant 1: S1, S2, S15
  - Assistant 2: S9, S10, S11, S12, S16
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'capabilities med')

#### 5. Work Schedule
- **Số tuần**: 2 tuần
- **Số bác sĩ**: 16 bác sĩ
- **Files**: lich_lam_viec_tuan1_med.xlsx, lich_lam_viec_tuan2_med.xlsx
- **Trạng thái**: ✅ ĐÚNG

---

### ✅ LARGE SCALE V2

#### 1. Số lượng phòng mổ (ORs)
- **Kết quả**: **6 phòng**
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'room', row 'large')

#### 2. Rest time cho ca mổ Adenotonsillectomy (loại 1)
- **Main surgeon**: **15 phút**
- **Assistant**: **10 phút**
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'rest time', Operation = 1)

#### 3. Tham số urgent patient
- **Mean inter-arrival time**: **112 phút** (~1.87 giờ)
- **Arrival rate**: **0.008929 bệnh nhân/phút**
- **Distribution**: Exponential
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'urgent parameter')

#### 4. Matrix năng lực bác sĩ (Capabilities)
- **Số loại ca mổ**: 10
- **Adenotonsillectomy capabilities**:
  - Main surgeons: S3, S4, S13, S18
  - Assistant 1: S1, S2, S15, S19
  - Assistant 2: S9, S10, S11, S12, S16, S20
- **Trạng thái**: ✅ ĐÚNG (đọc từ sheet 'capabilities large')

#### 5. Work Schedule
- **Số tuần**: 2 tuần
- **Số bác sĩ**: 20 bác sĩ
- **Files**: lich_lam_viec_tuan1_large.xlsx, lich_lam_viec_tuan2_large.xlsx
- **Trạng thái**: ✅ ĐÚNG

---

## Các sửa đổi đã thực hiện

### 1. Hàm `load_room_config(cap_rank_path, scale)`

**Vấn đề**: Hàm cũ tìm column 'num_rooms' không tồn tại trong Excel

**Giải pháp**: 
- Thêm parameter `scale` ('medium' hoặc 'large')
- Đọc từ bảng với format: scale name | Room count
- Tìm row phù hợp với scale và lấy giá trị từ column 'Room'

**Kết quả**: Medium = 3 phòng, Large = 6 phòng

### 2. Hàm `load_rest_time_map(cap_rank_path)`

**Vấn đề**: 
- Hàm cũ tìm column 'surgery_type' (không tồn tại)
- Column names có trailing spaces

**Giải pháp**:
- Đọc từ column 'Operation' (số 1-10)
- Map Operation number → surgery_type qua dictionary `OPERATION_TO_TYPE`
- Strip column names trước khi so sánh
- Xử lý cả 'Rest time main' và 'Rest time main ' (với/không space)

**Kết quả**: Đọc đúng rest times cho tất cả 10 loại ca mổ

### 3. Hàm `load_urgent_param_from_excel(cap_rank_path, scale)`

**Trạng thái**: ✅ Đã hoạt động đúng từ trước
- Đọc từ sheet 'urgent parameter'
- Tìm row phù hợp với scale
- Trả về 'Inter arrival time'

---

## So sánh Medium vs Large Scale

| Tham số | Medium Scale | Large Scale | Ghi chú |
|---------|--------------|-------------|---------|
| **Số phòng mổ** | 3 | 6 | Large gấp đôi |
| **Số bác sĩ** | 16 | 20 | Large +25% |
| **Urgent inter-arrival** | 210 min | 112 min | Large cao hơn ~87% |
| **Urgent arrival rate** | 0.0048 | 0.0089 | Large cao hơn ~87% |
| **Rest time (Adeno)** | Main: 15, Asst: 10 | Main: 15, Asst: 10 | Giống nhau |
| **Capability matrix** | 10 loại × 16 BS | 10 loại × 20 BS | Large có thêm BS |

---

## Kết luận

✅ **TẤT CẢ CÁC FILE RULE-BASED ĐỌC ĐÚNG DATA**

Cả hai file `rule_based_or_sim_v3.py` ở medium_scale_v2 và large_scale_v2 đã được sửa chữa và hiện đang:
1. Đọc đúng số lượng phòng mổ theo scale
2. Đọc đúng rest times theo loại ca mổ
3. Đọc đúng urgent parameters theo scale
4. Đọc đúng capability matrix theo scale
5. Đọc đúng work schedules (2 tuần)

Các files đã sẵn sàng để chạy simulation với data chính xác.

---

**Ngày kiểm tra**: 2026-01-04
**Files đã sửa**:
- `medium_scale_v2/rule_based_or_sim_v3.py`
- `large_scale_v2/rule_based_or_sim_v3.py`
