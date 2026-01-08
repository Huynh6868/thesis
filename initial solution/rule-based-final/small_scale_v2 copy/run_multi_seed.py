# -*- coding: utf-8 -*-
"""
Run Online Simulation for Multiple Seeds
Collect metrics for each seed: baseline, GA improved, % improvement, execution time
"""

import sys
import os
import time
import pandas as pd

# Set UTF-8 encoding for output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rule_based_or_sim_v3 as sim
from online_simulation import run_online_simulation

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration
INITIAL_SCHEDULE = os.path.join(_SCRIPT_DIR, "small_rulebased_output.xlsx")
WORK_SCHEDULE = os.path.join(_SCRIPT_DIR, "lich_lam_viec_tuan1.xlsx")
CAP_RANK = os.path.join(_SCRIPT_DIR, "Cap_Rank.xlsx")
NUM_SEEDS = 10
GA_GENS = 10
GA_POP = 30
SEED_GA = 42

# Load mean_interarrival from Excel
mean_interarrival = sim.load_urgent_param_from_excel(CAP_RANK, 'Small scale')
print(f"Loaded mean_interarrival from Excel: {mean_interarrival} minutes (Small scale)")

# Load initial schedule
initial_df = pd.read_excel(INITIAL_SCHEDULE)

# Load rest time map
rest_time_map = sim.load_rest_time_map(CAP_RANK)

# Results storage
results_data = []

print("\n" + "="*80)
print("RUNNING ONLINE SIMULATION FOR 10 SEEDS")
print("="*80)

for seed in range(1, NUM_SEEDS + 1):
    print(f"\n{'='*80}")
    print(f"SEED {seed}/{NUM_SEEDS}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        results = run_online_simulation(
            initial_schedule_df=initial_df,
            work_schedule_path=WORK_SCHEDULE,
            cap_rank_path=CAP_RANK,
            scenario_seed=seed,
            mean_interarrival=mean_interarrival,
            rest_time=rest_time_map,
            ga_gens_per_trigger=GA_GENS,
            ga_pop_size=GA_POP,
            seed_ga=SEED_GA,
        )
        
        execution_time = time.time() - start_time
        
        # Extract metrics
        true_baseline = results.get("true_baseline_fitness", 0)
        final_ga = results.get("final_ga_fitness", 0)
        pct_improvement = results.get("pct_improvement", 0)
        urgent_count = results.get("urgent_count", 0)
        
        results_data.append({
            "Seed": seed,
            "Urgent Count": urgent_count,
            "Baseline Objective": true_baseline,
            "GA Improved Objective": final_ga,
            "Improvement": true_baseline - final_ga,
            "% Improvement": pct_improvement,
            "Execution Time (s)": execution_time,
        })
        
        print(f"\nSeed {seed} completed in {execution_time:.1f} seconds")
        print(f"  Baseline: {true_baseline:.1f}")
        print(f"  GA: {final_ga:.1f}")
        print(f"  Improvement: {pct_improvement:.2f}%")
        
    except Exception as e:
        print(f"\nERROR for seed {seed}: {e}")
        import traceback
        traceback.print_exc()
        continue

# Print summary table
print("\n" + "="*80)
print("SUMMARY OF ALL SEEDS")
print("="*80)

if results_data:
    df_results = pd.DataFrame(results_data)
    
    # Print table
    print("\n" + df_results.to_string(index=False))
    
    # Print statistics
    print("\n" + "="*80)
    print("STATISTICS ACROSS ALL SEEDS")
    print("="*80)
    print(f"Average % Improvement: {df_results['% Improvement'].mean():.2f}%")
    print(f"Std Dev % Improvement: {df_results['% Improvement'].std():.2f}%")
    print(f"Min % Improvement: {df_results['% Improvement'].min():.2f}%")
    print(f"Max % Improvement: {df_results['% Improvement'].max():.2f}%")
    print(f"\nAverage Execution Time: {df_results['Execution Time (s)'].mean():.1f} seconds")
    print(f"Total Execution Time: {df_results['Execution Time (s)'].sum():.1f} seconds")
    
    # Save to Excel
    output_path = os.path.join(_SCRIPT_DIR, "multi_seed_results.xlsx")
    df_results.to_excel(output_path, index=False)
    print(f"\nResults saved to: {output_path}")
else:
    print("\nNo successful runs to summarize.")

print("\n" + "="*80)
print("MULTI-SEED SIMULATION COMPLETE")
print("="*80)
