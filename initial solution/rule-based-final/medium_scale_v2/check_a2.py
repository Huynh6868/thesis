import rule_based_or_sim_v3 as sim

cap = sim.load_cap_rank_xlsx('Cap_Rank.xlsx')
a2 = cap.a2_by_type.get('thyroidectomy', set())
print(f'Assistant 2: {sorted(a2)}')
print(f'Has S16: {"S16" in a2}')
print(f'Total surgeons in a2: {len(a2)}')
