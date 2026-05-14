import pandas as pd
import os

script_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2 copy"
cap_rank_file = os.path.join(script_dir, "Cap_Rank.xlsx")

try:
    df = pd.read_excel(cap_rank_file, sheet_name='capabilities med')
    print("Columns:", df.columns.tolist())
    print(df.head())
except Exception as e:
    print(e)
