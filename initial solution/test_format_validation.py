"""Simple test to validate heuristic output format"""
import pandas as pd
import sys

# Create a sample output to validate format
sample_schedule = [
    {
        'pid': 'P001',
        'surgery_type': 'adenotonsillectomy',
        'day': 0,
        'time_hhmm': '08:00',
        'room': 1,
        'main': 'S1',
        'assist1': 'S2',
        'assist2': 'S9'
    },
    {
        'pid': 'P002',
        'surgery_type': 'thyroidectomy',
        'day': 0,
        'time_hhmm': '09:30',
        'room': 2,
        'main': 'S3',
        'assist1': 'S4',
        'assist2': 'S10'
    }
]

print("Creating sample Excel with expected format...")
df = pd.DataFrame(sample_schedule)
df.to_excel("test_format.xlsx", index=False)
print("Sample Excel created: test_format.xlsx")

print("\nColumns:", df.columns.tolist())
print("\nFirst row:")
for col in df.columns:
    print(f"  {col}: {df.iloc[0][col]} (type: {type(df.iloc[0][col]).__name__})")

# Now try to load with rule-based v3 loader
print("\n" + "="*60)
print("Testing compatibility with rule-based v3...")
print("="*60)

sys.path.insert(0, r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final")
try:
    from rule_based_or_sim_v3 import load_elective_schedule_xlsx
    
    cases = load_elective_schedule_xlsx("test_format.xlsx")
    print(f"\nSUCCESS: Loaded {len(cases)} elective cases")
    if cases:
        c = cases[0]
        print(f"\nFirst case:")
        print(f"  pid: {c.pid}")
        print(f"  surgery_type: {c.surgery_type}")
        print(f"  planned_start: {c.planned_start} minutes")
        print(f"  room: {c.room}")
        print(f"  main: {c.main}, assist1: {c.assist1}, assist2: {c.assist2}")
        print("\nFORMAT VALIDATION: PASS")
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    print("\nFORMAT VALIDATION: FAIL")
