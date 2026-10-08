import sys
import asyncio
import json
import logging
import traceback
import csv
from curl_cffi.requests import AsyncSession

# ==============================================================================
# 1. NETWORKING & ERROR LOG CONFIGURATION (Completely separate from console)
# ==============================================================================
logger = logging.getLogger("NetworkLogger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("network_handshakes.log", mode="w")
file_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# ==============================================================================
# 2. HIDDEN CALENDAR ROUTINE: Find current week dynamics
# ==============================================================================
async def get_espn_current_week(session: AsyncSession) -> tuple:
    """
    Queries ESPN's root core API to discover the exact season type and week number 
    active right now, eliminating empty hardcoded date arrays.
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    try:
        logger.debug("Querying hidden core API for active week identification parameters...")
        response = await session.get(url, headers=headers, impersonate="chrome120", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            season_type = data.get("season", {}).get("type", 2)  # 2 = Regular Season
            week_num = data.get("week", {}).get("number", 1)
            logger.info(f"Targeting active ESPN grid window: Season Type {season_type}, Week {week_num}")
            return season_type, week_num
    except Exception as e:
        logger.error(f"Failed to pull calendar meta configuration: {str(e)}")
    return 2, 1  # Fallback gracefully to week 1 if meta extraction fails


# ==============================================================================
# 3. CHUNKED ROLLING FETCH ENGINE
# ==============================================================================
async def fetch_espn_week_data(session: AsyncSession, season_type: int, week: int, group: int) -> dict:
    """
    Executes a heavily targeted hidden API call using explicit group structures.
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
    
    params = {
        "limit": "100",
        "groups": str(group),       # 80 = FBS Mainline, 81 = FCS Alternative
        "seasontype": str(season_type),
        "week": str(week)
    }
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.espn.com",
        "Referer": "https://www.espn.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        logger.debug(f"Sending rolling worker target -> Group: {group}, Week: {week}")
        response = await session.get(url, params=params, headers=headers, impersonate="chrome120", timeout=15.0)
        
        logger.info(f"Handshake success | Group: {group} | Status: {response.status_code}")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        tb_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.error(f"TLS/Network Exception for group {group}:\n{tb_text}")
    return {}


async def process_schedule_rolling_loop():
    """
    Drives the rolling chunk loop while keeping targets structured in groups of 19 or fewer.
    """
    all_raw_data = []

    async with AsyncSession() as session:
        # Step A: Discover what week index the schedule is running on
        season_type, current_week = await get_espn_current_week(session)
        
        # Step B: Define target array explicitly inside list boundaries
        target_groups = [80, 81]  
        chunk_size = 19  
        
        for i in range(0, len(target_groups), chunk_size):
            chunk = target_groups[i:i + chunk_size]
            logger.debug(f"Spawning target processing vectors: {chunk}")
            
            tasks = [fetch_espn_week_data(session, season_type, current_week, group_id) for group_id in chunk]
            chunk_results = await asyncio.gather(*tasks)
            
            all_raw_data.extend(chunk_results)
            await asyncio.sleep(0.5) 
            
    return all_raw_data


# ==============================================================================
# 4. DATA EXTRACTION ENGINE & CSV STORAGE
# ==============================================================================
def parse_and_save_to_csv(raw_payloads: list, output_filename: str = "cfb_weekly_schedule.csv"):
    """
    Processes response data payloads cleanly and writes directly to a CSV document.
    """
    headers = ["Date/Time (ISO)", "Away Team", "Away Score", "Home Team", "Home Score", "Status"]
    games_list = []
    
    for payload in raw_payloads:
        if not payload or "events" not in payload:
            continue
            
        for event in payload["events"]:
            try:
                date_iso = event.get("date")
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                
                competition = competitions[0]
                status_text = competition["status"]["type"]["detail"]
                
                competitors = competition["competitors"]
                home_team = next(t for t in competitors if t["homeAway"] == "home")
                away_team = next(t for t in competitors if t["homeAway"] == "away")
                
                home_name = home_team["team"]["displayName"]
                away_name = away_team["team"]["displayName"]
                
                home_score = home_team.get("score", "0")
                away_score = away_team.get("score", "0")
                
                games_list.append([date_iso, away_name, away_score, home_name, home_score, status_text])
            except Exception as e:
                tb_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                logger.error(f"Extraction Node failure:\n{tb_text}")
                continue
                
    try:
        with open(output_filename, mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            writer.writerows(games_list)
        print(f"\n{'='*70}\n CSV EXPORT SUCCESSFUL\n{'='*70}")
        print(f"Successfully compiled and saved {len(games_list)} games to: {output_filename}\n{'='*70}")
    except Exception as csv_err:
        print(f"Error writing data to CSV file: {str(csv_err)}")


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    print("[*] Instantiating Network Handshakes... Tracking via network_handshakes.log")
    extracted_payloads = asyncio.run(process_schedule_rolling_loop())
    
    print("[*] Processing Raw Payloads via Extraction Module & Saving...")
    parse_and_save_to_csv(extracted_payloads)
