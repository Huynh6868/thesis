import pandas as pd
import os
import sys

# Set UTF-8 encoding for output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Paths to Cap_Rank.xlsx files for each scale
scales = {
    'Small': r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\small_scale_v2 copy\Cap_Rank.xlsx",
    'Medium': r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2 copy\Cap_Rank.xlsx",
    'Large': r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2 copy\Cap_Rank.xlsx"
}

capability_sheets = {
    'Small': 'Capabilities',
    'Medium': 'capabilities med',
    'Large': 'capabilities large'
}

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

print("="*80)
print("ASSISTANT 2 CONFIGURATION BY SCALE")
print("="*80)

for scale_name, cap_rank_path in scales.items():
    if not os.path.exists(cap_rank_path):
        print(f"\n{scale_name} Scale: File not found!")
        continue
    
    sheet_name = capability_sheets[scale_name]
    
    try:
        df = pd.read_excel(cap_rank_path, sheet_name=sheet_name)
        
        print(f"\n{'='*80}")
        print(f"{scale_name.upper()} SCALE (Sheet: '{sheet_name}')")
        print(f"{'='*80}")
        
        # Collect all Assistant 2 surgeons
        all_assistant2 = set()
        
        for _, row in df.iterrows():
            op = int(row["Operation"])
            stype = OPERATION_TO_TYPE.get(op, f"Unknown_{op}")
            a2_raw = row.get("Assistant 2", "")
            
            if pd.notna(a2_raw):
                a2_str = str(a2_raw).strip()
                if a2_str:
                    # Parse the surgeons
                    surgeons = [s.strip() for s in a2_str.split(";") if s.strip()]
                    surgeons_formatted = [f"S{s}" if not s.startswith("S") else s for s in surgeons]
                    all_assistant2.update(surgeons_formatted)
                    print(f"  {stype:45s}: {', '.join(surgeons_formatted)}")
        
        print(f"\n  -> TOTAL ASSISTANT 2: {sorted(all_assistant2, key=lambda x: int(x[1:]))}")
        
    except Exception as e:
        print(f"\n{scale_name} Scale: Error reading file - {e}")

print(f"\n{'='*80}")
