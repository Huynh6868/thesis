# -*- coding: utf-8 -*-
"""
Heuristic Scheduler for Large Scale (150 patients)
Reads from Excel files and generates surgery schedule
"""

import pandas as pd
import random
import os
import sys

# Import scale config
try:
    import scale_config
    SCALE = 'large'
    config = scale_config.get_scale_config(SCALE)
except ImportError:
    config = {'patient_file': '../patients_150_large.xlsx', 'capability_sheet': 'capabilities large'}

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

NAME_MAPPING = {
    "Adeno": "adenotonsillectomy",
    "Micro": "microlaryngoscopy",
    "Buccal": "buccal mucosa bioppsy",
    "Excision": "excision of the lymphadenopathy from the lumbar",
    "Septo": "septoplasty",
    "Modified": "modified radical mastoidectomy",
    "Thyroi": "thyroidectomy",
    "Rhino": "rhinoplasty",
    "Endos": "endoscopic sinus",
    "Sleep": "sleep apnea diagnosis test",
}

def load_patient_list(filepath):
    """Load patient list from Excel"""
    df = pd.read_excel(filepath)
    patients = []
    for _, row in df.iterrows():
        raw_name = row['Surgery_Name']
        canon_name = NAME_MAPPING.get(raw_name, raw_name)
        patients.append({
            'pid': row['Patient_ID'],
            'surgery_type_id': row['Surgery_Type_ID'],
            'surgery_name': canon_name
        })
    return patients

def load_room_config(cap_rank_path, scale='large'):
    """Load room configuration from Cap_Rank.xlsx 'room' sheet"""
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='room')
        # Format: first column has scale names (small/medium/large), 'Room' column has counts
        if 'Room' in df.columns:
            row = df[df.iloc[:, 0].str.strip().str.lower() == scale.lower()]
            if not row.empty:
                return int(row['Room'].iloc[0])
        # Fallback
        if 'num_rooms' in df.columns:
            return int(df['num_rooms'].iloc[0])
        return 6  # default for large
    except Exception as e:
        print(f"Warning: Could not load room config: {e}. Using default (6 rooms)")
        return 6

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

