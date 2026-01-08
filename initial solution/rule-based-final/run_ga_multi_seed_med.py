"""
Multi-Seed GA Test for Medium Scale
Run GA with 10 different urgent seeds and analyze results
"""
import subprocess
import sys
import os
import json
import pandas as pd

# Get current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

# Check input file (try local first, then parent)
local_file = "medium_scale_result.xlsx"
parent_file = os.path.join("..", "medium_scale_result.xlsx")

if os.path.exists(local_file):
    input_file = local_file
    print(f"Found input file: {os.path.abspath(local_file)}")
elif os.path.exists(parent_file):
    input_file = parent_file
    print(f"Found input file: {os.path.abspath(parent_file)}")
else:
    print("ERROR: medium_scale_result.xlsx not found!")
    print("  Searched in:")
    print(f"    - {os.path.abspath(local_file)}")
    print(f"    - {os.path.abspath(parent_file)}")
    print("\nPlease run heuristic_med.py first or copy the file here")
    sys.exit(1)

print("="*80)
print("MULTI-SEED GA VALIDATION - MEDIUM SCALE (50 patients)")
print("="*80)
print(f"Input: medium_scale_result.xlsx")
print(f"Seeds: 1-10")
print(f"Configuration: pop=50, gens=50, max_weeks=1")
print("="*80 + "\n")

results = []

for seed in range(1, 11):
    print(f"\n{'='*80}")
    print(f"Running Seed {seed}/10")
    print(f"{'='*80}")
    
    cmd = [
        sys.executable,
        "ga_optimize_priority_fullschedule.py",
        "--elective_sched", input_file,
        "--scenario_seed", str(seed),
        "--max_weeks", "1",
        "--pop", "50",
        "--gens", "50"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        # Read comparison file
        comparison_file = f"comparison_priority_seed{seed}.json"
        if os.path.exists(comparison_file):
            with open(comparison_file, 'r') as f:
                data = json.load(f)
                
            baseline = data['baseline']
            ga_best = data['ga_best']
            
            results.append({
                'seed': seed,
                'baseline_objective': baseline['objective'],
                'ga_objective': ga_best['objective'],
                'improvement_pct': ((baseline['objective'] - ga_best['objective']) / baseline['objective'] * 100) if baseline['objective'] > 0 else 0,
                'baseline_urgent_wait': baseline['urgent_wait_weighted'],
                'ga_urgent_wait': ga_best['urgent_wait_weighted'],
                'baseline_elective_delay': baseline['elective_delay_total'],
                'ga_elective_delay': ga_best['elective_delay_total'],
                'baseline_overtime': baseline.get('overtime_total', 0),
                'ga_overtime': ga_best.get('overtime_total', 0),
            })
            
            print(f"OK Seed {seed}: Baseline={baseline['objective']:.1f}, GA={ga_best['objective']:.1f}, Improvement={results[-1]['improvement_pct']:.2f}%")
        else:
            print(f"FAIL Seed {seed}: No comparison file found")
            
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT Seed {seed}: >10 min")
    except Exception as e:
        print(f"ERROR Seed {seed}: {e}")

# Summary
print("\n" + "="*80)
print("SUMMARY - MULTI-SEED RESULTS")
print("="*80)

if results:
    df = pd.DataFrame(results)
    
    print(f"\nSeeds completed: {len(results)}/10")
    print(f"\nObjective (lower is better):")
    print(f"  Baseline avg: {df['baseline_objective'].mean():.1f} ± {df['baseline_objective'].std():.1f}")
    print(f"  GA avg: {df['ga_objective'].mean():.1f} ± {df['ga_objective'].std():.1f}")
    print(f"  Avg improvement: {df['improvement_pct'].mean():.2f}% ± {df['improvement_pct'].std():.2f}%")
    
    print(f"\nUrgent Wait (weighted):")
    print(f"  Baseline avg: {df['baseline_urgent_wait'].mean():.1f}")
    print(f"  GA avg: {df['ga_urgent_wait'].mean():.1f}")
    print(f"  Reduction: {(df['baseline_urgent_wait'].mean() - df['ga_urgent_wait'].mean()):.1f}")
    
    print(f"\nElective Delay:")
    print(f"  Baseline avg: {df['baseline_elective_delay'].mean():.1f}")
    print(f"  GA avg: {df['ga_elective_delay'].mean():.1f}")
    print(f"  Reduction: {(df['baseline_elective_delay'].mean() - df['ga_elective_delay'].mean()):.1f}")
    
    print(f"\nBest seed: {df.loc[df['improvement_pct'].idxmax(), 'seed']} ({df['improvement_pct'].max():.2f}% improvement)")
    print(f"Worst seed: {df.loc[df['improvement_pct'].idxmin(), 'seed']} ({df['improvement_pct'].min():.2f}% improvement)")
    
    # Save summary
    summary_file = "multi_seed_summary_medium.xlsx"
    df.to_excel(summary_file, index=False)
    print(f"\nSummary saved: {summary_file}")
    
    # Conclusion
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    avg_improvement = df['improvement_pct'].mean()
    if avg_improvement > 5:
        print(f"✓ GA shows SIGNIFICANT improvement ({avg_improvement:.1f}% on average)")
        print("  GA successfully optimizes priority and team assignment")
    elif avg_improvement > 0:
        print(f"○ GA shows MODEST improvement ({avg_improvement:.1f}% on average)")
        print("  Small gains, may need parameter tuning")
    else:
        print(f"✗ GA shows NO improvement ({avg_improvement:.1f}% on average)")
        print("  Baseline is already near-optimal or GA not converging")
else:
    print("No results collected!")

print("="*80)
