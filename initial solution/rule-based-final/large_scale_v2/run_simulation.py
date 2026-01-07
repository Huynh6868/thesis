#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Large Scale Simulation Runner
Just run this file to start simulation with large scale parameters (112 min interarrival)
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

import rule_based_or_sim_v3 as sim

if __name__ == "__main__":
    # Default configuration for large scale
    default_args = [
        "--work_schedule", "lich_lam_viec_tuan1.xlsx",
        "--cap_rank", "Cap_Rank.xlsx",
        "--elective_sched", "surgery_schedule.xlsx",
        # mean_urgent will be auto-loaded from Excel (112 min)
    ]
    
    # Allow command line overrides
    if len(sys.argv) > 1:
        sys.argv = sys.argv[:1] + default_args + sys.argv[1:]
    else:
        sys.argv = sys.argv + default_args
    
    print("=" * 70)
    print("LARGE SCALE SIMULATION")
    print("Auto-loading urgent parameter from Cap_Rank.xlsx")
    print("=" * 70)
    print()
    
    # Run main simulation
    sim.main()