def load_capabilities(cap_rank_path, sheet_name='capabilities large'):
    """
    Load surgeon capabilities from Excel.
    Returns a dict: {surgery_type: {'main': [s_ids], 'assist1': [s_ids], 'assist2': [s_ids]}}
    """
    try:
        df = pd.read_excel(cap_rank_path, sheet_name=sheet_name)
        caps = {}
        
        for _, row in df.iterrows():
            op_num = int(row['Operation'])
            surgery_type = OPERATION_TO_TYPE.get(op_num)
            
            if surgery_type:
                # Helper to parse surgeon IDs "1;2;3" -> ["S1", "S2", "S3"]
                def parse_ids(cell_val):
                    if pd.isna(cell_val): return []
                    s_ids = []
                    # Handle "3;4;13" or simple int/float
                    val_str = str(cell_val).strip()
                    parts = val_str.replace(',', ';').split(';') # Handle both separators just in case
                    for p in parts:
                        try:
                            sid = int(float(p.strip())) # handle "3.0"
                            s_ids.append(f"S{sid}")
                        except ValueError:
                            pass
                    return s_ids

                # Find columns safely
                main_col = next((c for c in df.columns if c.strip().lower() == 'main surgeon'), None)
                a1_col = next((c for c in df.columns if c.strip().lower() == 'assistant 1'), None)
                a2_col = next((c for c in df.columns if c.strip().lower() == 'assistant 2'), None)

                if main_col and a1_col and a2_col:
                    caps[surgery_type] = {
                        'main': parse_ids(row[main_col]),
                        'assist1': parse_ids(row[a1_col]),
                        'assist2': parse_ids(row[a2_col])
                    }
        return caps
    except Exception as e:
        print(f"Error loading capabilities: {e}")
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
    print(f"\n=== LARGE SCALE HEURISTIC SCHEDULER ===")
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
    
    # Load capabilities
    capabilities = load_capabilities(cap_rank_file, capability_sheet)
    print(f"Loaded capabilities for {len(capabilities)} surgery types")
    
    # Initialize resources
    # Create a map for easy lookup by ID
    surgeons_map = {f"S{i+1}": Resource(f"S{i+1}", 'Surgeon', num_days) for i in range(num_surgeons)}
    
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
        
        # Get surgery caps
        s_caps = capabilities.get(surgery_name)
        if not s_caps:
            print(f"Warning: No capabilities found for {surgery_name}, skipping patient {patient['pid']}")
            unassigned.append(patient['pid'])
            continue

        # Get rest time from map
        rest_config = rest_time_map.get(surgery_name, {})
        rest_main = rest_config.get('main', 15)
        rest_assist = rest_config.get('assistant', 15)
        
        dur_room = duration + prep
        # Duration for surgeons includes their specific rest times
        dur_main = duration + rest_main
        dur_assist = duration + rest_assist 
        
        is_scheduled = False
        
        # Try each day and room
        for day in range(num_days):
            if is_scheduled:
                break
            
            for room_idx, room in enumerate(rooms):
                if is_scheduled:
                    break
                
                # Get eligible surgeons for each role
                qualified_main = [surgeons_map[sid] for sid in s_caps['main'] if sid in surgeons_map]
                qualified_a1 = [surgeons_map[sid] for sid in s_caps['assist1'] if sid in surgeons_map]
                qualified_a2 = [surgeons_map[sid] for sid in s_caps['assist2'] if sid in surgeons_map]
                
                # Sort by workload (greedy)
                qualified_main.sort(key=lambda s: s.workload)
                qualified_a1.sort(key=lambda s: s.workload)
                qualified_a2.sort(key=lambda s: s.workload)
                
                # Find time slot (try every 1 minute)
                for t in range(0, ADMIN_HOURS - dur_room, 1):
                    t_end_room = t + dur_room
                    t_end_main = t + dur_main
                    t_end_assist = t + dur_assist
                    
                    if not room.is_available(day, t, t_end_room):
                        continue
                        
                    # Find a main surgeon
                    chosen_main = None
                    for s in qualified_main:
                        if s.is_available(day, t, t_end_main):
                            chosen_main = s
                            break
                    if not chosen_main: continue
                    
                    # Find assist 1
                    chosen_a1 = None
                    for s in qualified_a1:
                        if s.id != chosen_main.id and s.is_available(day, t, t_end_assist):
                            chosen_a1 = s
                            break
                    if not chosen_a1: continue
                    
                    # Find assist 2
                    chosen_a2 = None
                    for s in qualified_a2:
                        if s.id != chosen_main.id and s.id != chosen_a1.id and s.is_available(day, t, t_end_assist):
                            chosen_a2 = s
                            break
                    if not chosen_a2: continue
                    
                    # Book resources
                    room.book(day, t, t_end_room)
                    chosen_main.book(day, t, t_end_main)
                    chosen_a1.book(day, t, t_end_assist)
                    chosen_a2.book(day, t, t_end_assist)
                    
                    # Record assignment
                    assignments.append({
                        'pid': patient['pid'],
                        'surgery_type': surgery_name,
                        'day': day,
                        'time_hhmm': minutes_to_hhmm(t),
                        'room': room_idx + 1,
                        'main': chosen_main.id,
                        'assist1': chosen_a1.id,
                        'assist2': chosen_a2.id
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
        output_path = os.path.join(script_dir, "large_scale_result.xlsx")
        df.to_excel(output_path, index=False)
        print(f"\n[OK] Exported schedule to: {output_path}")
        
        return df
    else:
        print("\n[!] No patients were scheduled!")
        return None

def main():
    """Main entry point"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # File paths - Use raw patient list, not heuristic output
    patient_file = os.path.join(script_dir, "patients_150_large.xlsx")
    cap_rank_file = os.path.join(script_dir, "Cap_Rank.xlsx")
    capability_sheet = config.get('capability_sheet', 'capabilities large')
    
    # Run heuristic
    solve_heuristic_excel(
        patient_file=patient_file,
        cap_rank_file=cap_rank_file,
        capability_sheet=capability_sheet,
        num_days=5,
        num_surgeons=20,  # Large scale has 20 surgeons
    )

if __name__ == "__main__":
    main()
