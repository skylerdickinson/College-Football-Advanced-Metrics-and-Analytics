import os
import json
import time
import pandas as pd
from curl_cffi import requests

# Pointing to the specific fitt/v3 powerindex backend feed
BASE_URL = "https://site.web.api.espn.com/apis/fitt/v3/sports/football/college-football/powerindex"
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
            "season": "2026"
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

# Step 2: Loop and Parse the unified datasets
compiled_teams = {}

print("\n Merging 'fpi', 'resume', and 'efficiencies' metrics layout...")
# The fitt/v3 feed packages everything under the 'results' node array
results_list = master_cache.get('results', [])

for item in results_list:
    team_node = item.get('team', {})
    team_name = team_node.get('displayName') or team_node.get('name')
    if not team_name:
        continue
        
    if team_name not in compiled_teams:
        compiled_teams[team_name] = {"Team": team_name}
        
    # Extract deep dictionary values out of the fitt/v3 layout structure
    fpi_stats = item.get('fpi', {})
    resume_stats = item.get('resume', {})
    eff_stats = item.get('efficiencies', {})
    
    compiled_teams[team_name]["FPI"] = fpi_stats.get('fpi')
    compiled_teams[team_name]["SOS_Rank"] = resume_stats.get('sosRank')
    compiled_teams[team_name]["Off_Efficiency"] = eff_stats.get('effOff')
    compiled_teams[team_name]["Def_Efficiency"] = eff_stats.get('effDef')

# Step 3: Clean up data frame
df = pd.DataFrame(compiled_teams.values())

if not df.empty:
    # Ensure numerical properties for clean sorting sequence
    df['FPI'] = pd.to_numeric(df['FPI'], errors='coerce')
    df = df.sort_values(by='FPI', ascending=False).dropna(subset=['Team'])
    
    print("\n--- Unified ESPN CFB Advanced Metrics (Top 20) ---")
    print(df.head(20).to_string(index=False))
else:
    print("\n Error: Compiled data set evaluated out to a zero-row matrix layer.")

# Step 4: Export to spreadsheet
df.to_csv(OUTPUT_CSV, index=False)
print(f"\n Compilation successfully written to spreadsheet: '{OUTPUT_CSV}'")
