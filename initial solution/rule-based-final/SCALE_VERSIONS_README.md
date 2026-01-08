# Scale-Specific Versions - README

## Overview
This directory contains 3 scale-specific versions of the simulation and GA optimization code:
- **small_scale_v2/** - For small scale experiments (480 min interarrival)
- **medium_scale_v2/** - For medium scale experiments (210 min interarrival)  
- **large_scale_v2/** - For large scale experiments (112 min interarrival)

## Key Features
Each version automatically reads the urgent patient interarrival time parameter from `Cap_Rank.xlsx` → `urgent parameter` sheet based on its scale.

### Urgent Parameter Values (from Excel)
| Scale  | Inter arrival time (min) | Arrival rate |
|--------|-------------------------|--------------|
| Small  | 480                     | 0.0021       |
| Medium | 210                     | 0.0048       |
| Large  | 112                     | 0.0089       |

## Files in Each Folder
1. **rule_based_or_sim_v3.py** - Rule-based simulator with auto-loading of urgent parameters
2. **ga_optimize_priority_fullschedule.py** - GA optimizer with auto-loading of urgent parameters
3. **lightweight_fitness_priority.py** - Fitness evaluation module (shared)
4. **Cap_Rank.xlsx** - Capability, ranking, and urgent parameter data

## Usage

### Running Rule-Based Simulation
```bash
# Navigate to scale folder
cd small_scale_v2   # or medium_scale_v2 or large_scale_v2

# Run simulation (parameters auto-loaded from Excel)
python rule_based_or_sim_v3.py --work_schedule lich_lam_viec.xlsx --elective_sched schedule.xlsx

# Optional: Override urgent parameter manually
python rule_based_or_sim_v3.py --mean_urgent 600 ...
```

### Running GA Optimization
```bash
# Navigate to scale folder
cd medium_scale_v2

# Run GA (parameters auto-loaded from Excel)
python ga_optimize_priority_fullschedule.py --pop 100 --gens 100

# Optional: Override urgent parameter manually
python ga_optimize_priority_fullschedule.py --mean_urgent 300 --pop 100 --gens 100
```

## How It Works

### Automatic Parameter Loading
Each version includes a helper function:
```python
def load_urgent_param_from_excel(cap_rank_path: str, scale: str) -> float:
    """Load urgent interarrival time from Cap_Rank.xlsx urgent parameter sheet"""
    df = pd.read_excel(cap_rank_path, sheet_name='urgent parameter')
    row = df[df.iloc[:, 0].str.strip().str.lower() == scale.lower()]
    return float(row.iloc[0]['Inter arrival time'])
```

This function is automatically called when:
- `--mean_urgent` is NOT provided (automatic mode)
- Falls back to manual value if `--mean_urgent` is specified

### Console Output
When running, you'll see:
```
Using mean_interarrival_urgent: 480.0 (Small scale)
```
or
```
Using mean_interarrival_urgent: 210.0 (Medium scale)
```

## Modifying Parameters

### Option 1: Edit Excel File
Update `Cap_Rank.xlsx` → `urgent parameter` sheet:
1. Open Cap_Rank.xlsx
2. Go to "urgent parameter" sheet
3. Modify "Inter arrival time" column
4. Save and re-run simulation

### Option 2: Command Line Override
```bash
python rule_based_or_sim_v3.py --mean_urgent 500 ...
python ga_optimize_priority_fullschedule.py --mean_urgent 300 ...
```

## Validation

To verify parameter loading:
```bash
# Test small scale
python -c "import rule_based_or_sim_v3 as sim; print(sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Small scale'))"
# Expected output: 480.0

# Test medium scale  
python -c "import rule_based_or_sim_v3 as sim; print(sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Medium scale'))"
# Expected output: 210.0

# Test large scale
python -c "import rule_based_or_sim_v3 as sim; print(sim.load_urgent_param_from_excel('Cap_Rank.xlsx', 'Large scale'))"
# Expected output: 112.0
```

## Notes
- The old `DEFAULT_MEAN_INTERARRIVAL_URGENT = 2520` constant is still defined for backward compatibility
- Each scale version is independent and self-contained
- All versions share the same code structure, only differing in which scale parameter they load

## Created By
Automated generation script: `create_scale_versions.py` and `create_ga_versions.py`
Date: January 2026
