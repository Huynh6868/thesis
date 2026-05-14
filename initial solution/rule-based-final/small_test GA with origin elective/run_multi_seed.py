# -*- coding: utf-8 -*-
"""
Run Online Simulation for Multiple Seeds (with Multiprocessing)
Collect metrics for each seed: baseline, GA improved, % improvement, execution time
"""

import sys
import os
import time
import pandas as pd
from multiprocessing import Pool, cpu_count

# Set UTF-8 encoding for output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rule_based_or_sim_v3 as sim
from online_simulation import run_online_simulation

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration
INITIAL_SCHEDULE = os.path.join(_SCRIPT_DIR, "surgery_schedule.xlsx")
WORK_SCHEDULE = os.path.join(_SCRIPT_DIR, "lich_lam_viec_tuan1.xlsx")
CAP_RANK = os.path.join(_SCRIPT_DIR, "Cap_Rank.xlsx")
NUM_SEEDS = 10
GA_GENS = 10
GA_POP = 100
SEED_GA = 42


def run_single_seed(seed: int) -> dict:
    """
    Worker function to run online simulation for a single seed.
    This function will be executed in parallel by multiprocessing.Pool.
    
    Args:
        seed: Scenario seed to run
    
    Returns:
        dict with seed results or error information
    """
    try:
        # Load data inside worker (each process needs its own copy)
        mean_interarrival = sim.load_urgent_param_from_excel(CAP_RANK, 'Small scale')
        initial_df = pd.read_excel(INITIAL_SCHEDULE)
        rest_time_map = sim.load_rest_time_map(CAP_RANK)
        
        print(f"[Seed {seed}] Starting...")
        start_time = time.time()
        
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
        
        result_dict = {
            "Seed": seed,
            "Urgent Count": urgent_count,
            "Baseline Objective": true_baseline,
            "GA Improved Objective": final_ga,
            "Improvement": true_baseline - final_ga,
            "% Improvement": pct_improvement,
            "Execution Time (s)": execution_time,
            "Status": "Success",
        }
        
        print(f"[Seed {seed}] Completed in {execution_time:.1f}s | Improvement: {pct_improvement:.2f}%")
        return result_dict
        
    except Exception as e:
        print(f"[Seed {seed}] ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "Seed": seed,
            "Urgent Count": 0,
            "Baseline Objective": 0,
            "GA Improved Objective": 0,
            "Improvement": 0,
            "% Improvement": 0,
            "Execution Time (s)": 0,
            "Status": f"Failed: {str(e)[:50]}",
        }


def main():
    """Main entry point with multiprocessing."""
    print("\n" + "="*80)
    print("RUNNING ONLINE SIMULATION FOR 10 SEEDS (MULTIPROCESSING)")
    print("="*80)
    
    # Determine number of processes (leave 1 core free for system)
    num_processes = max(1, cpu_count() - 1)
    print(f"\nUsing {num_processes} parallel processes (CPU cores: {cpu_count()})")
    
    # Prepare seeds list
    seeds = list(range(1, NUM_SEEDS + 1))
    
    # Run in parallel using multiprocessing Pool
    print(f"\nStarting parallel execution for {NUM_SEEDS} seeds...")
    overall_start = time.time()
    
    with Pool(processes=num_processes) as pool:
        results_data = pool.map(run_single_seed, seeds)
    
    overall_time = time.time() - overall_start
    
    # Filter successful results
    successful_results = [r for r in results_data if r["Status"] == "Success"]
    failed_count = len(results_data) - len(successful_results)
    
    # Print summary table
    print("\n" + "="*80)
    print("SUMMARY OF ALL SEEDS")
    print("="*80)
    
    if successful_results:
        df_results = pd.DataFrame(successful_results)
        
        # Sort by seed for readability
        df_results = df_results.sort_values("Seed").reset_index(drop=True)
        
        # Print table (exclude Status column for successful runs)
        display_df = df_results.drop(columns=["Status"])
        print("\n" + display_df.to_string(index=False))
        
        # Print statistics
        print("\n" + "="*80)
        print("STATISTICS ACROSS ALL SEEDS")
        print("="*80)
        print(f"Successful runs: {len(successful_results)}/{NUM_SEEDS}")
        if failed_count > 0:
            print(f"Failed runs: {failed_count}")
        
        print(f"\nAverage % Improvement: {df_results['% Improvement'].mean():.2f}%")
        print(f"Std Dev % Improvement: {df_results['% Improvement'].std():.2f}%")
        print(f"Min % Improvement: {df_results['% Improvement'].min():.2f}%")
        print(f"Max % Improvement: {df_results['% Improvement'].max():.2f}%")
        
        print(f"\nAverage Execution Time per Seed: {df_results['Execution Time (s)'].mean():.1f} seconds")
        print(f"Total Sequential Time (sum): {df_results['Execution Time (s)'].sum():.1f} seconds")
        print(f"Actual Parallel Time (wall clock): {overall_time:.1f} seconds")
        speedup = df_results['Execution Time (s)'].sum() / overall_time if overall_time > 0 else 0
        print(f"Speedup factor: {speedup:.2f}x")
        
        # Save to Excel
        output_path = os.path.join(_SCRIPT_DIR, "multi_seed_results.xlsx")
        df_results.to_excel(output_path, index=False)
        print(f"\nResults saved to: {output_path}")
    else:
        print("\nNo successful runs to summarize.")
    
    print("\n" + "="*80)
    print("MULTI-SEED SIMULATION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    # Required guard for Windows multiprocessing
    main()
