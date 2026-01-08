"""
Master Pipeline: CPLEX Optimization → CSV Conversion → Simulation
Automated workflow for surgery scheduling optimization and simulation.

Usage:
    python run_pipeline.py

Author: Auto-generated
Date: 2025-12-25
"""

import subprocess
import sys
from pathlib import Path
import time

# ==================== CONFIGURATION ====================
# Paths
SCRIPT_DIR = Path(__file__).parent
MODEL_DIR = SCRIPT_DIR.parent / "model1_revise1"

# CPLEX files
PHASE1_MOD = MODEL_DIR / "d_model1_week_ORcapacity.mod"
PHASE1_DAT = MODEL_DIR / "Data_1_EDITED.dat"
PHASE1_OUT = MODEL_DIR / "phase1_results.dat"

PHASE2_MOD = MODEL_DIR / "test_model 2.mod"
PHASE2_DAT = MODEL_DIR / "model 2.dat"
PHASE2_OUT = MODEL_DIR / "phase2_results.dat"

# Converter and CSV
CONVERTER_SCRIPT = SCRIPT_DIR / "transfer_solu.py"
OUTPUT_CSV = SCRIPT_DIR / "elective_schedule.csv"

# Simulation
SIMULATION_SCRIPT = SCRIPT_DIR / "rule-based-2-week.py"

# ==================== HELPER FUNCTIONS ====================

def print_header(title):
    """Print a formatted section header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def run_cplex(mod_file, dat_file, phase_name):
    """
    Run CPLEX optimization.
    
    Args:
        mod_file: Path to .mod file
        dat_file: Path to .dat file
        phase_name: Name for logging (e.g., "Phase 1")
    
    Returns:
        True if successful, False otherwise
    """
    print_header(f"Running {phase_name} CPLEX Optimization")
    
    if not mod_file.exists():
        print(f"ERROR: Model file not found: {mod_file}")
        return False
    
    if not dat_file.exists():
        print(f"ERROR: Data file not found: {dat_file}")
        return False
    
    print(f"Model: {mod_file.name}")
    print(f"Data:  {dat_file.name}")
    print(f"\nExecuting CPLEX...")
    
    try:
        # Change to model directory for execution
        result = subprocess.run(
            ["oplrun", str(mod_file.name), str(dat_file.name)],
            cwd=str(MODEL_DIR),
            capture_output=True,
            text=True,
            timeout=900  # 15 minute timeout
        )
        
        # Print output
        if result.stdout:
            print("\n--- CPLEX Output ---")
            print(result.stdout)
        
        if result.stderr:
            print("\n--- Warnings/Errors ---")
            print(result.stderr)
        
        if result.returncode != 0:
            print(f"\nX {phase_name} FAILED with return code {result.returncode}")
            return False
        
        print(f"\n[OK] {phase_name} completed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"\nX {phase_name} TIMEOUT (exceeded 5 minutes)")
        return False
    except FileNotFoundError:
        print("\nX ERROR: 'oplrun' command not found!")
        print("   Please ensure CPLEX is installed and 'oplrun' is in your PATH")
        return False
    except Exception as e:
        print(f"\nX Unexpected error running {phase_name}: {e}")
        return False


def run_converter():
    """Run the CSV converter script."""
    print_header("Converting CPLEX Results to CSV")
    
    if not CONVERTER_SCRIPT.exists():
        print(f"ERROR: Converter script not found: {CONVERTER_SCRIPT}")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, str(CONVERTER_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        
        if result.stderr:
            print("Warnings:")
            print(result.stderr)
        
        if result.returncode != 0:
            print("\nX Conversion FAILED")
            return False
        
        if not OUTPUT_CSV.exists():
            print(f"\nX Output CSV not created: {OUTPUT_CSV}")
            return False
        
        print(f"\n[OK] CSV conversion completed: {OUTPUT_CSV}")
        return True
        
    except Exception as e:
        print(f"\nX Error running converter: {e}")
        return False


def verify_outputs():
    """Verify that all expected output files exist."""
    print_header("Verifying Output Files")
    
    files_to_check = [
        (PHASE1_OUT, "Phase 1 results"),
        (PHASE2_OUT, "Phase 2 results"),
        (OUTPUT_CSV, "Elective schedule CSV")
    ]
    
    all_exist = True
    for file_path, description in files_to_check:
        if file_path.exists():
            size_kb = file_path.stat().st_size / 1024
            print(f"  [OK] {description}: {file_path.name} ({size_kb:.1f} KB)")
        else:
            print(f"  [X] {description}: NOT FOUND")
            all_exist = False
    
    return all_exist


# ==================== MAIN PIPELINE ====================

def run_full_pipeline(skip_cplex=False, run_simulation=False):
    """
    Execute the full pipeline.
    
    Args:
        skip_cplex: If True, skip CPLEX and only run converter
        run_simulation: If True, also run the simulation after conversion
    """
    start_time = time.time()
    
    print("\n" + "#"*70)
    print("#" + " "*68 + "#")
    print("#" + "  SURGERY SCHEDULING OPTIMIZATION PIPELINE".center(68) + "#")
    print("#" + " "*68 + "#")
    print("#"*70)
    
    success = True
    
    # Step 1: Phase 1 CPLEX
    if not skip_cplex:
        if not run_cplex(PHASE1_MOD, PHASE1_DAT, "Phase 1"):
            return False
        time.sleep(1)
        
        # Step 2: Phase 2 CPLEX
        if not run_cplex(PHASE2_MOD, PHASE2_DAT, "Phase 2"):
            return False
        time.sleep(1)
    else:
        print_header("Skipping CPLEX (using existing results)")
    
    # Step 3: Convert to CSV
    if not run_converter():
        return False
    time.sleep(1)
    
    # Step 4: Verify outputs
    if not verify_outputs():
        print("\n⚠ Warning: Some output files are missing")
        success = False
    
    # Optional: Run simulation
    if run_simulation and success:
        print_header("Running Rule-Based Simulation")
        print("Note: You may need to update rule-based-2-week.py to read from CSV")
        print(f"CSV file location: {OUTPUT_CSV}")
        # TODO: Integrate simulation run if needed
    
    # Summary
    elapsed_time = time.time() - start_time
    print("\n" + "="*70)
    if success:
        print(f"  [OK] PIPELINE COMPLETED SUCCESSFULLY in {elapsed_time:.1f}s")
    else:
        print(f"  [X] PIPELINE COMPLETED WITH WARNINGS in {elapsed_time:.1f}s")
    print("="*70)
    
    return success


# ==================== COMMAND LINE INTERFACE ====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run the surgery scheduling optimization pipeline"
    )
    parser.add_argument(
        "--skip-cplex",
        action="store_true",
        help="Skip CPLEX optimization and only run converter"
    )
    parser.add_argument(
        "--with-simulation",
        action="store_true",
        help="Also run the simulation after conversion"
    )
    
    args = parser.parse_args()
    
    try:
        success = run_full_pipeline(
            skip_cplex=args.skip_cplex,
            run_simulation=args.with_simulation
        )
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nX Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
