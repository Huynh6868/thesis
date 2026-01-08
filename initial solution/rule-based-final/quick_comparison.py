# Quick comparison: Rule-Based vs GA (current, vs CPLEX baseline)
import pandas as pd
import json

print("="*80)
print("QUICK TEST: Rule-Based vs GA Comparison")
print("="*80)

# 1. Load Rule-Based baseline schedule
rb_df = pd.read_excel("rule_based_baseline_seed1.xlsx")
print(f"\nRule-Based Baseline Schedule (seed=1):")
print(f"  Total cases: {len(rb_df)}")
print(f"  Urgent: {len(rb_df[rb_df['patient_type'] == 'URGENT'])}")
print(f"  Elective: {len(rb_df[rb_df['patient_type'] == 'ELECTIVE'])}")

# 2. Load previous GA comparison (vs CPLEX)
with open("comparison_priority_seed1.json", 'r') as f:
    ga_data = json.load(f)

print(f"\n{'='*80}")
print("Previous GA Results (WRONG baseline = CPLEX):")
print(f"{'='*80}")
print(f"Baseline objective: {ga_data['baseline']['objective']:.2f}")
print(f"  Urgent wait weighted: {ga_data['baseline']['urgent_wait_weighted']:.2f}")
print(f"  Elective delay: {ga_data['baseline']['elective_delay_total']:.2f}")
print(f"  Overtime: {ga_data['baseline']['overtime_total']}")

print(f"\nGA Best objective: {ga_data['ga_best']['objective']:.2f}")
print(f"  Urgent wait weighted: {ga_data['ga_best']['urgent_wait_weighted']:.2f}")
print(f"  Elective delay: {ga_data['ga_best']['elective_delay_total']:.2f}")
print(f"  Overtime: {ga_data['ga_best']['overtime_total']}")

print(f"\n** Improvement: {ga_data['improvement_pct']:.2f}% (vs CPLEX) **")

# 3. Extract Rule-Based metrics from schedule
urgent_wait = rb_df[rb_df['patient_type'] == 'URGENT']['wait'].sum()
elective_delay = rb_df[rb_df['patient_type'] == 'ELECTIVE']['wait'].sum()

print(f"\n{'='*80}")
print("NEW: Rule-Based Baseline Metrics (CORRECT baseline):")
print(f"{'='*80}")
print(f"  Urgent wait (total): {urgent_wait:.2f}")
print(f"  Elective delay (total): {elective_delay:.2f}")
print(f"  (Note: Need to run full simulation to get weighted urgent wait + overtime)")

print(f"\n{'='*80}")
print("CONCLUSION:")
print(f"{'='*80}")
print("Previous comparison was GA vs CPLEX (wrong!)")
print("Need to run GA from Rule-Based baseline to get correct improvement %")
print(f"Expected: Improvement will be LOWER (Rule-Based already optimized)")
