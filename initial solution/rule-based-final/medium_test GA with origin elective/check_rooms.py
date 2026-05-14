import pandas as pd

df = pd.read_excel('medium_rulebased_output.xlsx')
print(f'Max room number: {df["room"].max()}')
print(f'Unique rooms: {sorted(df["room"].unique())}')
print(f'Total number of rooms: {len(df["room"].unique())}')
