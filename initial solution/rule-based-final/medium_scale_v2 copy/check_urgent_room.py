import rule_based_or_sim_v3 as sim

print("=" * 60)
print("URGENT PARAMETER & ROOM VERIFICATION")
print("=" * 60)

# Check urgent parameter loading
print("\n1. URGENT PARAMETER:")
try:
    small_urgent = sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Small scale')
    print(f"   Small scale: {small_urgent} minutes")
except Exception as e:
    print(f"   Small scale: ERROR - {e}")

try:
    medium_urgent = sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Medium scale')
    print(f"   Medium scale: {medium_urgent} minutes")
except Exception as e:
    print(f"   Medium scale: ERROR - {e}")

try:
    large_urgent = sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Large scale')
    print(f"   Large scale: {large_urgent} minutes")
except Exception as e:
    print(f"   Large scale: ERROR - {e}")

# Check room configuration
print("\n2. ROOM CONFIGURATION:")
try:
    small_rooms = sim.load_room_config('Cap_Rank.xlsx', 'small')
    print(f"   Small scale: {small_rooms} rooms")
except Exception as e:
    print(f"   Small scale: ERROR - {e}")

try:
    medium_rooms = sim.load_room_config('Cap_Rank.xlsx', 'medium')
    print(f"   Medium scale: {medium_rooms} rooms")
except Exception as e:
    print(f"   Medium scale: ERROR - {e}")

try:
    large_rooms = sim.load_room_config('Cap_Rank.xlsx', 'large')
    print(f"   Large scale: {large_rooms} rooms")
except Exception as e:
    print(f"   Large scale: ERROR - {e}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
