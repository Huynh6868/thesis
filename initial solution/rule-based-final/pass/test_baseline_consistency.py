import sys
sys.path.insert(0, r'c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final')

import pandas as pd
from ga_optimize_per_scenario_patched_v3_fullschedule import run_ga_for_scenario
import rule_based_or_sim_v3 as sim

# Load data
elective_df = sim.load_elective_schedule_xlsx("surgery_schedule.xlsx", return_df=True)

# Run for seed 2 with minimal GA (just to get baseline comparison)
print("Running GA to get baseline comparison...")
best_df, best_metrics, baseline_metrics = run_ga_for_scenario(
    elective_input_df=elective_df,
    work_schedule_path="lich_lam_viec_tuan1.xlsx",
    cap_rank_path="Cap_Rank.xlsx",
    scenario_seed=2,
    mean_interarrival=sim.DEFAULT_MEAN_INTERARRIVAL_URGENT,
    rest_time=sim.DEFAULT_REST_TIME_MIN,
    max_reschedule_weeks=1,
    penalty_next_week=sim.DEFAULT_PENALTY_DELAY_NEXT_WEEK,
    pop_size=1,  # Just baseline!
    gens=0,  # No evolution!
    cx_rate=0.85,
    mut_rate=0.35,
    tournament_k=3,
    w_urgent=10.0,
    w_elective_delay=8.0,
    w_overtime=1.0,
    w_next_week=1.0,
    w_shift=0.01,
    seed_ga=123,
)

print("\n" + "="*80)
print("COMPARISON:")
print("="*80)
print(f"Baseline (from rule-based): {baseline_metrics}")
print(f"GA eval (pop=1, gen=0):     {best_metrics}")
print("\nDifference in elective_delay:", best_metrics['elective_delay_total'] - baseline_metrics['elective_delay_total'])
