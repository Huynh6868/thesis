import rule_based_or_sim_v3 as sim

# Load capability model
cap = sim.load_cap_rank_xlsx('Cap_Rank.xlsx')

print("=" * 60)
print("CAPABILITY MODEL VERIFICATION - Medium Scale")
print("=" * 60)

# Check all assistant 2 surgeons
print("\nAssistant 2 surgeons by surgery type:")
for stype in sorted(cap.a2_by_type.keys()):
    a2_list = sorted(list(cap.a2_by_type[stype]))
    print(f"  {stype:30s}: {a2_list}")

# Check specific expected configuration
expected_a2 = {'S9', 'S10', 'S11', 'S12', 'S16'}
print(f"\nExpected assistant 2 for medium scale: {sorted(expected_a2)}")

# Verify for a sample surgery type
sample_type = 'thyroidectomy'
actual_a2 = cap.a2_by_type.get(sample_type, set())
print(f"Actual assistant 2 for {sample_type}: {sorted(actual_a2)}")

if actual_a2 == expected_a2:
    print("✅ CORRECT: Cap_Rank.xlsx has correct medium scale configuration")
else:
    missing = expected_a2 - actual_a2
    extra = actual_a2 - expected_a2
    print("❌ INCORRECT: Cap_Rank.xlsx does NOT match medium scale")
    if missing:
        print(f"   Missing surgeons: {sorted(missing)}")
    if extra:
        print(f"   Extra surgeons: {sorted(extra)}")
