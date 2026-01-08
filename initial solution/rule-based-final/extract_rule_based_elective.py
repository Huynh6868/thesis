# Extract elective-only schedule from Rule-Based baseline for GA input
import pandas as pd
import rule_based_or_sim_v3 as sim

# Load Rule-Based combined baseline
rb_df = pd.read_excel("rule_based_baseline_seed1.xlsx")

# Extract ELECTIVE only
elective_df = rb_df[rb_df['patient_type'] == 'ELECTIVE'].copy()

# Convert to GA input format
# patient_id "P14" -> pid=14, "E14" also possible
elective_df['pid'] = elective_df['patient_id'].apply(
    lambda x: int(x[1:]) if isinstance(x, str) and (x.startswith('P') or x.startswith('E')) else int(x)
)

# Keep necessary columns in GA format
ga_input = elective_df[[
    'pid', 'surgery_type', 'day', 'time_hhmm', 
    'room', 'main', 'assist1', 'assist2'
]].copy()

# Save as GA input
ga_input.to_excel("rule_based_elective_only_seed1.xlsx", index=False)

print(f"Extracted {len(ga_input)} elective cases from Rule-Based baseline")
print(f"Saved to: rule_based_elective_only_seed1.xlsx")
print(f"\nFirst 5 cases:")
print(ga_input.head().to_string())
