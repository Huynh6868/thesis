import pandas as pd
import os

script_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\large_scale_v2 copy"
cap_rank_file = os.path.join(script_dir, "Cap_Rank.xlsx")

try:
    df = pd.read_excel(cap_rank_file, sheet_name='capabilities large')
    # Filter for Op 7 (Thyroidectomy)
    # Note: Name might be 'Thyroid' or similar
    row = df[df['Operation'] == 7].iloc[0]
    print("Op 7 Capabilities:")
    print("Main:", row['Main surgeon'])
    print("Assist 1:", row['Assistant 1'])
    print("Assist 2:", row['Assistant 2'])
    
    # Check Assignment: P012 (Thyroidectomy): S5, S3, S9
    # S5 in Main?
    # S3 in Assist 1?
    # S9 in Assist 2?
    
except Exception as e:
    print(e)
