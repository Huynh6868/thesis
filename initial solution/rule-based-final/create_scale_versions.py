# Helper script to create 3 scale versions with parameter reading from Excel
import shutil
import os

scales = {
    'small_scale_v2': 'Small scale',
    'medium_scale_v2': 'Medium scale', 
    'large_scale_v2': 'Large scale'
}

base_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final"

# Function code to add to each file
read_param_function = '''
def load_urgent_param_from_excel(cap_rank_path: str, scale: str) -> float:
    """
    Load urgent interarrival time parameter from Cap_Rank.xlsx urgent parameter sheet.
    
    Args:
        cap_rank_path: Path to Cap_Rank.xlsx
        scale: One of 'Small scale', 'Medium scale', 'Large scale'
    
    Returns:
        mean_interarrival_urgent in minutes
    """
    try:
        df = pd.read_excel(cap_rank_path, sheet_name='urgent parameter')
        # Find row matching the scale
        row = df[df.iloc[:, 0].str.strip().str.lower() == scale.lower()]
        if row.empty:
            print(f"Warning: Scale '{scale}' not found in urgent parameter sheet. Using default.")
            return DEFAULT_MEAN_INTERARRIVAL_URGENT
        return float(row.iloc[0]['Inter arrival time'])
    except Exception as e:
        print(f"Error loading urgent parameter: {e}. Using default.")
        return DEFAULT_MEAN_INTERARRIVAL_URGENT
'''

print("Creating scale-specific versions...")

# Read original file
with open(os.path.join(base_dir, 'rule_based_or_sim_v3.py'), 'r', encoding='utf-8') as f:
    original_content = f.read()

for folder, scale_name in scales.items():
    print(f"\nCreating {folder} version for '{scale_name}'...")
    
    # Modify content
    lines = original_content.split('\n')
    new_lines = []
    
    # Add import if not exists and insert helper function after imports
    import_section_end = 0
    for i, line in enumerate(lines):
        new_lines.append(line)
        if line.strip().startswith('import pandas as pd'):
            import_section_end = i
    
    # Insert helper function after global config section (after line with DEFAULT_PENALTY_DELAY_NEXT_WEEK)
    inserted = False
    final_lines = []
    for i, line in enumerate(new_lines):
        final_lines.append(line)
        if 'DEFAULT_PENALTY_DELAY_NEXT_WEEK' in line and not inserted:
            final_lines.append('')
            final_lines.extend(read_param_function.split('\n'))
            inserted = True
    
    # Write to new file
    output_path = os.path.join(base_dir, folder, 'rule_based_or_sim_v3.py')
    with open(output_path, 'w', encoding='utf-8') as f:
        modified_content = '\n'.join(final_lines)
        
        # Replace DEFAULT_MEAN_INTERARRIVAL_URGENT usage in main
        # Find the main() function and update argument parser default
        modified_content = modified_content.replace(
            'parser.add_argument("--mean_urgent", type=float, default=DEFAULT_MEAN_INTERARRIVAL_URGENT,',
            f'parser.add_argument("--mean_urgent", type=float, default=None,'
        )
        
        # Add scale parameter loading in main
        # Find where args are used and add dynamic loading
        main_insert = f'''
    # Load urgent parameter from Excel based on scale
    if args.mean_urgent is None:
        args.mean_urgent = load_urgent_param_from_excel(args.cap_rank, '{scale_name}')
    print(f"Using mean_interarrival_urgent: {{args.mean_urgent}} ({scale_name})")
'''
        
        # Insert after args parsing (find "args = parser.parse_args()")
        modified_content = modified_content.replace(
            'args = parser.parse_args()',
            f'args = parser.parse_args(){main_insert}'
        )
        
        f.write(modified_content)
    
    print(f"  Created: {output_path}")
    
    # Copy Cap_Rank.xlsx
    shutil.copy(
        os.path.join(base_dir, 'Cap_Rank.xlsx'),
        os.path.join(base_dir, folder, 'Cap_Rank.xlsx')
    )
    print(f"  Copied Cap_Rank.xlsx")

print("\n✓ All scale versions created successfully!")
print("\nFolders:")
for folder in scales.keys():
    print(f"  - rule-based-final/{folder}/")
