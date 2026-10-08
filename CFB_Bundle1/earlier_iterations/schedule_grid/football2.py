# ==========================================
# PART 1: IMPORTS & DATA CLEANING START
# ==========================================
import io
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ReportLab Visual Layer Components
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def clean_team_name(name):
    """
    Cleans raw web string inputs into sanitized school names.
    Strips rankings symbols like '#' and chops text appended in parentheses.
    """
    if not isinstance(name, str):
        return ""
    if '(' in name:
        name = name.split('(')[0]
    name = name.replace("#", "").strip()
    
    mapping = {
        "Miami OH": "Miami (OH)",
        "NC State": "North Carolina State",
        "App State": "Appalachian State",
        "E Carolina": "East Carolina",
        "Arizona St": "Arizona State",
        "Texas A&M": "Texas A&M",
        "Penn St": "Penn State",
        "Kent St": "Kent State",
        "W Kentucky": "Western Kentucky",
        "West Virginia": "West Virginia",
        "C Michigan": "Central Michigan",
        "Ball St": "Ball State",
        "Mississippi St": "Mississippi State",
        "Utah St": "Utah State",
        "Texas St": "Texas State",
        "Akron": "Akron",
        "E Michigan": "Eastern Michigan",
        "Michigan St": "Michigan State",
        "J Madison": "James Madison",
        "Florida St": "Florida State",
        "San Jose St": "San Jose State",
        "Ohio St": "Ohio State",
        "Texas Tech": "Texas Tech",
        "Oregon St": "Oregon State",
        "Iowa St": "Iowa State",
        "Coastal Car": "Coastal Carolina",
        "Florida Atlantic": "Florida Atlantic",
        "Southern Miss": "Southern Mississippi",
        "Kennesaw St": "Kennesaw State",
        "Sam Houston": "Sam Houston State",
        "Missouri St": "Missouri State",
        "Arkansas St": "Arkansas State",
        "Colorado St": "Colorado State",
        "Georgia Tech": "Georgia Tech",
        "San Diego St": "San Diego State",
        "Fresno St": "Fresno State"
    }
    return mapping.get(name, name)

