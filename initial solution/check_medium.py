import pandas as pd

df = pd.read_excel('medium_scale_result.xlsx')
print(f'Total rows in file: {len(df)}')
print(f'Unique patients: {df["pid"].nunique()}')
print(f'\nFirst 10 PIDs:')
print(df['pid'].head(10).tolist())
print(f'\nLast 10 PIDs:')
print(df['pid'].tail(10).tolist())
print(f'\nAll unique PIDs:')
print(sorted(df['pid'].unique()))
