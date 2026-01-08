import sys
sys.path.insert(0, r'c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final')

import pandas as pd
import rule_based_or_sim_v3 as sim
from ga_optimize_per_scenario_patched_v3_fullschedule import (
    get_rule_based_baseline,
    generate_urgent_list,
    decode_full_schedule_df,
    GAIndividual
)

# Parameters
scenario_seed = 2
urgent_list = generate_urgent_list(sim.DEFAULT_MEAN_INTERARRIVAL_URGENT, scenario_seed)
elective_df = sim.load_elective_schedule_xlsx("surgery_schedule.xlsx", return_df=True)

# Get baseline
print("Generating rule-based baseline...")
baseline_full_df, baseline_metrics = get_rule_based_baseline(
    work_schedule_path="lich_lam_viec_tuan1.xlsx",
    cap_rank_path="Cap_Rank.xlsx",
    elective_input_df=elective_df,
    urgent_list=urgent_list,
    rest_time=sim.DEFAULT_REST_TIME_MIN,
    max_reschedule_weeks=1,
    penalty_next_week=sim.DEFAULT_PENALTY_DELAY_NEXT_WEEK,
    seed=scenario_seed,
)

print(f"\nBaseline has {len(baseline_full_df)} cases")
print(f"Baseline metrics: elective_delay={baseline_metrics['elective_delay_total']}")

# Create baseline individual (delta=0, room unchanged)
case_ids = baseline_full_df["case_id"].tolist()
base_room = {str(r["case_id"]): int(r["room"]) for _, r in baseline_full_df.iterrows()}
baseline_ind = GAIndividual(
    delta_by_case={cid: 0 for cid in case_ids},
    room_by_case=dict(base_room),
)

# Decode it back
df_work = sim.load_work_schedule_xlsx("lich_lam_viec_tuan1.xlsx")
surgeons = [f"S{i}" for i in range(1, 13)]
work = sim.WorkSchedule(df_work, surgeons)
cap = sim.load_cap_rank_xlsx("Cap_Rank.xlsx")

print("\nDecoding baseline individual (delta=0, room unchanged)...")
decoded_df = decode_full_schedule_df(
    baseline_df=baseline_full_df,
    ind=baseline_ind,
    work=work,
    cap=cap,
    rest_time=sim.DEFAULT_REST_TIME_MIN,
    max_reschedule_weeks=1,
    step=5,
)

print(f"Decoded has {len(decoded_df)} cases")

# Compare schedules
print("\n" + "="*80)
print("COMPARING SCHEDULES:")
print("="*80)

for idx in range(min(10, len(baseline_full_df))):
    b_row = baseline_full_df.iloc[idx]
    d_row = decoded_df[decoded_df["case_id"] == b_row["case_id"]]
    
    if len(d_row) == 0:
        print(f"Case {b_row['case_id']}: MISSING in decoded!")
        continue
    
    d_row = d_row.iloc[0]
    
    if b_row["start"] != d_row["start"]:
        print(f"Case {b_row['case_id']}: start changed! {b_row['start']} -> {d_row['start']} (delta={d_row['start']-b_row['start']})")

print("\nChecking if ALL start times match...")
mismatches = 0
for _, b_row in baseline_full_df.iterrows():
    d_row = decoded_df[decoded_df["case_id"] == b_row["case_id"]]
    if len(d_row) > 0:
        if abs(b_row["start"] - d_row.iloc[0]["start"]) > 0.1:
            mismatches += 1

print(f"Mismatches: {mismatches} out of {len(baseline_full_df)} cases")
