# -*- coding: utf-8 -*-
"""
Multi-seed validation script for GA Priority Permutation.

Runs GA for seeds 1-10 and compares with rule-based baseline.
Generates CSV report for manual comparison.
"""

import subprocess
import json
import pandas as pd
from pathlib import Path

def run_ga_for_seed(seed: int, pop: int = 50, gens: int = 50):
    """Run GA for single seed."""
    print(f"\n{'='*80}")
    print(f"Running GA: Seed {seed}, Pop {pop}, Gens {gens}")
    print('='*80)
    
    cmd = [
        "python", "ga_optimize_priority_fullschedule.py",
        "--pop", str(pop),
        "--gens", str(gens),
        "--scenario_seed", str(seed)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR for seed {seed}:")
        print(result.stderr)
        return None
    
    # Load comparison JSON
    json_file = f"comparison_priority_seed{seed}.json"
    if Path(json_file).exists():
        with open(json_file, 'r') as f:
            data = json.load(f)
        return data
    return None


def extract_metrics(data: dict, method: str) -> dict:
    """Extract metrics for comparison."""
    if method == "baseline":
        m = data["baseline"]
    else:
        m = data["ga_best"]
    
    return {
        "urgent_wait_weighted": m.get("urgent_wait_weighted", 0),
        "elective_delay_total": m.get("elective_delay_total", 0),
        "overtime_total": m.get("overtime_total", 0),
        "objective": m.get("objective", 0),
    }


def main():
    """Run multi-seed validation."""
    seeds = range(1, 11)  # Seeds 1-10
    pop = 50
    gens = 50
    
    results = []
    
    for seed in seeds:
        data = run_ga_for_seed(seed, pop, gens)
        
        if data:
            baseline_metrics = extract_metrics(data, "baseline")
            ga_metrics = extract_metrics(data, "ga_best")
            
            improvement = data.get("improvement", {})
            
            baseline_obj = baseline_metrics["objective"]
            ga_obj = ga_metrics["objective"]
            improvement_pct = ((baseline_obj - ga_obj) / baseline_obj * 100) if baseline_obj > 0 else 0
            
            results.append({
                "seed": seed,
                "baseline_urgent_wait": baseline_metrics["urgent_wait_weighted"],
                "baseline_elective_delay": baseline_metrics["elective_delay_total"],
                "baseline_overtime": baseline_metrics["overtime_total"],
                "baseline_objective": baseline_obj,
                "ga_urgent_wait": ga_metrics["urgent_wait_weighted"],
                "ga_elective_delay": ga_metrics["elective_delay_total"],
                "ga_overtime": ga_metrics["overtime_total"],
                "ga_objective": ga_obj,
                "improvement_pct": improvement_pct,
                "improvement_urgent_wait": improvement.get("urgent_wait_weighted", 0),
                "improvement_elective_delay": improvement.get("elective_delay_total", 0),
                "improvement_overtime": improvement.get("overtime_total", 0),
            })
        else:
            print(f"WARNING: No data for seed {seed}")
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Add summary statistics
    summary = {
        "seed": "AVERAGE",
        "baseline_objective": df["baseline_objective"].mean(),
        "ga_objective": df["ga_objective"].mean(),
        "improvement_pct": df["improvement_pct"].mean(),
        "baseline_urgent_wait": df["baseline_urgent_wait"].mean(),
        "ga_urgent_wait": df["ga_urgent_wait"].mean(),
        "improvement_urgent_wait": df["improvement_urgent_wait"].mean(),
        "baseline_elective_delay": df["baseline_elective_delay"].mean(),
        "ga_elective_delay": df["ga_elective_delay"].mean(),
        "improvement_elective_delay": df["improvement_elective_delay"].mean(),
        "baseline_overtime": df["baseline_overtime"].mean(),
        "ga_overtime": df["ga_overtime"].mean(),
        "improvement_overtime": df["improvement_overtime"].mean(),
    }
    
    df = pd.concat([df, pd.DataFrame([summary])], ignore_index=True)
    
    # Save to Excel
    output_file = f"multi_seed_validation_pop{pop}_gens{gens}.xlsx"
    df.to_excel(output_file, index=False)
    
    print("\n" + "="*80)
    print("MULTI-SEED VALIDATION COMPLETE")
    print("="*80)
    print(f"\nResults saved to: {output_file}")
    print(f"\nAverage improvement: {summary['improvement_pct']:.2f}%")
    print(f"Min improvement: {df[df['seed'] != 'AVERAGE']['improvement_pct'].min():.2f}%")
    print(f"Max improvement: {df[df['seed'] != 'AVERAGE']['improvement_pct'].max():.2f}%")
    
    # Print summary table
    print("\n" + "="*80)
    print("SUMMARY TABLE")
    print("="*80)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
