# -*- coding: utf-8 -*-
"""
Complete 10-seed validation: Rule-Based → GA pipeline
Outputs: Combined schedules (urgent+elective) + comparison metrics
"""

import subprocess
import pandas as pd
import json
from pathlib import Path
import time

def run_rule_based_baseline(seed: int):
    """Step 1: Run Rule-Based to generate baseline with urgent+elective."""
    print(f"\n{'='*80}")
    print(f"Seed {seed}: Running Rule-Based baseline...")
    print('='*80)
    
    output_file = f"rule_based_baseline_seed{seed}.xlsx"
    
    cmd = [
        "python", "rule_based_or_sim_v3.py",
        "--seed", str(seed),
        "--output", output_file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR: Rule-Based failed for seed {seed}")
        print(result.stderr)
        return None
    
    print(f"✓ Rule-Based baseline created: {output_file}")
    return output_file


def extract_elective_only(rule_based_file: str, seed: int):
    """Step 2: Extract elective-only schedule from Rule-Based baseline."""
    print(f"Extracting elective-only schedule...")
    
    # Load Rule-Based combined baseline
    rb_df = pd.read_excel(rule_based_file)
    
    # Extract ELECTIVE only
    elective_df = rb_df[rb_df['patient_type'] == 'ELECTIVE'].copy()
    
    # Convert patient_id to pid
    elective_df['pid'] = elective_df['patient_id'].apply(
        lambda x: int(x[1:]) if isinstance(x, str) and (x.startswith('P') or x.startswith('E')) else int(x)
    )
    
    # Keep necessary columns for GA input
    ga_input = elective_df[[
        'pid', 'surgery_type', 'day', 'time_hhmm', 
        'room', 'main', 'assist1', 'assist2'
    ]].copy()
    
    output_file = f"rule_based_elective_only_seed{seed}.xlsx"
    ga_input.to_excel(output_file, index=False)
    
    print(f"✓ Extracted {len(ga_input)} electives: {output_file}")
    return output_file


def run_ga_optimization(elective_file: str, seed: int, pop: int = 50, gens: int = 50):
    """Step 3: Run GA optimization from Rule-Based elective baseline."""
    print(f"Running GA optimization (pop={pop}, gens={gens})...")
    
    cmd = [
        "python", "ga_optimize_priority_fullschedule.py",
        "--elective_sched", elective_file,
        "--pop", str(pop),
        "--gens", str(gens),
        "--scenario_seed", str(seed)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"WARNING: GA had issues for seed {seed}")
        print("Last 500 chars of output:")
        print(result.stdout[-500:] if result.stdout else "No stdout")
        # Don't fail - might be just file permission issue
    
    # Check if comparison file was created
    comparison_file = f"comparison_priority_seed{seed}.json"
    if Path(comparison_file).exists():
        print(f"✓ GA completed: {comparison_file}")
        return comparison_file
    else:
        print(f"⚠ GA completed but no comparison file found")
        return None


def extract_metrics(seed: int):
    """Extract metrics from both Rule-Based and GA."""
    metrics = {
        "seed": seed,
        "rule_based_file": f"rule_based_baseline_seed{seed}.xlsx",
        "ga_schedule_file": f"combined_schedule_seed{seed}.xlsx",
    }
    
    # Try to load GA comparison JSON
    comparison_file = f"comparison_priority_seed{seed}.json"
    if Path(comparison_file).exists():
        with open(comparison_file, 'r') as f:
            data = json.load(f)
        
        metrics["rule_based_objective"] = data["baseline"]["objective"]
        metrics["ga_objective"] = data["ga_best"]["objective"]
        
        # Calculate improvement_pct if not present
        if "improvement_pct" in data:
            metrics["improvement_pct"] = data["improvement_pct"]
        else:
            rb_obj = data["baseline"]["objective"]
            ga_obj = data["ga_best"]["objective"]
            metrics["improvement_pct"] = ((rb_obj - ga_obj) / rb_obj * 100) if rb_obj > 0 else 0
        
        metrics["rule_based_urgent_wait"] = data["baseline"].get("urgent_wait_weighted", 0)
        metrics["ga_urgent_wait"] = data["ga_best"].get("urgent_wait_weighted", 0)
        
        metrics["rule_based_elective_delay"] = data["baseline"].get("elective_delay_total", 0)
        metrics["ga_elective_delay"] = data["ga_best"].get("elective_delay_total", 0)
        
        metrics["rule_based_overtime"] = data["baseline"].get("overtime_total", 0)
        metrics["ga_overtime"] = data["ga_best"].get("overtime_total", 0)
    else:
        print(f"⚠ No comparison file for seed {seed}")
        metrics["rule_based_objective"] = None
        metrics["ga_objective"] = None
        metrics["improvement_pct"] = None
    
    return metrics


def main():
    """Run complete pipeline for seeds 1-10."""
    # Fix UTF-8 encoding for Windows
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except:
            pass
    
    seeds = range(1, 11)
    pop = 50
    gens = 50
    
    results = []
    
    print("="*80)
    print("FULL 10-SEED VALIDATION: Rule-Based -> GA Pipeline")
    print("="*80)
    print(f"Parameters: pop={pop}, gens={gens}")
    print(f"Output: Combined schedules (urgent+elective) for each seed")
    print("="*80)
    
    start_time = time.time()
    
    for seed in seeds:
        print(f"\n\n{'#'*80}")
        print(f"# SEED {seed}/10")
        print(f"{'#'*80}")
        
        # Step 1: Rule-Based baseline
        rb_file = run_rule_based_baseline(seed)
        if not rb_file:
            print(f"⚠ Skipping seed {seed} due to Rule-Based failure")
            continue
        
        # Step 2: Extract elective-only
        elective_file = extract_elective_only(rb_file, seed)
        
        # Step 3: GA optimization
        ga_comparison = run_ga_optimization(elective_file, seed, pop, gens)
        
        # Step 4: Extract metrics
        metrics = extract_metrics(seed)
        results.append(metrics)
        
        print(f"\n✓ Seed {seed} complete!")
        if metrics.get("improvement_pct"):
            print(f"  Improvement: {metrics['improvement_pct']:.2f}%")
    
    # Create summary DataFrame
    df = pd.DataFrame(results)
    
    # Add summary statistics
    if len(df) > 0 and "improvement_pct" in df.columns:
        summary = {
            "seed": "AVERAGE",
            "rule_based_objective": df["rule_based_objective"].mean(),
            "ga_objective": df["ga_objective"].mean(),
            "improvement_pct": df["improvement_pct"].mean(),
            "rule_based_urgent_wait": df["rule_based_urgent_wait"].mean(),
            "ga_urgent_wait": df["ga_urgent_wait"].mean(),
            "rule_based_elective_delay": df["rule_based_elective_delay"].mean(),
            "ga_elective_delay": df["ga_elective_delay"].mean(),
            "rule_based_overtime": df["rule_based_overtime"].mean(),
            "ga_overtime": df["ga_overtime"].mean(),
        }
        df = pd.concat([df, pd.DataFrame([summary])], ignore_index=True)
    
    # Save results
    output_excel = f"full_validation_rule_based_vs_ga_pop{pop}_gens{gens}.xlsx"
    df.to_excel(output_excel, index=False)
    
    elapsed = time.time() - start_time
    
    print("\n" + "="*80)
    print("VALIDATION COMPLETE!")
    print("="*80)
    print(f"Results saved to: {output_excel}")
    print(f"Total time: {elapsed/60:.1f} minutes")
    
    if len(df) > 1:  # Has data + average row
        avg_imp = df[df["seed"] == "AVERAGE"]["improvement_pct"].values[0]
        print(f"\n** Average Improvement: {avg_imp:.2f}% **")
        print(f"   (GA vs Rule-Based baseline, NOT CPLEX)")
    
    print("\n" + "="*80)
    print("OUTPUT FILES:")
    print("="*80)
    print("For each seed (1-10):")
    print("  • rule_based_baseline_seed{X}.xlsx - Rule-Based schedule (urgent+elective)")
    print("  • combined_schedule_seed{X}.xlsx - GA optimized schedule (urgent+elective)")
    print("  • comparison_priority_seed{X}.json - Detailed metrics comparison")
    
    print(f"\nSummary:")
    print(f"  • {output_excel} - Complete comparison table")
    
    # Print summary table
    print("\n" + "="*80)
    print("SUMMARY TABLE:")
    print("="*80)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
