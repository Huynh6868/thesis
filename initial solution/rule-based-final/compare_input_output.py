"""Compare heuristic input vs GA processing"""
import pandas as pd

print("="*60)
print("INPUT vs OUTPUT COMPARISON")
print("="*60)

# Check heuristic input
heuristic_df = pd.read_excel("large_scale_result.xlsx")
print(f"\n1. HEURISTIC INPUT (large_scale_result.xlsx):")
print(f"   Total elective patients: {len(heuristic_df)}")
print(f"   PIDs: {sorted(heuristic_df['pid'].unique())[:10]}...")

# Check GA output
ga_df = pd.read_excel("combined_schedule_seed1.xlsx")
elective_ga = ga_df[ga_df['patient_type'] == 'ELECTIVE']
print(f"\n2. GA OUTPUT (combined_schedule_seed1.xlsx):")
print(f"   Total elective scheduled: {len(elective_ga)}")
print(f"   PIDs (sample): {sorted(elective_ga['patient_id'].unique())[:10]}...")

# Extract numeric PIDs from GA output
ga_pids = set()
for pid in elective_ga['patient_id'].unique():
    if pid.startswith('E'):
        ga_pids.add(int(pid[1:]))

print(f"\n3. MISSING FROM GA:")
heuristic_pids = set([int(p[1:]) if isinstance(p, str) and p.startswith('P') else int(p) for p in heuristic_df['pid']])
missing = heuristic_pids - ga_pids
print(f"   Missing count: {len(missing)}")
print(f"   Missing PIDs (sample): {sorted(list(missing))[:20]}...")

print(f"\n4. ISSUE ANALYSIS:")
if len(elective_ga) < len(heuristic_df):
    print(f"   ❌ GA scheduled FEWER patients than heuristic input!")
    print(f"   Expected: {len(heuristic_df)} elective")
    print(f"   Actual: {len(elective_ga)} elective")
    print(f"   Loss: {len(heuristic_df) - len(elective_ga)} patients")
    
    print(f"\n5. POSSIBLE CAUSES:")
    print(f"   - build_elective_plan() failing to find slots")
    print(f"   - max_reschedule_weeks too restrictive (only 1 week)")
    print(f"   - Team availability issues")
    print(f"   - Room conflicts")
