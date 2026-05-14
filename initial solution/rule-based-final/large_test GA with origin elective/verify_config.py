import rule_based_or_sim_v3 as sim

print("=" * 60)
print("LARGE SCALE CONFIGURATION CHECK")
print("=" * 60)

# 1. Urgent parameter
mean_urgent = sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Large scale')
print(f"\n1. Urgent parameter:")
print(f"   Mean interarrival time: {mean_urgent} minutes")

# 2. Rest time
rest_time_map = sim.load_rest_time_map('Cap_Rank.xlsx')
print(f"\n2. Rest time configuration:")
print(f"   Type: {type(rest_time_map)}")
sample_types = ['thyroidectomy', 'rhinoplasty', 'microlaryngoscopy']
for stype in sample_types:
    rest_val = rest_time_map.get(stype, "Not found")
    print(f"   {stype}: {rest_val}")

# 3. Capabilities
cap = sim.load_cap_rank_xlsx('Cap_Rank.xlsx', capability_sheet='capabilities large')
print(f"\n3. Surgeon capabilities:")
print(f"   Main surgeons (thyroidectomy): {sorted(cap.main_by_type.get('thyroidectomy', set()))}")
print(f"   Assistant 1 (thyroidectomy): {sorted(cap.a1_by_type.get('thyroidectomy', set()))}")
print(f"   Assistant 2 (thyroidectomy): {sorted(cap.a2_by_type.get('thyroidectomy', set()))}")

# 4. Room config
rooms = sim.load_room_config('Cap_Rank.xlsx', 'large')
print(f"\n4. Room configuration:")
print(f"   Number of rooms: {rooms}")

print(f"\n5. Other parameters:")
print(f"   Expected number of surgeons: 20 (S1-S20)")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
