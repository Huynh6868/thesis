# -*- coding: utf-8 -*-
"""
Online Simulation with Urgent-Triggered Rescheduling

This module orchestrates GA optimization triggered by each urgent case arrival.
- Each urgent arrival sets frozen_time = arrival time
- Cases with scheduled_start < frozen_time are locked
- GA optimizes only the remaining modifiable elective cases
"""

from __future__ import annotations

import random
import math
from typing import Dict, List, Tuple, Optional, Union

import pandas as pd

import rule_based_or_sim_v3 as sim
from ga_optimize_priority_fullschedule import (
    run_ga_for_scenario,
    generate_urgent_list,
    ElectiveCase,
    PlannerOverrides,
)


def convert_ga_output_to_input(ga_output_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert GA output DataFrame format back to input format.
    
    GA output columns: patient_id (E1), patient_type, surgery_type, day, time_hhmm, room, main, assist1, assist2
    Input columns: pid (P1 or 1), surgery_type, day, time_hhmm, room, main, assist1, assist2
    """
    # Filter only ELECTIVE patients (skip URGENT)
    elective_rows = ga_output_df[ga_output_df["patient_type"] == "ELECTIVE"].copy()
    
    if elective_rows.empty:
        return pd.DataFrame()
    
    # Convert patient_id format: "E1" -> "P1"
    elective_rows["pid"] = elective_rows["patient_id"].str.replace("E", "P")
    
    # Select and rename columns to match input format
    result = elective_rows[["pid", "surgery_type", "day", "time_hhmm", "room", "main", "assist1", "assist2"]].copy()

    # Preserve actual_start if available (used to freeze already-started cases at next urgent trigger)
    if "actual_start" in elective_rows.columns:
        result["actual_start"] = elective_rows["actual_start"]

    return result


def run_online_simulation(
    initial_schedule_df: pd.DataFrame,
    work_schedule_path: str,
    cap_rank_path: str,
    scenario_seed: int,
    mean_interarrival: float,
    rest_time: Union[int, Dict[str, int]],
    max_reschedule_weeks: int = 1,
    penalty_next_week: int = 10000,
    ga_gens_per_trigger: int = 20,
    ga_pop_size: int = 30,
    weights: Optional[Dict[str, float]] = None,
    seed_ga: int = 42,
) -> Dict:
    """
    Run online simulation with urgent-triggered GA rescheduling.
    
    Args:
        initial_schedule_df: Initial elective schedule from rule-based heuristic
        work_schedule_path: Path to work schedule Excel
        cap_rank_path: Path to Cap_Rank.xlsx
        scenario_seed: Seed for urgent case generation
        mean_interarrival: Mean interarrival time for urgent cases (minutes)
        rest_time: Surgeon rest time (int or Dict)
        max_reschedule_weeks: Maximum weeks to reschedule
        penalty_next_week: Penalty for delayed cases
        ga_gens_per_trigger: Number of GA generations per urgent trigger
        ga_pop_size: GA population size
        weights: Objective weights (default: balanced)
        seed_ga: Seed for GA randomization
    
    Returns:
        Dict with simulation results and metrics
    """
    if weights is None:
        weights = {
            "urgent": 1.0,
            "elective_delay": 0.5,
            "overtime": 0.2,
            "next_week": 1.0,
        }
    
    # Generate urgent list ONCE for this scenario
    urgent_list = generate_urgent_list(mean_interarrival, scenario_seed)
    urgent_list_sorted = sorted(urgent_list, key=lambda x: x[0])
    print(f"\n{'='*60}")
    print(f"ONLINE SIMULATION: {len(urgent_list)} urgent cases to process")
    print(f"GA will run with {ga_gens_per_trigger} generations per trigger")
    print(f"{'='*60}\n")
    
    # Initialize current schedule
    current_schedule_df = initial_schedule_df.copy()
    
    # =========================================================================
    # SAVE ORIGINAL RULE-BASED SCHEDULE for true baseline comparison
    # This will be used at the end to compare against GA-optimized result
    # =========================================================================
    original_rulebased_schedule_df = initial_schedule_df.copy()
    
    # Track metrics across all urgent arrivals
    all_metrics: List[dict] = []
    schedule_history: List[pd.DataFrame] = [current_schedule_df.copy()]

    
    # Process each urgent arrival as a trigger point
    # Each GA run uses the CURRENT schedule (initially from heuristic, then from previous GA)
    for idx, (urgent_arrival_time, urgent_type) in enumerate(urgent_list_sorted):
        frozen_time = int(math.ceil(urgent_arrival_time - 1e-12))
        
        observed_urgent_list = urgent_list_sorted[: idx + 1]

        print(f"\n--- Urgent #{idx+1}/{len(urgent_list)} ---")
        print(f"Type: {urgent_type}, Arrival: {frozen_time} min ({frozen_time//60:.1f}h)")
        
        # Run GA with current schedule and frozen_time
        try:
            best_schedule_df, best_metrics, baseline_metrics = run_ga_for_scenario(
                elective_input_df=current_schedule_df,  # Use current (updated) schedule
                work_schedule_path=work_schedule_path,
                cap_rank_path=cap_rank_path,
                scenario_seed=scenario_seed,
                mean_interarrival=mean_interarrival,
                observed_urgent_list=observed_urgent_list,
                rest_time=rest_time,
                max_reschedule_weeks=max_reschedule_weeks,
                penalty_next_week=penalty_next_week,
                pop_size=ga_pop_size,
                gens=ga_gens_per_trigger,
                cx_rate=0.8,
                mut_rate=0.2,
                tournament_k=3,
                weights=weights,
                seed_ga=seed_ga + idx,  # Different seed per trigger
                frozen_time=frozen_time,
            )
            
            # Convert GA output back to input format for next iteration
            converted_schedule = convert_ga_output_to_input(best_schedule_df)
            if not converted_schedule.empty:
                current_schedule_df = converted_schedule
            
            # Store metrics
            all_metrics.append({
                "urgent_idx": idx,
                "urgent_type": urgent_type,
                "arrival_time": urgent_arrival_time,
                "frozen_time": frozen_time,
                "baseline_fitness": baseline_metrics.get("objective", 0),
                "best_fitness": best_metrics.get("objective", 0),
                "improvement": baseline_metrics.get("objective", 0) - best_metrics.get("objective", 0),
            })
            
            schedule_history.append(best_schedule_df.copy())
            
            print(f"GA improvement: {all_metrics[-1]['improvement']:.1f}")
            
        except Exception as e:
            print(f"Warning: GA failed for urgent #{idx+1}: {e}")
            continue
    
    # Final summary
    print(f"\n{'='*60}")
    print("ONLINE SIMULATION COMPLETE")
    print(f"{'='*60}")
    total_improvement = sum(m["improvement"] for m in all_metrics)
    
    # Calculate percentage improvement: compare FINAL baseline (with all urgents) vs FINAL best
    if all_metrics:
        # =====================================================================
        # TRUE BASELINE COMPARISON
        # Run both original rule-based schedule AND final GA-optimized schedule
        # through the same simulation with ALL urgent cases
        # =====================================================================
        print(f"\n--- Computing TRUE Baseline vs GA Comparison ---")
        print(f"Evaluating ORIGINAL rule-based schedule with ALL {len(urgent_list)} urgents...")
        
        # Evaluate ORIGINAL rule-based schedule (never touched by GA)
        try:
            _, true_baseline_metrics, _ = run_ga_for_scenario(
                elective_input_df=original_rulebased_schedule_df,
                work_schedule_path=work_schedule_path,
                cap_rank_path=cap_rank_path,
                scenario_seed=scenario_seed,
                mean_interarrival=mean_interarrival,
                observed_urgent_list=urgent_list_sorted,  # ALL urgents
                rest_time=rest_time,
                max_reschedule_weeks=max_reschedule_weeks,
                penalty_next_week=penalty_next_week,
                pop_size=1,  # Minimal - just evaluating baseline
                gens=0,      # No optimization - just evaluation
                cx_rate=0.0,
                mut_rate=0.0,
                tournament_k=2,
                weights=weights,
                seed_ga=seed_ga,
                frozen_time=None,  # No frozen cases for baseline
            )
            true_baseline_fitness = true_baseline_metrics.get("objective", 0)
        except Exception as e:
            print(f"Warning: Could not evaluate true baseline: {e}")
            true_baseline_fitness = all_metrics[0]["baseline_fitness"] if all_metrics else 0
        
        # The final GA-optimized fitness (from last trigger with all urgents)
        final_ga_fitness = all_metrics[-1]["best_fitness"]
        
        # Calculate TRUE improvement
        true_improvement = true_baseline_fitness - final_ga_fitness
        true_pct_improvement = ((true_improvement) / true_baseline_fitness * 100) if true_baseline_fitness > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"TRUE COMPARISON: Rule-Based vs GA-Optimized")
        print(f"{'='*60}")
        print(f"Original Rule-Based (with ALL {len(urgent_list)} urgents): {true_baseline_fitness:.1f}")
        print(f"Final GA-Optimized (with ALL {len(urgent_list)} urgents): {final_ga_fitness:.1f}")
        print(f"TRUE Improvement: {true_improvement:.1f} ({true_pct_improvement:.2f}%)")
        print(f"\n(Note: Previous 'per-trigger' improvements are not directly comparable)")
        
        pct_improvement = true_pct_improvement
    else:
        print(f"Total improvement across {len(all_metrics)} triggers: {total_improvement:.1f}")
        pct_improvement = 0
        true_baseline_fitness = 0
        final_ga_fitness = 0
    
    return {
        "final_schedule": current_schedule_df,
        "original_rulebased_schedule": original_rulebased_schedule_df,
        "schedule_history": schedule_history,
        "metrics_per_trigger": all_metrics,
        "total_improvement": total_improvement,
        "pct_improvement": pct_improvement,
        "urgent_count": len(urgent_list),
        "true_baseline_fitness": true_baseline_fitness,
        "final_ga_fitness": final_ga_fitness,
    }


if __name__ == "__main__":
    import argparse
    import os
    
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    
    parser = argparse.ArgumentParser(description="Online simulation with urgent-triggered GA")
    parser.add_argument("--initial_schedule", type=str, 
                       default=os.path.join(_SCRIPT_DIR, "medium_rulebased_output.xlsx"),
                       help="Path to initial elective schedule")
    parser.add_argument("--work_schedule", type=str,
                       default=os.path.join(_SCRIPT_DIR, "lich_lam_viec_tuan1_med.xlsx"))
    parser.add_argument("--cap_rank", type=str,
                       default=os.path.join(_SCRIPT_DIR, "Cap_Rank.xlsx"))
    parser.add_argument("--scenario_seed", type=int, default=1)
    parser.add_argument("--mean_interarrival", type=float, default=None)  # Load from Excel if None
    parser.add_argument("--ga_gens", type=int, default=10)
    parser.add_argument("--ga_pop", type=int, default=30)
    parser.add_argument("--rest_time", type=int, default=15)
    parser.add_argument("--seed_ga", type=int, default=42)
    
    args = parser.parse_args()
    
    # Load mean_interarrival from Excel if not specified
    if args.mean_interarrival is None:
        args.mean_interarrival = sim.load_urgent_param_from_excel(args.cap_rank, 'Medium scale')
        print(f"Loaded mean_interarrival from Excel: {args.mean_interarrival} minutes (Medium scale)")
    
    # Load initial schedule
    initial_df = pd.read_excel(args.initial_schedule)
    
    # Load rest time map if available
    rest_time_map = sim.load_rest_time_map(args.cap_rank)
    
    # Run online simulation
    results = run_online_simulation(
        initial_schedule_df=initial_df,
        work_schedule_path=args.work_schedule,
        cap_rank_path=args.cap_rank,
        scenario_seed=args.scenario_seed,
        mean_interarrival=args.mean_interarrival,
        rest_time=rest_time_map,
        ga_gens_per_trigger=args.ga_gens,
        ga_pop_size=args.ga_pop,
        seed_ga=args.seed_ga,
    )
    
    # Save final schedule
    output_path = os.path.join(_SCRIPT_DIR, f"online_schedule_seed{args.scenario_seed}.xlsx")
    results["final_schedule"].to_excel(output_path, index=False)
    print(f"\nFinal schedule saved to: {output_path}")
