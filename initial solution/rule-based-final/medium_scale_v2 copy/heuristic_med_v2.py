# -*- coding: utf-8 -*-
"""
Heuristic Scheduler for Medium Scale (80 patients)
Reads from Excel files and generates surgery schedule
"""

import pandas as pd
import random
import os
import sys

# Import scale config
try:
    import scale_config
    SCALE = 'medium'
    config = scale_config.get_scale_config(SCALE)
except ImportError:
    config = {'patient_file': '../patients_80_medium.xlsx', 'capability_sheet': 'capabilities med'}

# Surgery duration and prep time mappings
SURGERY_DURATION_MIN = {
    "adenotonsillectomy": 60,
    "microlaryngoscopy": 65,
    "septoplasty": 90,
    "thyroidectomy": 160,
    "buccal mucosa bioppsy": 30,
    "excision of the lymphadenopathy from the lumbar": 30,
    "modified radical mastoidectomy": 100,
    "rhinoplasty": 90,
    "endoscopic sinus": 65,
    "sleep apnea diagnosis test": 30,
}

PREP_TIME_MIN = {k: (15 if SURGERY_DURATION_MIN[k] >= 90 else 10) for k in SURGERY_DURATION_MIN.keys()}

ADMIN_SHIFT_START = 8 * 60  # 08:00
ADMIN_SHIFT_END = 16 * 60   # 16:00
ADMIN_HOURS = ADMIN_SHIFT_END - ADMIN_SHIFT_START

def minutes_to_hhmm(minutes):
    """Convert minutes to HH:MM format"""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

class Resource:
    """Resource (surgeon or room) with schedule tracking"""
    def __init__(self, id, type_res, num_days):
        self.id = id
        self.type = type_res
        self.schedule = {d: [] for d in range(num_days)}
        self.workload = 0

    def is_available(self, day, start, end):
        """Check if resource is available in time slot"""
        for s, e in self.schedule[day]:
            if not (end <= s or start >= e):
                return False
        return True

    def book(self, day, start, end):
        """Book resource for time slot"""
        self.schedule[day].append((start, end))
        self.schedule[day].sort()
        self.workload += (end - start)

def load_patient_list(filepath):
    """Load patient list from Excel"""
    df = pd.read_excel(filepath)
    patients = []
    for _, row in df.iterrows():
        patients.append({
            'pid': row['Patient_ID'],
            'surgery_type_id': row['Surgery_Type_ID'],
            'surgery_name': row['Surgery_Name']
        })
    return patients

def load_room_config(cap_rank_path, scale='medium'):
    """Load room configuration from Cap_Rank.xlsx 'room' sheet"""
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='room')
        if 'Room' in df.columns:
            row = df[df.iloc[:, 0].str.strip().str.lower() == scale.lower()]
            if not row.empty:
                return int(row['Room'].iloc[0])
        if 'num_rooms' in df.columns:
            return int(df['num_rooms'].iloc[0])
        return 3  # default for medium
    except Exception as e:
        print(f"Warning: Could not load room config: {e}. Using default (3 rooms)")
        return 3

# Map operation number to surgery type name
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

def load_rest_time_map(cap_rank_path):
    """Load rest time map from Cap_Rank.xlsx 'rest time' sheet"""
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='rest time')
        rest_map = {}
        
        # Map from Operation number to surgery type
        for _, row in df.iterrows():
            op_num = int(row['Operation'])
            surgery_type = OPERATION_TO_TYPE.get(op_num)
            if surgery_type:
                # Column names may have trailing spaces - strip them
                main_val = None
                asst_val = None
                
                for col in df.columns:
                    col_stripped = col.strip()
                    if col_stripped.lower() == 'rest time main':
                        main_val = int(row[col])
                    elif col_stripped.lower() == 'rest time assistant':
                        asst_val = int(row[col])
                
                if main_val is not None and asst_val is not None:
                    rest_map[surgery_type] = {
                        'main': main_val,
                        'assistant': asst_val
                    }
        return rest_map
    except Exception as e:
        print(f"Warning: Could not load rest time map: {e}. Using default (15 min)")
        return {}

