# Helper script to create GA versions for 3 scales
import shutil
import os

scales = {
    'small_scale_v2': 'Small scale',
    'medium_scale_v2': 'Medium scale',
    'large_scale_v2': 'Large scale'
}

base_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final"

# Read original GA file
with open(os.path.join(base_dir, 'ga_optimize_priority_fullschedule.py'), 'r', encoding='utf-8') as f:
    original_ga = f.read()

print("Creating GA versions for each scale...")

for folder, scale_name in scales.items():
    print(f"\nCreating {folder}/ga_optimize_priority_fullschedule.py for '{scale_name}'...")
    
    # Modify GA content
    modified_ga = original_ga
    
    # Update the default mean_urgent parameter to None
    modified_ga = modified_ga.replace(
        'parser.add_argument("--mean_urgent", type=float, default=sim.DEFAULT_MEAN_INTERARRIVAL_URGENT)',
        f'parser.add_argument("--mean_urgent", type=float, default=None)'
    )
    
    # Add parameter loading after args parsing
    param_loading = f'''
    # Load urgent parameter from Excel based on scale
    if args.mean_urgent is None:
        args.mean_urgent = sim.load_urgent_param_from_excel(args.cap_rank, '{scale_name}')
    print(f"Using mean_interarrival_urgent: {{args.mean_urgent}} ({scale_name})")
'''
    
    # Insert after args parsing
    modified_ga = modified_ga.replace(
        'args = parser.parse_args()',
        f'args = parser.parse_args(){param_loading}'
    )
    
    # Write to new file
    output_path = os.path.join(base_dir, folder, 'ga_optimize_priority_fullschedule.py')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(modified_ga)
    
    print(f"  Created: {output_path}")
    
    # Copy lightweight_fitness_priority.py if exists
    fitness_file = os.path.join(base_dir, 'lightweight_fitness_priority.py')
    if os.path.exists(fitness_file):
        shutil.copy(fitness_file, os.path.join(base_dir, folder, 'lightweight_fitness_priority.py'))
        print(f"  Copied lightweight_fitness_priority.py")

print("\nAll GA versions created successfully!")
print("\nScale versions created in:")
for folder in scales.keys():
    print(f"  - rule-based-final/{folder}/")
