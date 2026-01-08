#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Medium Scale GA Optimizer Runner
Just run this file to start GA optimization with medium scale parameters (210 min interarrival)
"""

import sys
import os

# Get script directory and change to it
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Add current directory to path
sys.path.insert(0, script_dir)

import ga_optimize_priority_fullschedule as ga

if __name__ == "__main__":
    # Default configuration for medium scale GA optimization
    # Using absolute paths based on script directory
    default_args = [
        "--work_schedule", os.path.join(script_dir, "lich_lam_viec_tuan1_med.xlsx"),
        "--cap_rank", os.path.join(script_dir, "Cap_Rank.xlsx"),
        "--elective_sched", os.path.join(script_dir, "medium_scale_result.xlsx"),
        "--pop", "50",          # Population size
        "--gens", "50",         # Number of generations
        "--scenario_seed", "1", # Scenario seed
        # mean_urgent will be auto-loaded from Excel (210 min)
    ]
    
    # Allow command line overrides
    if len(sys.argv) > 1:
        sys.argv = sys.argv[:1] + default_args + sys.argv[1:]
    else:
        sys.argv = sys.argv + default_args
    
    print("=" * 70)
    print("MEDIUM SCALE GA OPTIMIZATION")
    print("Auto-loading urgent parameter from Cap_Rank.xlsx")
    print("Population: 50, Generations: 50")
    print("=" * 70)
    print()
    
    # Run main GA
    ga.main()

