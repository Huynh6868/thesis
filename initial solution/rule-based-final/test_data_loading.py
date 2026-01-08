# -*- coding: utf-8 -*-
"""
Script to test data loading for heuristic scripts in medium_scale_v2 and large_scale_v2
Tests:
1. Number of rooms
2. Rest time for a main surgeon for surgery type 1
3. Distribution parameters for urgent patients
4. Capability matrix of surgeons
"""

import pandas as pd
import sys
import os

def test_medium_scale():
    """Test medium scale v2 data loading"""
    print("="*60)
    print("TESTING MEDIUM SCALE V2")
    print("="*60)
    
    base_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2"
    cap_rank_file = os.path.join(base_dir, "Cap_Rank.xlsx")
    patient_file = os.path.join(base_dir, "patients_80_medium.xlsx")
    
    # 1. Number of rooms
    try:
        df_room = pd.read_excel(cap_rank_file, sheet_name='room')
        print(f"\nRoom config sheet columns: {list(df_room.columns)}")
        print(f"Room config data:\n{df_room}")
        # The format is: scale | rooms
        # We need the "medium" row
        if 'Room' in df_room.columns:
            medium_row = df_room[df_room.iloc[:, 0] == 'medium']
            if not medium_row.empty:
                num_rooms = int(medium_row['Room'].iloc[0])
            else:
                num_rooms = 3  # default
        elif 'num_rooms' in df_room.columns:
            num_rooms = int(df_room['num_rooms'].iloc[0])
        else:
            num_rooms = int(df_room.iloc[1, 1])  # medium is row 1
        print(f"\n[OK] So luong phong (Number of ORs): {num_rooms}")
    except Exception as e:
        print(f"\n[ERROR] Loi khi doc room config: {e}")
    
    # 2. Rest time for main surgeon for surgery type 1
    try:
        df_rest = pd.read_excel(cap_rank_file, sheet_name='rest time')
        print(f"\n[OK] Rest time configuration cho tat ca loai ca mo:")
        print(df_rest.to_string(index=False))
        
        # Find surgery type 1 (adenotonsillectomy = Adeno = Operation 1)
        surgery_type_1 = df_rest[df_rest['Operation'] == 1]
        if not surgery_type_1.empty:
            # Column names have capital letters and spaces: 'Rest time main', 'Rest time assistant'
            rest_main = int(surgery_type_1['Rest time main'].iloc[0])
            rest_asst = int(surgery_type_1['Rest time assistant'].iloc[0])
            surgery_name = surgery_type_1['Name'].iloc[0]
            print(f"\n[OK] Rest time cho ca mo loai 1 ({surgery_name} - adenotonsillectomy):")
            print(f"   - Bac si mo chinh (Main surgeon): {rest_main} phut")
            print(f"   - Bac si phu (Assistant): {rest_asst} phut")
        else:
            print(f"\n[WARN] Khong tim thay rest time cho operation 1")
    except Exception as e:
        print(f"\n[ERROR] Loi khi doc rest time: {e}")
    
    # 3. Urgent patient distribution parameters  
    # Note: This may not be in Cap_Rank.xlsx, might be in code or separate config
    print(f"\n⚠ Tham số distribution tạo urgent patient:")
    print(f"   Thông tin này thường được định nghĩa trong code (rule_based_or_sim_v3.py)")
    print(f"   hoặc trong file config riêng, không nằm trong Cap_Rank.xlsx")
    
    # 4. Capability matrix
    try:
        df_cap = pd.read_excel(cap_rank_file, sheet_name='capabilities med')
        print(f"\n✓ Matrix năng lực của bác sĩ (Surgeon Capability Matrix):")
        print(f"   Shape: {df_cap.shape}")
        print(f"   Columns: {list(df_cap.columns)}")
        print(f"\n   First 10 rows:")
        print(df_cap.head(10).to_string(index=False))
    except Exception as e:
        print(f"\n✗ Lỗi khi đọc capability matrix: {e}")
    
    # 5. Patient list
    try:
        df_patients = pd.read_excel(patient_file)
        print(f"\n✓ Danh sách bệnh nhân (Patient List):")
        print(f"   Total patients: {len(df_patients)}")
        print(f"   Columns: {list(df_patients.columns)}")
        print(f"\n   First 5 patients:")
        print(df_patients.head().to_string(index=False))
    except Exception as e:
        print(f"\n✗ Lỗi khi đọc patient list: {e}")

