import pandas as pd
import sys
sys.path.insert(0, r'c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2 copy')
import rule_based_or_sim_v3 as sim

cap_path = r'c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2 copy\Cap_Rank.xlsx'

print("=" * 70)
print("MEDIUM SCALE SURGEON ROLES CHECK")
print("=" * 70)

try:
    cap = sim.load_cap_rank_xlsx(cap_path, capability_sheet='capabilities med')
    
    print("\nSuccessfully loaded capabilities from 'capabilities med' sheet\n")
    
    for stype in sorted(cap.main_by_type.keys()):
        mains = sorted(cap.main_by_type.get(stype, set()), key=lambda x: int(x[1:]))
        a1s = sorted(cap.a1_by_type.get(stype, set()), key=lambda x: int(x[1:]))
        a2s = sorted(cap.a2_by_type.get(stype, set()), key=lambda x: int(x[1:]))
        
        print(f"{stype}:")
        print(f"  Main surgeons: {mains}")
        print(f"  Assistant 1:   {a1s}")
        print(f"  Assistant 2:   {a2s}")
        print()
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
