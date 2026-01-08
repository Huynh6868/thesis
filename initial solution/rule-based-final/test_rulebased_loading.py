# -*- coding: utf-8 -*-
"""
Script to test data loading in rule-based simulation scripts
Tests rule_based_or_sim_v3.py in both medium_scale_v2 and large_scale_v2
"""

import sys
import os

def test_rule_based_imports(scale_name, base_dir):
    """Test if rule-based script can load data correctly"""
    print(f"\n{'='*60}")
    print(f"TESTING RULE-BASED DATA LOADING - {scale_name.upper()} SCALE")
    print(f"{'='*60}")
    
    # Add directory to path
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    
    print(f"\nBase directory: {base_dir}")
    
    try:
        # Import the module functions
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"rule_based_{scale_name}", 
            os.path.join(base_dir, "rule_based_or_sim_v3.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        print("[OK] Successfully imported rule_based_or_sim_v3.py")
        
        # Test loading Cap_Rank.xlsx
        cap_rank_path = os.path.join(base_dir, "Cap_Rank.xlsx")
        
        # 1. Test room config loading
        print("\n1. Testing room config loading:")
        try:
            num_rooms = module.load_room_config(cap_rank_path)
            print(f"   [OK] Number of rooms: {num_rooms}")
        except Exception as e:
            print(f"   [ERROR] Failed to load room config: {e}")
        
        # 2. Test rest time map loading
        print("\n2. Testing rest time map loading:")
        try:
            rest_time_map = module.load_rest_time_map(cap_rank_path)
            print(f"   [OK] Loaded rest time map for {len(rest_time_map)} surgery types")
            
            # Check a specific surgery type (adenotonsillectomy)
            if 'adenotonsillectomy' in rest_time_map:
                main_rest = rest_time_map['adenotonsillectomy']['main']
                asst_rest = rest_time_map['adenotonsillectomy']['assistant']
                print(f"   [OK] Adenotonsillectomy rest times:")
                print(f"        Main surgeon: {main_rest} min")
                print(f"        Assistant: {asst_rest} min")
            else:
                # Try with Operation ID
                print(f"   [WARN] 'adenotonsillectomy' not found in rest_time_map")
                print(f"   Available keys: {list(rest_time_map.keys())[:5]}")
        except Exception as e:
            print(f"   [ERROR] Failed to load rest time map: {e}")
        
        # 3. Test urgent parameter loading
        print("\n3. Testing urgent parameter loading:")
        try:
            scale_str = f"{scale_name} scale"
            mean_interarrival = module.load_urgent_param_from_excel(cap_rank_path, scale_str)
            print(f"   [OK] Mean inter-arrival time for urgent patients: {mean_interarrival} minutes")
            arrival_rate = 1.0 / mean_interarrival if mean_interarrival > 0 else 0
            print(f"        Arrival rate: {arrival_rate:.6f} patients/minute")
        except Exception as e:
            print(f"   [ERROR] Failed to load urgent parameters: {e}")
        
        # 4. Test capability loading
        print("\n4. Testing capability matrix loading:")
        try:
            capability_sheet = 'capabilities med' if scale_name == 'medium' else 'capabilities large'
            cap_model = module.load_cap_rank_xlsx(cap_rank_path, capability_sheet)
            
            # Count capabilities for each surgery type
            num_surgery_types = len(cap_model.main_by_type)
            print(f"   [OK] Loaded capabilities for {num_surgery_types} surgery types")
            
            # Check adenotonsillectomy capabilities
            if 'adenotonsillectomy' in cap_model.main_by_type:
                mains = cap_model.main_by_type['adenotonsillectomy']
                a1s = cap_model.a1_by_type.get('adenotonsillectomy', set())
                a2s = cap_model.a2_by_type.get('adenotonsillectomy', set())
                
                print(f"   [OK] Adenotonsillectomy capabilities:")
                print(f"        Main surgeons: {sorted(mains, key=lambda x: int(x[1:]))}")
                print(f"        Assistant 1: {sorted(a1s, key=lambda x: int(x[1:]))}")
                print(f"        Assistant 2: {sorted(a2s, key=lambda x: int(x[1:]))}")
            else:
                print(f"   [WARN] 'adenotonsillectomy' not found in capability model")
        except Exception as e:
            print(f"   [ERROR] Failed to load capabilities: {e}")
        
        # 5. Test work schedule loading
        print("\n5. Testing work schedule loading:")
        try:
            import pandas as pd
            
            # Get work schedule files from scale_config
            try:
                import scale_config
                config = scale_config.get_scale_config(scale_name)
                work_schedule_files = config.get('work_schedules', [])
                print(f"   [INFO] Work schedule files from config: {work_schedule_files}")
            except Exception:
                # Fallback to default names
                if scale_name == 'medium':
                    work_schedule_files = ['lich_lam_viec_tuan1_med.xlsx', 'lich_lam_viec_tuan2_med.xlsx']
                else:
                    work_schedule_files = ['lich_lam_viec_tuan1_large.xlsx', 'lich_lam_viec_tuan2_large.xlsx']
            
            # Load work schedules
            df_weeks = []
            for ws_file in work_schedule_files:
                ws_path = os.path.join(base_dir, ws_file)
                if os.path.exists(ws_path):
                    df = module.load_work_schedule_xlsx(ws_path)
                    df_weeks.append(df)
                    print(f"   [OK] Loaded {ws_file}: {len(df)} doctors")
                else:
                    print(f"   [WARN] File not found: {ws_file}")
            
            if df_weeks:
                # Determine number of surgeons
                all_surgeons = set()
                for df in df_weeks:
                    for _, row in df.iterrows():
                        doc = row.get("Doctor", None)
                        code = module.parse_surgeon_code(doc)
                        if code:
                            all_surgeons.add(code)
                
                print(f"   [OK] Total unique surgeons in schedule: {len(all_surgeons)}")
                print(f"        Surgeons: {sorted(all_surgeons, key=lambda x: int(x[1:]))}")
                
                # Create WorkSchedule object
                work_sched = module.WorkSchedule(df_weeks, sorted(all_surgeons, key=lambda x: int(x[1:])))
                print(f"   [OK] WorkSchedule object created with {work_sched.num_weeks} weeks")
            
        except Exception as e:
            print(f"   [ERROR] Failed to load work schedules: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n[SUCCESS] All data loading tests completed for {scale_name.upper()} scale")
        
    except Exception as e:
        print(f"\n[ERROR] Failed to import or test module: {e}")
        import traceback
        traceback.print_exc()
    
    # Remove from path to avoid conflicts
    if base_dir in sys.path:
        sys.path.remove(base_dir)

if __name__ == "__main__":
    # Test medium scale
    med_base = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2"
    test_rule_based_imports("medium", med_base)
    
    # Test large scale
    large_base = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2"
    test_rule_based_imports("large", large_base)
    
    print(f"\n\n{'='*60}")
    print("ALL TESTS COMPLETED")
    print(f"{'='*60}")
