"""Quick check GA output"""
import pandas as pd
import sys

try:
    df = pd.read_excel("combined_schedule_seed1.xlsx")
    
    print("="*60)
    print("GA OUTPUT ANALYSIS")
    print("="*60)
    
    total = len(df)
    elective = len(df[df['patient_type'] == 'ELECTIVE'])
    urgent = len(df[df['patient_type'] == 'URGENT'])
    
    print(f"\nTotal patients scheduled: {total}")
    print(f"  - Elective: {elective}")
    print(f"  - Urgent: {urgent}")
    
    print(f"\nElective patient IDs (sample):")
    elective_pids = df[df['patient_type'] == 'ELECTIVE']['patient_id'].tolist()
    print(f"  {elective_pids[:10]}...")
    
    print(f"\nDay distribution:")
    print(df.groupby('day').size())
    
    print(f"\nRoom distribution:")
    print(df.groupby('room').size())
    
except FileNotFoundError:
    print("ERROR: combined_schedule_seed1.xlsx not found!")
    print("Please run GA first.")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
