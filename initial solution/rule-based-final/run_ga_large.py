"""
Wrapper script to run GA with heuristic output (handles path automatically)
Just press F5 to run!
"""
import subprocess
import sys
import os

# Get current directory (rule-based-final)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Check if large_scale_result.xlsx exists in current folder
local_file = os.path.join(current_dir, "large_scale_result.xlsx")
parent_file = os.path.join(current_dir, "..", "large_scale_result.xlsx")

if os.path.exists(local_file):
    elective_path = "large_scale_result.xlsx"
    print(f"✓ Found: {local_file}")
elif os.path.exists(parent_file):
    elective_path = "../large_scale_result.xlsx"
    print(f"✓ Found: {parent_file}")
else:
    print("✗ ERROR: large_scale_result.xlsx not found!")
    print("  Please run heuristic large.py first to generate elective schedule")
    sys.exit(1)

# Change to the directory where the GA script is located
os.chdir(current_dir)

# Run GA with correct path
cmd = [
    sys.executable,
    "ga_optimize_priority_fullschedule.py",
    "--elective_sched", elective_path,
    "--scenario_seed", "1",
    "--pop", "50",
    "--gens", "50"
]

print("\n" + "="*60)
print("Starting GA Optimization...")
print("="*60)
print(f"Working directory: {os.getcwd()}")
print(f"Elective schedule: {elective_path}")
print(f"Population: 50, Generations: 50")
print(f"Scenario seed: 1")
print("="*60 + "\n")

subprocess.run(cmd)
