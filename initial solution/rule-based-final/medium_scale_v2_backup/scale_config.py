# -*- coding: utf-8 -*-
"""
Scale Configuration Module
Centralizes scale-specific file paths and parameters for medium and large scale simulations.
"""

SCALE_CONFIGS = {
    'small': {
        'patient_file': 'surgery_schedule.xlsx',  # Original small scale
        'capability_sheet': 'Capabilities',
        'work_schedules': ['lich_lam_viec_tuan1.xlsx'],
        'num_weeks': 1,
        'num_doctors': 12  # S1-S12
    },
    'medium': {
        'patient_file': 'medium_scale_result.xlsx',  # Heuristic output
        'capability_sheet': 'capabilities med',
        'work_schedules': [
            'lich_lam_viec_tuan1_med.xlsx',
            'lich_lam_viec_tuan2_med.xlsx'
        ],
        'num_weeks': 2,
        'num_doctors': 16  # S1-S16 for medium scale
    },
    'large': {
        'patient_file': 'large_scale_result.xlsx',  # Heuristic output
        'capability_sheet': 'capabilities large',
        'work_schedules': [
            'lich_lam_viec_tuan1_large.xlsx',
            'lich_lam_viec_tuan2_large.xlsx'
        ],
        'num_weeks': 2,
        'num_doctors': 20  # S1-S20 for large scale
    }
}

def get_scale_config(scale: str):
    """
    Get configuration for a specific scale.
    
    Args:
        scale: One of 'small', 'medium', 'large'
    
    Returns:
        Dictionary with configuration for the scale
    
    Raises:
        ValueError: If scale is not recognized
    """
    if scale.lower() not in SCALE_CONFIGS:
        raise ValueError(f"Unknown scale '{scale}'. Must be one of: {list(SCALE_CONFIGS.keys())}")
    
    return SCALE_CONFIGS[scale.lower()]


def get_surgeon_list(scale: str):
    """
    Get list of surgeon IDs for a given scale.
    
    Args:
        scale: One of 'small', 'medium', 'large'
    
    Returns:
        List of surgeon IDs (e.g., ['S1', 'S2', ..., 'S12'])
    """
    config = get_scale_config(scale)
    return [f"S{i}" for i in range(1, config['num_doctors'] + 1)]
