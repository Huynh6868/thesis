import sys
sys.path.insert(0, r'c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final')

from ga_optimize_per_scenario_patched_v3_fullschedule import generate_urgent_list
import rule_based_or_sim_v3 as sim

# Test with same parameters as GA
mean_urgent = sim.DEFAULT_MEAN_INTERARRIVAL_URGENT
scenario_seed = 2

urgent_list = generate_urgent_list(mean_urgent, scenario_seed)
print(f"Mean interarrival: {mean_urgent}")
print(f"Scenario seed: {scenario_seed}")
print(f"Generated {len(urgent_list)} urgent arrivals:")
for i, (t, stype) in enumerate(urgent_list, 1):
    day = int(t // 1440)
    print(f"  U{i}: Day {day}, t={t:.0f}min, type={stype}")
