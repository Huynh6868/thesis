import pandas as pd
import numpy as np

# 1. CẤU HÌNH LOẠI PHẪU THUẬT (Dựa trên file Ranking.csv của bạn)
surgery_types = {
    1: 'Adeno',
    2: 'Micro',
    3: 'Buccal',
    4: 'Excision',
    5: 'Septo',
    6: 'Modified',
    7: 'Thyroi',
    8: 'Rhino',
    9: 'Endos',
    10: 'Sleep'
}

# 2. THIẾT LẬP TRỌNG SỐ (WEIGHTS)
# Tổng xác suất phải bằng 1.0 (100%)
# Logic: Ca dễ/phổ biến xuất hiện nhiều, ca khó (Thyroid, Modified) xuất hiện ít.
surgery_probs = [
    0.15,  # Op 1: Adeno (Rất phổ biến)
    0.12,  # Op 2: Micro
    0.12,  # Op 3: Buccal
    0.15,  # Op 4: Excision (Rất phổ biến)
    0.10,  # Op 5: Septo
    0.06,  # Op 6: Modified (Ca khó - Ít)
    0.05,  # Op 7: Thyroi (Ca khó nhất Rank 1 - Rất ít)
    0.05,  # Op 8: Rhino (Ca hiếm)
    0.10,  # Op 9: Endos
    0.10   # Op 10: Sleep
]

def generate_patient_list(num_patients, scale_name):
    # Set seed để kết quả giống nhau mỗi lần chạy (quan trọng cho báo cáo)
    np.random.seed(42 if scale_name == 'Medium' else 99)
    
    # Sinh danh sách Surgery Type ID dựa trên trọng số
    surgery_ids = np.random.choice(
        list(surgery_types.keys()), 
        size=num_patients, 
        p=surgery_probs
    )
    
    # Tạo DataFrame
    df = pd.DataFrame({
        'Patient_ID': [f'P{i+1:03d}' for i in range(num_patients)], # Ví dụ: P001, P002
        'Surgery_Type_ID': surgery_ids,
        'Surgery_Name': [surgery_types[code] for code in surgery_ids]
    })
    
    return df

# 3. THỰC HIỆN GENERATE
# Medium Scale (80 Patients)
df_medium = generate_patient_list(80, 'Medium')

# Large Scale (150 Patients)
df_large = generate_patient_list(150, 'Large')

# 4. KIỂM TRA KẾT QUẢ (Distribution Check)
print("--- PHAN BO MEDIUM DATASET (80) ---")
print(df_medium['Surgery_Name'].value_counts())
print("\n--- PHAN BO LARGE DATASET (150) ---")
print(df_large['Surgery_Name'].value_counts())

# 5. XUẤT RA FILE CSV VÀ EXCEL
print("\n--- DANG XUAT FILE ---")

# Xuất Medium Scale
df_medium.to_csv('patients_80_medium.csv', index=False)
df_medium.to_excel('patients_80_medium.xlsx', index=False, sheet_name='Patients')
print("Da tao: patients_80_medium.csv")
print("Da tao: patients_80_medium.xlsx")

# Xuất Large Scale
df_large.to_csv('patients_150_large.csv', index=False)
df_large.to_excel('patients_150_large.xlsx', index=False, sheet_name='Patients')
print("Da tao: patients_150_large.csv")
print("Da tao: patients_150_large.xlsx")

# Hiển thị mẫu dữ liệu
print("\n--- MAU DU LIEU MEDIUM ---")
print(df_medium.head())

print("\n--- MAU DU LIEU LARGE ---")
print(df_large.head())