def solve_heuristic_excel(
    patient_file,
    cap_rank_file,
    capability_sheet,
    num_days=5,
    num_surgeons=16,
):
    """
    Heuristic scheduler reading from Excel files
    
    Args:
        patient_file: Path to patient list Excel (patients_80_medium.xlsx)
        cap_rank_file: Path to Cap_Rank.xlsx
        capability_sheet: Sheet name in Cap_Rank ('capabilities med')
        num_days: Number of days to schedule (default 5 = Mon-Fri)
        num_surgeons: Number of surgeons
    """
    print(f"\n=== MEDIUM SCALE HEURISTIC SCHEDULER ===")
    print(f"Reading patients from: {patient_file}")
    print(f"Reading capabilities from: {cap_rank_file} (sheet: {capability_sheet})")
    
    # Load patients
    patients = load_patient_list(patient_file)
    print(f"Loaded {len(patients)} patients")
    
    # Load room config from Excel
    num_rooms = load_room_config(cap_rank_file)
    print(f"Number of ORs: {num_rooms}")
    
    # Load rest time map from Excel
    rest_time_map = load_rest_time_map(cap_rank_file)
    print(f"Loaded rest time config for {len(rest_time_map)} surgery types")
    
    # Load capabilities (simplified - assume all surgeons can do all surgeries for now)
    # TODO: Parse capabilities from Excel properly
    
    # Initialize resources
    surgeons = [Resource(f"S{i+1}", 'Surgeon', num_days) for i in range(num_surgeons)]
    rooms = [Resource(f"R{i+1}", 'Room', num_days) for i in range(num_rooms)]
    
    assignments = []
    unassigned = []
    
    # Sort patients by surgery duration (longest first - bin packing heuristic)
    patients_sorted = sorted(
        patients,
        key=lambda p: SURGERY_DURATION_MIN.get(p['surgery_name'], 60),
        reverse=True
    )
    
    print(f"Scheduling {len(patients_sorted)} patients...")
    
    for patient in patients_sorted:
        surgery_name = patient['surgery_name']
        duration = SURGERY_DURATION_MIN.get(surgery_name, 60)
        prep = PREP_TIME_MIN.get(surgery_name, 10)
        
        # Get rest time from map (use 'main' surgeon rest time as default)
        rest = rest_time_map.get(surgery_name, {}).get('main', 15)
        
        dur_room = duration + prep
        dur_surgeon = duration + rest
        
        is_scheduled = False
        
        # Try each day and room
        for day in range(num_days):
            if is_scheduled:
                break
            
            for room_idx, room in enumerate(rooms):
                if is_scheduled:
                    break
                
                # Select team (simplified: pick least loaded surgeons)
                # Sort surgeons by workload
                available_surgeons = sorted(surgeons, key=lambda s: s.workload)
                
                # Need 3 surgeons: main, assist1, assist2
                if len(available_surgeons) < 3:
                    continue
                
                main = available_surgeons[0]
                assist1 = available_surgeons[1]
                assist2 = available_surgeons[2]
                
                # Find time slot (try every 15 minutes)
                for t in range(0, ADMIN_HOURS - dur_room, 15):
                    t_end_room = t + dur_room
                    t_end_surg = t + dur_surgeon
                    
                    # Check availability
                    if not room.is_available(day, t, t_end_room):
                        continue
                    if not main.is_available(day, t, t_end_surg):
                        continue
                    if not assist1.is_available(day, t, t_end_surg):
                        continue
                    if not assist2.is_available(day, t, t_end_surg):
                        continue
                    
                    # Book resources
                    room.book(day, t, t_end_room)
                    main.book(day, t, t_end_surg)
                    assist1.book(day, t, t_end_surg)
                    assist2.book(day, t, t_end_surg)
                    
                    # Record assignment
                    assignments.append({
                        'pid': patient['pid'],
                        'surgery_type': surgery_name,
                        'day': day,
                        'time_hhmm': minutes_to_hhmm(t),
                        'room': room_idx + 1,
                        'main': main.id,
                        'assist1': assist1.id,
                        'assist2': assist2.id
                    })
                    
                    is_scheduled = True
                    break
        
        if not is_scheduled:
            unassigned.append(patient['pid'])
    
    # Report results
    print(f"\n=== RESULTS ===")
    print(f"Successfully scheduled: {len(assignments)}/{len(patients)} ({len(assignments)/len(patients)*100:.1f}%)")
    print(f"Unscheduled: {len(unassigned)}")
    
    if unassigned:
        print(f"Unscheduled patients: {', '.join(unassigned[:10])}" + (" ..." if len(unassigned) > 10 else ""))
    
    # Create DataFrame and save
    if assignments:
        df = pd.DataFrame(assignments)
        df.sort_values(by=['day', 'room', 'time_hhmm'], inplace=True)
        
        print("\nFirst 10 scheduled cases:")
        print(df.head(10).to_string(index=False))
        
        # Save to Excel
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "medium_scale_result.xlsx")
        df.to_excel(output_path, index=False)
        print(f"\n[OK] Exported schedule to: {output_path}")
        
        return df
    else:
        print("\n✗ No patients were scheduled!")
        return None

def main():
    """Main entry point"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # File paths - Use raw patient list, not heuristic output
    # scale_config.patient_file is for rule-based/GA (uses heuristic output)
    # heuristic needs the RAW patient list as input
    patient_file = os.path.join(script_dir, "patients_80_medium.xlsx")
    cap_rank_file = os.path.join(script_dir, "Cap_Rank.xlsx")
    capability_sheet = config.get('capability_sheet', 'capabilities med')
    
    # Run heuristic
    solve_heuristic_excel(
        patient_file=patient_file,
        cap_rank_file=cap_rank_file,
        capability_sheet=capability_sheet,
        num_days=5,
        num_surgeons=16,
    )

if __name__ == "__main__":
    main()