# ==========================================
# PART 1: IMPORTS & DATA CLEANING END
# ==========================================
# ==========================================
# PART 2: DYNAMIC TEXT FILE LOADER START
# ==========================================
def fetch_live_cfb_schedule():
    """
    Dynamically opens and reads raw text lines directly from 'cfb_list.txt' 
    in this script's own folder, cleanly stripping out browser tabs and time elements.
    """
    desktop_dir = os.path.dirname(os.path.abspath(__file__))  # now anchored to this script's own folder instead of a hardcoded user path
    file_path = os.path.join(desktop_dir, "cfb_list.txt")
    
    if not os.path.exists(file_path):
        print(f"\n⚠️  System cannot find file: '{file_path}'")
        print("👉 Please create a plain text file named 'cfb_list.txt' in this script's own folder and paste your schedule list inside.\n")
        return pd.DataFrame()
        
    games_list = []
    fcs_ignore_list = [
        "Florida A&M", "Norfolk St", "Richmond", "Villanova", "Howard", 
        "East Tennessee State", "Wofford", "TN Martin", "Colgate", "Holy Cross", 
        "Stony Brook", "Robert Morris", "Wagner", "Sacred Heart", 
        "Central Connecticut State", "Alabama St", "N Colorado", "UC Davis", 
        "Mercyhurst", "Delaware", "Campbell", "Gard-Webb", "Monmouth", 
        "Illinois State", "Towson", "Lindenwood", "Southern", "West Georgia", 
        "S Utah", "W Carolina", "W Illinois", "Fordham", "Grambling St", 
        "Prairie View A&M", "Cal Poly", "Texas Southern", "Montana St"
    ]

    print(f"📋 Reading new raw weekly slate from text file: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                line_str = line.strip()
                if "@" in line_str:
                    parts = line_str.split('@')
                    
                    # Clean up Away Team name from the left side of the split
                    away_raw = parts[0].split('\t')[-1].strip()
                    
                    # Clean up Home Team name from the right side of the split
                    home_chunk = parts[1].strip()
                    home_raw = home_chunk.split('\t')[0].split('  ')[0].strip()
                    
                    if away_raw not in fcs_ignore_list and home_raw not in fcs_ignore_list:
                        away_clean = clean_team_name(away_raw)
                        home_clean = clean_team_name(home_raw)
                        
                        games_list.append({
                            "Game": f"{away_clean} at {home_clean}",
                            "Away_Team": away_clean,
                            "Home_Team": home_clean
                        })
    except Exception as e:
        print(f"❌ Error reading text from cfb_list.txt: {e}")
        
    return pd.DataFrame(games_list)

# ==========================================
# PART 2: DYNAMIC TEXT FILE LOADER END
# ==========================================
# ==========================================
# PART 3: MATRIX STATS CONSOLIDATOR START
# ==========================================
def fetch_all_teamrankings_stats():
    """Gathers stats using isolated structural indexing to forcefully block repetition errors."""
    turnover_slug = "/college-football/stat/turnover-margin-per-game"
    
    offense_metrics = {
        "/college-football/stat/yards-per-game": "Off_Yds_PG",
        "/college-football/stat/yards-per-play": "Off_YPP",
        "/college-football/stat/passing-yards-per-game": "Off_Pass_PG",
        "/college-football/stat/yards-per-pass-attempt": "Off_Pass_Att",
        "/college-football/stat/rushing-yards-per-game": "Off_Rush_PG",
        "/college-football/stat/yards-per-rush-attempt": "Off_Rush_Att",
        "/college-football/stat/points-per-game": "Off_PPG",  
        "/college-football/stat/third-down-conversion-pct": "Off_3rd_%",
        "/college-football/stat/red-zone-scoring-pct": "Off_RZ_%",
    }
    
    defense_metrics = {
        "/college-football/stat/opponent-yards-per-game": "Def_Yds_PG",
        "/college-football/stat/opponent-yards-per-play": "Def_YPP",
        "/college-football/stat/opponent-passing-yards-per-game": "Def_Pass_PG",
        "/college-football/stat/opponent-yards-per-pass-attempt": "Def_Pass_Att",
        "/college-football/stat/opponent-rushing-yards-per-game": "Def_Rush_PG",
        "/college-football/stat/opponent-yards-per-rush-attempt": "Def_Rush_Att",
        "/college-football/stat/opponent-points-per-game": "Def_PPG",  
        "/college-football/stat/opponent-third-down-conversion-pct": "Def_3rd_%",
        "/college-football/stat/opponent-red-zone-scoring-pct": "Def_RZ_%",
    }

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    master_df = None

    def scrape_metric_group(metrics_dict):
        group_df = None
        for slug, col_name in metrics_dict.items():
            url = f"https://teamrankings.com{slug}"
            try:
                response = requests.get(url, headers=headers, timeout=10)
                tables = pd.read_html(io.StringIO(response.text))
                raw_df = tables[0]
                
                team_series = raw_df.iloc[:, 1]
                value_series = raw_df.iloc[:, 2]
                
                df_clean = pd.DataFrame({'Clean_Name': team_series, col_name: value_series})
                df_clean['Clean_Name'] = df_clean['Clean_Name'].apply(clean_team_name)
                
                if group_df is None:
                    group_df = df_clean
                else:
                    group_df = pd.merge(group_df, df_clean, on="Clean_Name", how="outer")
            except Exception:
                pass
        return group_df

    try:
        to_url = f"https://teamrankings.com{turnover_slug}"
        to_response = requests.get(to_url, headers=headers, timeout=10)
        to_tables = pd.read_html(io.StringIO(to_response.text))
        raw_to_df = to_tables[0]
        
        master_df = pd.DataFrame({
            'Clean_Name': raw_to_df.iloc[:, 1],
            'Net_TO_Margin': raw_to_df.iloc[:, 2]
        })
        master_df['Clean_Name'] = master_df['Clean_Name'].apply(clean_team_name)
    except Exception:
        master_df = pd.DataFrame(columns=['Clean_Name', 'Net_TO_Margin'])

    off_df = scrape_metric_group(offense_metrics)
    def_df = scrape_metric_group(defense_metrics)

    if off_df is not None:
        master_df = pd.merge(master_df, off_df, on="Clean_Name", how="outer")
    if def_df is not None:
        master_df = pd.merge(master_df, def_df, on="Clean_Name", how="outer")

    return master_df

# ==========================================
# PART 3: MATRIX STATS CONSOLIDATOR END
# ==========================================
# ==========================================
# PART 4: PDF DOCUMENT GENERATOR START
# ==========================================
def generate_pdf_report(schedule_df, stats_lookup, filename="generated/cfb_matrices_outlook.pdf"):
    """Compiles schedules into a black-background stacked comparison layout with color conditional metrics."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    doc = SimpleDocTemplate(
        filename, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
        title="College Football On-Field Matchup Explorer"
    )
    styles = getSampleStyleSheet()
    
    bg_dark = colors.HexColor('#121212')
    card_bg = colors.HexColor('#1E1E1E')
    text_white = colors.HexColor('#FFFFFF')
    accent_blue = colors.HexColor('#1A365D')
    color_green = colors.HexColor('#48BB78') 
    color_red = colors.HexColor('#F56565')   
    team_cyan = colors.HexColor('#4FD1C5')

    national_baselines = {
        'YDS': 400.0, 'YPP': 5.5, 'PAS': 225.0, 'PAA': 7.2,
        'RUS': 175.0, 'RUA': 4.2, 'PPG': 28.0, '3RD': 40.0, 'RZ': 80.0
    }

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=text_white, alignment=1, spaceAfter=12)
    matchup_header_style = ParagraphStyle('MatchHeader', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=text_white)
    
    def make_cell_p(text, color_obj=text_white, is_bold=False):
        f_name = 'Helvetica-Bold' if is_bold else 'Helvetica'
        return Paragraph(f'<font color="{color_obj.hexval()}">{text}</font>', 
                         ParagraphStyle('cell', fontName=f_name, fontSize=8, leading=11, alignment=1 if not is_bold else 0))

    story = [Paragraph("COLLEGE FOOTBALL METRIC MATCHUP SYMMETRY", title_style), Spacer(1, 10)]
    col_widths = [135, 15, 43.3, 43.3, 43.3, 43.3, 43.3, 43.3, 43.3, 43.3, 43.3]
    
    for _, row in schedule_df.iterrows():
        away, home = row['Away_Team'], row['Home_Team']
        matchup_elements = []
        
        try:
            away_to = str(stats_lookup.loc[away].get('Net_TO_Margin', '--'))
            home_to = str(stats_lookup.loc[home].get('Net_TO_Margin', '--'))
        except KeyError:
            away_to = home_to = '--'

        banner_text = f"🏈 FIELD MATCHUP: {away.upper()} ({away_to if '-' in away_to or '0' in away_to else '+' + away_to} TO) AT {home.upper()} ({home_to if '-' in home_to or '0' in home_to else '+' + home_to} TO)"
        
        header_table = Table([[Paragraph(banner_text, matchup_header_style)]], colWidths=[540])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), accent_blue),
            ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8)
        ]))
        matchup_elements.append(header_table)
        
        table_data = [[
            make_cell_p("Matchup Breakdown", text_white, is_bold=True), make_cell_p("S", text_white, is_bold=True),
            make_cell_p("Yds/G", text_white, is_bold=True), make_cell_p("YPP", text_white, is_bold=True),
            make_cell_p("PassG", text_white, is_bold=True), make_cell_p("PassA", text_white, is_bold=True),
            make_cell_p("RushG", text_white, is_bold=True), make_cell_p("RushA", text_white, is_bold=True),
            make_cell_p("PPG", text_white, is_bold=True), make_cell_p("3rd%", text_white, is_bold=True),
            make_cell_p("RZ%", text_white, is_bold=True)
        ]]
        
        def get_team_metrics(team_name):
            try:
                ts = stats_lookup.loc[team_name]
                return {
                    'O_YDS': ts.get('Off_Yds_PG','--'), 'O_YPP': ts.get('Off_YPP','--'),
                    'O_PAS': ts.get('Off_Pass_PG','--'), 'O_PAA': ts.get('Off_Pass_Att','--'),
                    'O_RUS': ts.get('Off_Rush_PG','--'), 'O_RUA': ts.get('Off_Rush_Att','--'),
                    'O_PPD': ts.get('Off_PPG','--'), 'O_3RD': ts.get('Off_3rd_%','--'), 'O_RZ': ts.get('Off_RZ_%','--'),
                    'D_YDS': ts.get('Def_Yds_PG','--'), 'D_YPP': ts.get('Def_YPP','--'),
                    'D_PAS': ts.get('Def_Pass_PG','--'), 'D_PAA': ts.get('Def_Pass_Att','--'),
                    'D_RUS': ts.get('Def_Rush_PG','--'), 'D_RUA': ts.get('Def_Rush_Att','--'),
                    'D_PPD': ts.get('Def_PPG','--'), 'D_3RD': ts.get('Def_3rd_%','--'), 'D_RZ': ts.get('Def_RZ_%','--')
                }
            except KeyError:
                return {k: '--' for k in ['O_YDS','O_YPP','O_PAS','O_PAA','O_RUS','O_RUA','O_PPD','O_3RD','O_RZ',
                                         'D_YDS','D_YPP','D_PAS','D_PAA','D_RUS','D_RUA','D_PPD','D_3RD','D_RZ']}

        away_m = get_team_metrics(away)
        home_m = get_team_metrics(home)

        def color_stat(val, key, side):
            if val == '--' or val is None:
                return make_cell_p('--')
            try:
                clean_val = float(str(val).replace('%', ''))
                base = national_baselines[key]
                if side == 'O':
                    if clean_val > base: return make_cell_p(str(val), color_green)
                    elif clean_val < base: return make_cell_p(str(val), color_red)
                else: 
                    if clean_val < base: return make_cell_p(str(val), color_green)
                    elif clean_val > base: return make_cell_p(str(val), color_red)
            except ValueError:
                pass
            return make_cell_p(str(val), text_white)

        table_data.append([make_cell_p(f"{away} Offense", team_cyan, True), make_cell_p("O"), color_stat(away_m['O_YDS'], 'YDS', 'O'), color_stat(away_m['O_YPP'], 'YPP', 'O'), color_stat(away_m['O_PAS'], 'PAS', 'O'), color_stat(away_m['O_PAA'], 'PAA', 'O'), color_stat(away_m['O_RUS'], 'RUS', 'O'), color_stat(away_m['O_RUA'], 'RUA', 'O'), color_stat(away_m['O_PPD'], 'PPG', 'O'), color_stat(away_m['O_3RD'], '3RD', 'O'), color_stat(away_m['O_RZ'], 'RZ', 'O')])
        table_data.append([make_cell_p(f"vs. {home} Defense", team_cyan, True), make_cell_p("D"), color_stat(home_m['D_YDS'], 'YDS', 'D'), color_stat(home_m['D_YPP'], 'YPP', 'D'), color_stat(home_m['D_PAS'], 'PAS', 'D'), color_stat(home_m['D_PAA'], 'PAA', 'D'), color_stat(home_m['D_RUS'], 'RUS', 'D'), color_stat(home_m['D_RUA'], 'RUA', 'D'), color_stat(home_m['D_PPD'], 'PPG', 'D'), color_stat(home_m['D_3RD'], '3RD', 'D'), color_stat(home_m['D_RZ'], 'RZ', 'D')])
        table_data.append([make_cell_p(f"{home} Offense", team_cyan, True), make_cell_p("O"), color_stat(home_m['O_YDS'], 'YDS', 'O'), color_stat(home_m['O_YPP'], 'YPP', 'O'), color_stat(home_m['O_PAS'], 'PAS', 'O'), color_stat(home_m['O_PAA'], 'PAA', 'O'), color_stat(home_m['O_RUS'], 'RUS', 'O'), color_stat(home_m['O_RUA'], 'RUA', 'O'), color_stat(home_m['O_PPD'], 'PPG', 'O'), color_stat(home_m['O_3RD'], '3RD', 'O'), color_stat(home_m['O_RZ'], 'RZ', 'O')])
        table_data.append([make_cell_p(f"vs. {away} Defense", team_cyan, True), make_cell_p("D"), color_stat(away_m['D_YDS'], 'YDS', 'D'), color_stat(away_m['D_YPP'], 'YPP', 'D'), color_stat(away_m['D_PAS'], 'PAS', 'D'), color_stat(away_m['D_PAA'], 'PAA', 'D'), color_stat(away_m['D_RUS'], 'RUS', 'D'), color_stat(away_m['D_RUA'], 'RUA', 'D'), color_stat(away_m['D_PPD'], 'PPG', 'D'), color_stat(away_m['D_3RD'], '3RD', 'D'), color_stat(away_m['D_RZ'], 'RZ', 'D')])

        metrics_table = Table(table_data, colWidths=col_widths)
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), card_bg),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#2D2D2D')),
            ('LINEBELOW', (0,1), (-1,1), 0.5, colors.HexColor('#2D2D2D')),
            ('LINEBELOW', (0,2), (-1,2), 1.5, colors.HexColor('#444444')), 
            ('LINEBELOW', (0,3), (-1,3), 0.5, colors.HexColor('#2D2D2D')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        
        matchup_elements.append(metrics_table)
        matchup_elements.append(Spacer(1, 14))
        story.append(KeepTogether(matchup_elements))
        
    def draw_background(canvas, document):
        canvas.saveState()
        canvas.setFillColor(bg_dark)
        p_width, p_height = document.pagesize
        canvas.rect(0, 0, p_width, p_height, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)

def main():
    print("Loading schedule file coordinates...")
    schedule_df = fetch_live_cfb_schedule()
    if schedule_df.empty:
        print("Schedule matrix empty.")
        return
        
    print("Pulling global on-field matrix layers...")
    stats_lookup = fetch_all_teamrankings_stats()
    if stats_lookup is None or stats_lookup.empty:
        print("Could not load stats data.")
        return
        
    stats_lookup.set_index('Clean_Name', inplace=True)
    
    print("Building full weekly PDF document summary report...")
    generate_pdf_report(schedule_df, stats_lookup)
    print("Success! Generated layout report at: 'generated/cfb_matrices_outlook.pdf'")

if __name__ == "__main__":
    main()

# ==========================================
# PART 4: PDF DOCUMENT GENERATOR END
# ==========================================
