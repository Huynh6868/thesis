"""
CPLEX to CSV Converter for Surgery Scheduling
Converts CPLEX optimization results to CSV format for rule-based simulation.

Author: Auto-generated
Date: 2025-12-25
"""

import re
import csv
import os
from pathlib import Path

# ==================== CONFIGURATION ====================
SURGERY_TYPE_MAP = {
    1: "adenotonsillectomy",
    2: "microlaryngoscopy",
    3: "buccal mucosa bioppsy",
    4: "excision of the lymphadenopathy from the lumbar",
    5: "septoplasty",
    6: "modified radical mastoidectomy",
    7: "thyroidectomy",
    8: "rhinoplasty",
    9: "endoscopic sinus",
    10: "sleep apnea diagnosis test"  
}

MINUTES_PER_DAY = 1440

# ==================== HELPER FUNCTIONS ====================

def parse_matrix_from_dat(file_path, matrix_name):
    """
    Parse a 3D matrix from .dat file.
    Returns: dict with structure {(s, p, d): value}
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the matrix declaration
    pattern = rf'{matrix_name}\s*=\s*\[(.*?)\];'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        raise ValueError(f"Matrix '{matrix_name}' not found in {file_path}")
    
    matrix_str = match.group(1)
    
    # Parse the nested structure
    matrix = {}
    
    # Split by surgeon (outer dimension)
    surgeon_blocks = re.findall(r'\[(.*?)\](?:\s*,|\s*$)', matrix_str, re.DOTALL)
    
    for s_idx, surgeon_block in enumerate(surgeon_blocks):
        if not surgeon_block.strip():
            continue
            
        # Split by patient (middle dimension)
        patient_blocks = re.findall(r'\[(.*?)\]', surgeon_block)
        
        for p_idx, patient_block in enumerate(patient_blocks):
            # Split by day (inner dimension)
            days = patient_block.split(',')
            
            for d_idx, day_val in enumerate(days):
                value = int(day_val.strip()) if matrix_name != 'startsp_in' else float(day_val.strip())
                # Store with 1-indexed keys (matching CPLEX)
                matrix[(s_idx + 1, p_idx + 1, d_idx + 1)] = value
    
    return matrix


def parse_room_matrix_from_dat(file_path, matrix_name='v_in'):
    """
    Parse room assignment matrix v[p][k][d] from phase2 results.
    Returns: dict with structure {(p, k, d): value}
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = rf'{matrix_name}\s*=\s*\[(.*?)\];'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        raise ValueError(f"Matrix '{matrix_name}' not found in {file_path}")
    
    matrix_str = match.group(1)
    matrix = {}
    
    # Split by patient (outer dimension)
    patient_blocks = re.findall(r'\[(.*?)\](?:\s*,|\s*$)', matrix_str, re.DOTALL)
    
    for p_idx, patient_block in enumerate(patient_blocks):
        if not patient_block.strip():
            continue
            
        # Split by room (middle dimension)
        room_blocks = re.findall(r'\[(.*?)\]', patient_block)
        
        for k_idx, room_block in enumerate(room_blocks):
            # Split by day (inner dimension)
            days = room_block.split(',')
            
            for d_idx, day_val in enumerate(days):
                value = int(day_val.strip())
                matrix[(p_idx + 1, k_idx + 1, d_idx + 1)] = value
    
    return matrix