def test_large_scale():
    """Test large scale v2 data loading"""
    print("\n\n" + "="*60)
    print("TESTING LARGE SCALE V2")
    print("="*60)
    
    base_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2"
    cap_rank_file = os.path.join(base_dir, "Cap_Rank.xlsx")
    patient_file = os.path.join(base_dir, "patients_150_large.xlsx")
    
    # 1. Number of rooms
    try:
        df_room = pd.read_excel(cap_rank_file, sheet_name='room')
        print(f"\nRoom config sheet columns: {list(df_room.columns)}")
        print(f"Room config data:\n{df_room}")
        # The format is: scale | rooms
        # We need the "large" row
        if 'Room' in df_room.columns:
            large_row = df_room[df_room.iloc[:, 0] == 'large']
            if not large_row.empty:
                num_rooms = int(large_row['Room'].iloc[0])
            else:
                num_rooms = 6  # default
        elif 'num_rooms' in df_room.columns:
            num_rooms = int(df_room['num_rooms'].iloc[0])
        else:
            num_rooms = int(df_room.iloc[2, 1])  # large is row 2
        print(f"\n[OK] So luong phong (Number of ORs): {num_rooms}")
    except Exception as e:
        print(f"\n[ERROR] Loi khi doc room config: {e}")
    
    # 2. Rest time for main surgeon for surgery type 1
    try:
        df_rest = pd.read_excel(cap_rank_file, sheet_name='rest time')
        print(f"\n✓ Rest time configuration cho tất cả loại ca mổ:")
        print(df_rest.to_string(index=False))
        
        # Find surgery type 1 (adenotonsillectomy)
        surgery_type_1 = df_rest[df_rest['surgery_type'] == 'adenotonsillectomy']
        if not surgery_type_1.empty:
            rest_main = int(surgery_type_1['rest time main'].iloc[0])
            rest_asst = int(surgery_type_1['rest time assistant'].iloc[0])
            print(f"\n✓ Rest time cho ca mổ loại 1 (adenotonsillectomy):")
            print(f"   - Bác sĩ mổ chính (Main surgeon): {rest_main} phút")
            print(f"   - Bác sĩ phụ (Assistant): {rest_asst} phút")
        else:
            print(f"\n⚠ Không tìm thấy rest time cho 'adenotonsillectomy'")
    except Exception as e:
        print(f"\n✗ Lỗi khi đọc rest time: {e}")
    
    # 3. Urgent patient distribution parameters
    print(f"\n⚠ Tham số distribution tạo urgent patient:")
    print(f"   Thông tin này thường được định nghĩa trong code (rule_based_or_sim_v3.py)")
    print(f"   hoặc trong file config riêng, không nằm trong Cap_Rank.xlsx")
    
    # 4. Capability matrix
    try:
        df_cap = pd.read_excel(cap_rank_file, sheet_name='capabilities large')
        print(f"\n✓ Matrix năng lực của bác sĩ (Surgeon Capability Matrix):")
        print(f"   Shape: {df_cap.shape}")
        print(f"   Columns: {list(df_cap.columns)}")
        print(f"\n   First 10 rows:")
        print(df_cap.head(10).to_string(index=False))
    except Exception as e:
        print(f"\n✗ Lỗi khi đọc capability matrix: {e}")
    
    # 5. Patient list
    try:
        df_patients = pd.read_excel(patient_file)
        print(f"\n✓ Danh sách bệnh nhân (Patient List):")
        print(f"   Total patients: {len(df_patients)}")
        print(f"   Columns: {list(df_patients.columns)}")
        print(f"\n   First 5 patients:")
        print(df_patients.head().to_string(index=False))
    except Exception as e:
        print(f"\n✗ Lỗi khi đọc patient list: {e}")

def check_rule_based_urgent_params():
    """Check urgent patient parameters in rule-based scripts"""
    print("\n\n" + "="*60)
    print("CHECKING URGENT PATIENT PARAMETERS")
    print("="*60)
    
    # Check medium scale
    med_base = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2"
    large_base = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2"
    
    for base_dir, scale_name in [(med_base, "MEDIUM"), (large_base, "LARGE")]:
        print(f"\n{scale_name} SCALE:")
        
        # Check Cap_Rank.xlsx urgent parameter sheet
        cap_rank_file = os.path.join(base_dir, "Cap_Rank.xlsx")
        try:
            df_urgent = pd.read_excel(cap_rank_file, sheet_name='urgent parameter')
            print(f"  [OK] Urgent parameter sheet found in Cap_Rank.xlsx")
            print(f"  Columns: {list(df_urgent.columns)}")
            print(f"\n  Urgent parameters:")
            print(df_urgent.to_string(index=False))
            
            # Get parameter for this scale
            scale_str = f"{scale_name.lower()} scale"
            row = df_urgent[df_urgent.iloc[:, 0].str.strip().str.lower() == scale_str]
            if not row.empty:
                interarrival = float(row.iloc[0]['Inter arrival time'])
                print(f"\n  [OK] Inter-arrival time for {scale_name} scale: {interarrival} minutes")
                print(f"       (Exponential distribution with mean = {interarrival} min)")
            else:
                print(f"\n  [WARN] No parameter found for '{scale_str}'")
        except Exception as e:
            print(f"  [WARN] Could not load urgent parameter sheet: {e}")
        
        # Also check rule_based code for default values
        rule_based_file = os.path.join(base_dir, "rule_based_or_sim_v3.py")
        if os.path.exists(rule_based_file):
            with open(rule_based_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            matches = re.findall(r'DEFAULT_MEAN_INTERARRIVAL_URGENT\s*=\s*([0-9.]+)', content)
            if matches:
                print(f"  [INFO] Default value in code: {matches[0]} minutes")


if __name__ == "__main__":
    # Test medium scale first as requested
    test_medium_scale()
    
    # Then test large scale
    test_large_scale()
    
    # Check urgent parameters
    check_rule_based_urgent_params()
    
    print("\n\n" + "="*60)
    print("TESTING COMPLETED")
    print("="*60)
