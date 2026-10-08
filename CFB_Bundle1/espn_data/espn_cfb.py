import os
import json
import time
import pandas as pd
from curl_cffi import requests

# Pointing to the specific fitt/v3 powerindex backend feed
BASE_URL = "https://espn.com"
CACHE_FILE = "espn_cache.json"
OUTPUT_CSV = "cfb_espn_metrics.csv"

master_cache = {}

# Step 1: Manage the local cache strategy
if os.path.exists(CACHE_FILE):
    print(f" Reading raw metrics from local cache: '{CACHE_FILE}'...")
    with open(CACHE_FILE, "r") as f:
        master_cache = json.load(f)
else:
    print(" No local cache found. Accessing College Football Power Index 2026 Feed...")
    with requests.Session() as session:
        query_params = {
            "region": "us",
            "lang": "en",
            "season": "2026",
            "limit": "1000" # Increase limit to capture all teams on one handshake page
        }
        
        for attempt in range(1, 4):
            try:
                print(f"  [Attempt {attempt}/3] Querying unified index matrix layers...")
                response = session.get(
                    BASE_URL, 
                    params=query_params, 
                    impersonate="chrome", 
                    timeout=15
                )
                
                if response.status_code == 200:
                    master_cache = response.json()
                    break
                else:
                    print(f"   Server responded with status code: {response.status_code}")
            except Exception as e:
                print(f"   Handshake block on network layer: {e}")
            
            if attempt < 3:
                time.sleep(2)
        
        if not master_cache:
            print("\n Error: Failed to gather data from the FPI layout layer. Exiting.")
            exit()
            
    # Save a clean backup of the structural payload
    with open(CACHE_FILE, "w") as f:
        json.dump(master_cache, f, indent=4)
    print(f"   Success! Web components written to '{CACHE_FILE}'")

# Step 2: Loop and Parse the updated data matrix layer
compiled_teams = []

print("\n Merging 'fpi', 'resume', and 'efficiencies' metrics layout...")
# The payload packages entries under the 'teams' key array list
teams_list = master_cache.get('teams', [])

for entry in teams_list:
    team_node = entry.get('team', {})
    team_name = team_node.get('displayName')
    if not team_name:
        continue
        
    # Isolate structural conference fields
    group_node = team_node.get('group', {})
    conf_name = group_node.get('shortName') or group_node.get('name')
    
    # Initialize basic info block
    team_metrics = {
        "Team": team_name,
        "Conference": conf_name,
        "FPI": None,
        "SOS_Rank": None,
        "Off_Efficiency": None,
        "Def_Efficiency": None
    }
    
    # Extract values out of the inner sequential categories list node
    categories = entry.get('categories', [])
    for cat in categories:
        cat_name = cat.get('name')
        cat_values = cat.get('values', [])
        
        if not cat_values:
            continue
            
        if cat_name == "fpi" and len(cat_values) > 0:
            team_metrics["FPI"] = cat_values[0] # FPI Value is index 0
            
        elif cat_name == "resume" and len(cat_values) > 3:
            team_metrics["SOS_Rank"] = cat_values[3] # SOS Rank is index 3
            
        elif cat_name == "efficiencies" and len(cat_values) > 5:
            team_metrics["Off_Efficiency"] = cat_values[0] # Off Eff value is index 0
            team_metrics["Def_Efficiency"] = cat_values[2] # Def Eff value is index 2

    compiled_teams.append(team_metrics)

# Step 3: Clean up data frame
df = pd.DataFrame(compiled_teams)

if not df.empty:
    df['FPI'] = pd.to_numeric(df['FPI'], errors='coerce')
    # Sort teams by highest FPI value down to lowest
    df = df.sort_values(by='FPI', ascending=False).dropna(subset=['Team'])
    
    print("\n--- Unified ESPN CFB Advanced Metrics (Top 20) ---")
    print(df.head(20).to_string(index=False))
else:
    print("\n Error: Compiled data set evaluated out to a zero-row matrix layer.")

# Step 4: Export to spreadsheet
df.to_csv(OUTPUT_CSV, index=False)
print(f"\n Compilation successfully written to spreadsheet: '{OUTPUT_CSV}'")