def parse_patient_types_from_dat(data_file_path):
    """Parse PatientType array from data file."""
    with open(data_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'PatientType\s*=\s*\[(.*?)\];'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        raise ValueError(f"PatientType not found in {data_file_path}")
    
    types_str = match.group(1)
    types = [int(x.strip()) for x in types_str.split(',') if x.strip()]
    
    # Return 1-indexed dict
    return {i + 1: t for i, t in enumerate(types)}


# ==================== MAIN CONVERSION FUNCTION ====================

def convert_cplex_to_csv(phase1_results_path, phase2_results_path, data_file_path, output_csv_path):
    """
    Convert CPLEX results to CSV format for simulation.
    """
    print(f"[1/5] Parsing Phase 1 results from {phase1_results_path}...")
    xsp = parse_matrix_from_dat(phase1_results_path, 'xsp_in')
    startsp = parse_matrix_from_dat(phase1_results_path, 'startsp_in')
    wsp = parse_matrix_from_dat(phase1_results_path, 'wsp_in')
    ysp = parse_matrix_from_dat(phase1_results_path, 'ysp_in')
    zsp = parse_matrix_from_dat(phase1_results_path, 'zsp_in')
    
    print(f"[2/5] Parsing Phase 2 results from {phase2_results_path}...")
    v = parse_room_matrix_from_dat(phase2_results_path, 'v_in')
    
    print(f"[3/5] Parsing patient types from {data_file_path}...")
    patient_types = parse_patient_types_from_dat(data_file_path)
    
    print(f"[4/5] Building surgery schedule...")
    surgeries = []
    
    # Find all scheduled surgeries
    num_patients = max(p for s, p, d in xsp.keys())
    num_surgeons = max(s for s, p, d in xsp.keys())
    num_days = max(d for s, p, d in xsp.keys())
    
    for p in range(1, num_patients + 1):
        # Find which day this patient is scheduled
        scheduled_day = None
        main_surgeon = None
        assist1_surgeon = None
        assist2_surgeon = None
        start_time = 0
        room = None
        
        for d in range(1, num_days + 1):
            # Check if patient is scheduled on this day
            for s in range(1, num_surgeons + 1):
                if wsp.get((s, p, d), 0) == 1:
                    main_surgeon = s
                    scheduled_day = d
                    start_time = startsp.get((s, p, d), 0)
                    
                if ysp.get((s, p, d), 0) == 1:
                    assist1_surgeon = s
                    
                if zsp.get((s, p, d), 0) == 1:
                    assist2_surgeon = s
            
            # Find room assignment
            if scheduled_day == d:
                for k in [1, 2]:  # Assuming 2 rooms
                    if v.get((p, k, d), 0) == 1:
                        room = k
                        break
        
        if scheduled_day is None:
            print(f"  WARNING: Patient {p} not scheduled!")
            continue
        
        # Convert to simulation time (minutes from start of week)
        scheduled_time = (scheduled_day - 1) * MINUTES_PER_DAY + start_time
        
        # Get surgery type
        surgery_type_code = patient_types[p]
        surgery_type_name = SURGERY_TYPE_MAP[surgery_type_code]
        
        # Create surgery record
        surgery = {
            'pid': f'E{p:02d}',
            'surgery_type': surgery_type_name,
            'scheduled_time': int(scheduled_time),
            'room': room if room else 1,  # Default to room 1 if not found
            'main': f'S{main_surgeon}',
            'assist1': f'S{assist1_surgeon}',
            'assist2': f'S{assist2_surgeon}'
        }
        
        surgeries.append(surgery)
    
    # Sort by scheduled time
    surgeries.sort(key=lambda x: x['scheduled_time'])
    
    print(f"[5/5] Writing CSV to {output_csv_path}...")
    with open(output_csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['pid', 'surgery_type', 'scheduled_time', 'room', 'main', 'assist1', 'assist2']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        writer.writeheader()
        writer.writerows(surgeries)
    
    print(f"\n✓ Successfully converted {len(surgeries)} surgeries to {output_csv_path}")
    return surgeries


# ==================== COMMAND LINE INTERFACE ====================

if __name__ == "__main__":
    # Set paths relative to this script
    script_dir = Path(__file__).parent
    model_dir = script_dir.parent / "model1_revise1"
    
    PHASE1_RESULTS = model_dir / "phase1_results.dat"
    PHASE2_RESULTS = model_dir / "phase2_results.dat"
    DATA_FILE = model_dir / "Data_1_EDITED.dat"
    OUTPUT_CSV = script_dir / "elective_schedule.csv"
    
    print("=" * 60)
    print("CPLEX to CSV Converter")
    print("=" * 60)
    
    # Check if input files exist
    for file_path in [PHASE1_RESULTS, PHASE2_RESULTS, DATA_FILE]:
        if not file_path.exists():
            print(f"ERROR: Input file not found: {file_path}")
            print("Please run CPLEX optimization first!")
            exit(1)
    
    try:
        surgeries = convert_cplex_to_csv(
            str(PHASE1_RESULTS),
            str(PHASE2_RESULTS),
            str(DATA_FILE),
            str(OUTPUT_CSV)
        )
        
        print("\nFirst 5 surgeries:")
        for surg in surgeries[:5]:
            print(f"  {surg}")
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
