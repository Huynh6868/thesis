"""
Easy GA Runner for Medium Scale Test (50 patients)
Just press F5 to run!
"""
import subprocess
import sys
import os

# Get current directory (medium scale 2)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Check if medium_scale_result.xlsx exists in same directory
local_file = os.path.join(current_dir, "medium_scale_result.xlsx")

if os.path.exists(local_file):
    input_file = local_file
    print(f"Found input file: {local_file}")
else:
    print("ERROR: medium_scale_result.xlsx not found!")
    print(f"  Expected location: {local_file}")
    print("\nPlease run heuristic_med.py first:")
    print("  python heuristic_med.py")
    sys.exit(1)

# Change to the directory where the GA script is located
ga_script_dir = os.path.join(current_dir, "..")
os.chdir(ga_script_dir)

# Run GA with correct path and medium-scale parameters
cmd = [
    sys.executable,
    "ga_optimize_priority_fullschedule.py",
    "--elective_sched", local_file,
    "--scenario_seed", "1",
    "--max_weeks", "1",  # Medium scale: 1 week should be enough for 80 patients
    "--pop", "50",
    "--gens", "50"
]

print("\n" + "="*60)
print("Starting GA Optimization - MEDIUM SCALE 2 (80 patients)")
print("="*60)
print(f"Working directory: {os.getcwd()}")
print(f"Elective schedule: {local_file}")
print(f"Population: 50, Generations: 50")
print(f"Max reschedule weeks: 1 (sufficient for 80 patients)")
print(f"Scenario seed: 1")
print("="*60 + "\n")

print("EXPECTED RESULTS FOR MEDIUM SCALE 2 (80 patients):")
print("- Heuristic baseline: 80/80 patients (100%)")
print("- GA baseline: Should match heuristic (~80 patients)")
print("- GA optimized: Improve metrics (urgent wait, elective delay)")
print("\nIf GA baseline schedules < 70 patients:")
print("  -> GA planner may need max_weeks adjustment")
print("\nIf GA baseline schedules ~80 patients:")
print("  -> GA planner works correctly")
print("  -> Focus on metrics improvement, not patient count")
print("="*60 + "\n")

subprocess.run(cmd)
