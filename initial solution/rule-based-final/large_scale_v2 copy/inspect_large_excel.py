import pandas as pd
import os

script_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2 copy"
cap_rank_file = os.path.join(script_dir, "Cap_Rank.xlsx")

try:
    # Try loading 'capabilities large' as hinted in config
    df = pd.read_excel(cap_rank_file, sheet_name='capabilities large')
    print("Sheet 'capabilities large' found.")
    print("Columns:", df.columns.tolist())
    print(df.head())
except Exception as e:
    print(f"Error loading 'capabilities large': {e}")
    try:
        xl = pd.ExcelFile(cap_rank_file)
        print("Available sheets:", xl.sheet_names)
    except Exception as e2:
        print(f"Error reading Excel file: {e2}")
