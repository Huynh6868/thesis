# -*- coding: utf-8 -*-
"""
Run Online Simulation for Multiple Seeds - Medium Scale
Collect metrics for each seed: baseline, GA improved, % improvement, execution time
"""

import sys
import os
import time
import pandas as pd
from datetime import datetime

# Set UTF-8 encoding for output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rule_based_or_sim_v3 as sim
from online_simulation import run_online_simulation

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration
INITIAL_SCHEDULE = os.path.join(_SCRIPT_DIR, "medium_rulebased_output.xlsx")
WORK_SCHEDULE = os.path.join(_SCRIPT_DIR, "lich_lam_viec_tuan1_med.xlsx")
CAP_RANK = os.path.join(_SCRIPT_DIR, "Cap_Rank.xlsx")
NUM_SEEDS = 10
GA_GENS = 10
GA_POP = 30
SEED_GA = 42

# Create log file with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(_SCRIPT_DIR, f"multi_seed_log_{timestamp}.txt")

def log_message(message, file_handle=None):
    """Print to console and write to log file"""
    print(message)
    if file_handle:
        file_handle.write(message + "\n")
        file_handle.flush()  # Ensure data is written immediately

# Load mean_interarrival from Excel
mean_interarrival = sim.load_urgent_param_from_excel(CAP_RANK, 'Medium scale')
startup_msg = f"Loaded mean_interarrival from Excel: {mean_interarrival} minutes (Medium scale)"

# Results storage
results_data = []

# Open log file and write header
with open(log_file, 'w', encoding='utf-8') as f:
    header = f"""
{'='*80}
MULTI-SEED SIMULATION LOG - MEDIUM SCALE
Started at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
{'='*80}
Configuration:
  - Number of Seeds: {NUM_SEEDS}
  - GA Generations: {GA_GENS}
  - GA Population: {GA_POP}
  - Mean Interarrival: {mean_interarrival} minutes
  - Log File: {log_file}
{'='*80}
"""
    log_message(header, f)

# Load initial schedule
initial_df = pd.read_excel(INITIAL_SCHEDULE)

# Load rest time map
rest_time_map = sim.load_rest_time_map(CAP_RANK)

print("\n" + "="*80)
print("RUNNING ONLINE SIMULATION FOR 10 SEEDS - MEDIUM SCALE")
print("="*80)

# Re-open log file in append mode for writing seed results
with open(log_file, 'a', encoding='utf-8') as f:
    for seed in range(1, NUM_SEEDS + 1):
        separator = f"\n{'='*80}\nSEED {seed}/{NUM_SEEDS}\n{'='*80}"
        log_message(separator, f)
        
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
            
            # Write results to log immediately
            result_msg = f"""
Seed {seed} completed in {execution_time:.1f} seconds
  Urgent Count: {urgent_count}
  Baseline: {true_baseline:.1f}
  GA: {final_ga:.1f}
  Improvement: {true_baseline - final_ga:.1f} ({pct_improvement:.2f}%)
  Status: SUCCESS
"""
            log_message(result_msg, f)
            
            # Save incremental Excel file after each seed
            df_results = pd.DataFrame(results_data)
            output_path = os.path.join(_SCRIPT_DIR, "multi_seed_results_medium.xlsx")
            df_results.to_excel(output_path, index=False)
            log_message(f"Results saved to Excel: {output_path}", f)
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"""
ERROR for seed {seed} after {execution_time:.1f} seconds:
  Error Type: {type(e).__name__}
  Error Message: {str(e)}
  Status: FAILED
"""
            log_message(error_msg, f)
            import traceback
            traceback_str = traceback.format_exc()
            f.write(traceback_str + "\n")
            f.flush()
            continue

# Print summary table
print("\n" + "="*80)
print("SUMMARY OF ALL SEEDS - MEDIUM SCALE")
print("="*80)

# Append summary to log file
with open(log_file, 'a', encoding='utf-8') as f:
    summary_header = f"\n{'='*80}\nSUMMARY OF ALL SEEDS - MEDIUM SCALE\n{'='*80}"
    log_message(summary_header, f)
    
    if results_data:
        df_results = pd.DataFrame(results_data)
        
        # Print table to console and log
        table_str = "\n" + df_results.to_string(index=False)
        log_message(table_str, f)
        
        # Print statistics
        stats_header = f"\n{'='*80}\nSTATISTICS ACROSS ALL SEEDS\n{'='*80}"
        log_message(stats_header, f)
        
        avg_improvement = df_results['% Improvement'].mean()
        std_improvement = df_results['% Improvement'].std()
        min_improvement = df_results['% Improvement'].min()
        max_improvement = df_results['% Improvement'].max()
        avg_time = df_results['Execution Time (s)'].mean()
        total_time = df_results['Execution Time (s)'].sum()
        
        stats_msg = f"""Average % Improvement: {avg_improvement:.2f}%
Std Dev % Improvement: {std_improvement:.2f}%
Min % Improvement: {min_improvement:.2f}%
Max % Improvement: {max_improvement:.2f}%

Average Execution Time: {avg_time:.1f} seconds
Total Execution Time: {total_time:.1f} seconds"""
        log_message(stats_msg, f)
        
        # Save to Excel
        output_path = os.path.join(_SCRIPT_DIR, "multi_seed_results_medium.xlsx")
        df_results.to_excel(output_path, index=False)
        save_msg = f"\nResults saved to: {output_path}"
        log_message(save_msg, f)
    else:
        no_results_msg = "\nNo successful runs to summarize."
        log_message(no_results_msg, f)
    
    completion_msg = f"""
{'='*80}
MULTI-SEED SIMULATION COMPLETE - MEDIUM SCALE
Completed at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Log saved to: {log_file}
{'='*80}"""
    log_message(completion_msg, f)

print("\n" + "="*80)
print("MULTI-SEED SIMULATION COMPLETE - MEDIUM SCALE")
print("="*80)

