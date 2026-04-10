import pandas as pd

# Count lines
matches_df = pd.read_csv('auto_merge_matches.csv')
print(f"Total matches: {len(matches_df)}")
print(f"\nFirst match example:")
print(matches_df.iloc[0][['unique_id_l', 'unique_id_r', 'name_l', 'name_r', 'email_l', 'email_r']])
