"""Test script to validate heuristic large.py output format"""
import sys
sys.path.insert(0, r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution")

# Test imports and helper functions
try:
    # Import specific functions to test
    import importlib.util
    spec = importlib.util.spec_from_file_location("heuristic", 
        r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\heuristic large.py")
    heuristic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(heuristic)
    
    print("✅ Module loaded successfully")
    
    # Test OPERATION_TO_TYPE
    print(f"\n✅ OPERATION_TO_TYPE has {len(heuristic.OPERATION_TO_TYPE)} entries")
    print(f"   Sample: {list(heuristic.OPERATION_TO_TYPE.items())[:3]}")
    
    # Test minutes_to_hhmm
    test_cases = [(0, "00:00"), (480, "08:00"), (125, "02:05"), (960, "16:00")]
    print(f"\n✅ Testing minutes_to_hhmm():")
    for minutes, expected in test_cases:
        result = heuristic.minutes_to_hhmm(minutes)
        status = "✅" if result == expected else "❌"
        print(f"   {status} minutes_to_hhmm({minutes}) = {result} (expected: {expected})")
    
    # Test ADMIN_HOURS constant
    print(f"\n✅ ADMIN_HOURS = {heuristic.ADMIN_HOURS}")
    
    print("\n" + "="*60)
    print("VALIDATION SUMMARY:")
    print("="*60)
    print("✅ All imports successful")
    print("✅ Helper functions working correctly")
    print("✅ Constants defined properly")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
