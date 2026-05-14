import pandas as pd
import os

script_dir = r"c:\Users\ASUS\OneDrive\nam 4\THESIS\code - Copy\initial solution\rule-based-final\medium_scale_v2 copy"
patient_file = os.path.join(script_dir, "patients_80_medium.xlsx")

try:
    df = pd.read_excel(patient_file)
    print("Columns:", df.columns.tolist())
    print("Unique Surgery Names:", df['Surgery_Name'].unique().tolist())
except Exception as e:
    print(e)
