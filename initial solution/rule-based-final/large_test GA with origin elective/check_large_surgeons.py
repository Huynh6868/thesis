import pandas as pd
import os

base_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2 copy"
cap_path = os.path.join(base_dir, "Cap_Rank.xlsx")
work_path = os.path.join(base_dir, "lich_lam_viec_tuan1_large.xlsx")

try:
    print("--- Capabilities Sheet (Large) ---")
    df_cap = pd.read_excel(cap_path, sheet_name="capabilities large")
    # Parse surgeons from Main/Assistant columns
    surgeons = set()
    for col in ["Main surgeon", "Assistant 1", "Assistant 2"]:
        if col in df_cap.columns:
            for val in df_cap[col].dropna().astype(str):
                parts = [p.strip() for p in val.split(";") if p.strip()]
                for p in parts:
                    if p.isdigit():
                        surgeons.add(f"S{int(p)}")
                    elif p.upper().startswith("S"):
                        surgeons.add(p.upper())
    
    print(f"Found {len(surgeons)} unique surgeons in Capabilities: {sorted(list(surgeons), key=lambda x: int(x[1:]))}")

    print("\n--- Work Schedule (Large) ---")
    df_work = pd.read_excel(work_path)
    work_surgeons = set()
    if "Doctor" in df_work.columns:
        for val in df_work["Doctor"].dropna().astype(str):
             work_surgeons.add(val)
    print(f"Found {len(work_surgeons)} doctors in Work Schedule: {sorted(list(work_surgeons))}")

except Exception as e:
    print(f"Error: {e}")
