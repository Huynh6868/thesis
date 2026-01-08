#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Small Scale Simulation Runner
Just run this file to start simulation with small scale parameters (480 min interarrival)
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

import rule_based_or_sim_v3 as sim

if __name__ == "__main__":
    # Default configuration for small scale
    default_args = [
        "--work_schedule", "lich_lam_viec_tuan1.xlsx", "lich_lam_viec_tuan2.xlsx",
        "--cap_rank", "Cap_Rank.xlsx",
        "--elective_sched", "surgery_schedule.xlsx",
        # mean_urgent will be auto-loaded from Excel (480 min)
    ]
    
    # Allow command line overrides
    if len(sys.argv) > 1:
        sys.argv = sys.argv[:1] + default_args + sys.argv[1:]
    else:
        sys.argv = sys.argv + default_args
    
    print("=" * 70)
    print("SMALL SCALE SIMULATION")
    print("Auto-loading urgent parameter from Cap_Rank.xlsx")
    print("=" * 70)
    print()
    
    # Run main simulation
    sim.main()
