import re
import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- 1. CONFIGURATION & UI THEME ---
st.set_page_config(
    page_title="CRIC-F1 // Pro Analytics",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #0b0e14; color: #f1f5f9; font-family: 'Inter', 'Segoe UI', sans-serif; }
        .metric-box { background-color: #151b26; border: 1px solid #1f2937; padding: 15px; border-radius: 8px; text-align: center; }
        .metric-title { font-size: 12px; color: #9ca3af; text-transform: uppercase; letter-spacing: 1px; }
        .metric-value { font-size: 24px; font-weight: 800; color: #ffffff; }
        .section-card { background-color: #111827; border: 1px solid #1f2937; padding: 20px; border-radius: 12px; margin-bottom: 20px; }
        
        .part-container { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; font-size: 14px; }
        .part-bar-bg { width: 100%; height: 8px; background-color: #374151; border-radius: 4px; margin-bottom: 20px; display: flex; overflow: hidden; }
        .part-bar-left { height: 100%; background-color: #8b5cf6; } 
        .part-bar-right { height: 100%; background-color: #d1d5db; }
        
        .roster-header { padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 15px; font-size: 18px; }
        .roster-card { display: flex; align-items: center; padding: 12px; border-bottom: 1px solid #1f2937; transition: background-color 0.2s ease; }
        .roster-card:hover { background-color: #1f2937; }
        .roster-avatar { background-color: #374151; border-radius: 50%; width: 45px; height: 45px; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-size: 22px; }
        .roster-name { font-weight: bold; color: #ffffff; font-size: 15px; }
        .roster-role { font-size: 12px; color: #9ca3af; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 2. PARSER ENGINE (WITH STRICT CHRONOLOGICAL SORTING) ---
def clean_name(name):
    name = re.sub(r'\(.*?\)', '', str(name))
    clean = re.sub(r'[^A-Za-z\s\-]', '', name).strip()
    return clean if 2 < len(clean) < 25 else None

def process_lines(all_lines):
    match_title = "Match Overview"
    playing_xi, team_names = {}, []
    
    for line in all_lines[:15]:
        title_match = re.search(r"([A-Za-z\s]+)\s+vs\s+([A-Za-z\s]+),", line)
        if title_match:
            match_title = f"{title_match.group(1).strip()} vs {title_match.group(2).strip()}"
            break

    for line in all_lines:
        if "(Playing XI):" in line:
            parts = line.split("(Playing XI):")
            team_name = parts[0].strip()
            if team_name not in team_names: team_names.append(team_name)
            for p in parts[1].split(","):
                c_name = clean_name(p)
                if c_name: playing_xi[c_name] = team_name
    if not team_names: team_names = ["Team A", "Team B"]

    raw_ball_events = []
    current_over = -1.0
    last_over = -1.0
    current_inning_id = 1
    
    zone_mapping = {
        "extra cover": {"name": "Extra Cover", "angle": 315}, "cover": {"name": "Cover", "angle": 300}, 
        "backward point": {"name": "Point", "angle": 250}, "point": {"name": "Point", "angle": 270}, 
        "third man": {"name": "Third Man", "angle": 225}, "fine leg": {"name": "Fine Leg", "angle": 135}, 
        "square leg": {"name": "Square Leg", "angle": 90}, "mid-wicket": {"name": "Mid-Wicket", "angle": 60}, 
        "midwicket": {"name": "Mid-Wicket", "angle": 60}, "mid-on": {"name": "Mid-On", "angle": 30}, 
        "long-on": {"name": "Long-On", "angle": 15}, "straight": {"name": "Straight", "angle": 0},
        "mid-off": {"name": "Mid-Off", "angle": 330}, "long-off": {"name": "Long-Off", "angle": 345}
    }

    for line in all_lines:
        over_match = re.match(r"^(\d{1,2}\.\d{1,2})$", line)
        if over_match:
            new_over = float(over_match.group(1))
            if last_over != -1.0 and new_over > last_over + 10.0:
                current_inning_id += 1
            current_over = new_over
            last_over = new_over
            continue
            
        ball_match = re.search(r"^([A-Z][A-Za-z\s\.\-\']+)\s+to\s+([A-Z][A-Za-z\s\.\-\']+),\s+(.*)", line)
        if ball_match:
            raw_bowler, raw_batter, desc = ball_match.groups()
            outcome_segment = desc.lower().split(',')[0].strip()
            
            valid_outcomes = ['run', 'runs', 'four', 'six', 'maximum', 'out', 'wide', 'no ball', 'bye', 'byes']
            if not any(k in outcome_segment for k in valid_outcomes):
                continue
                
            bowler, batter = clean_name(raw_bowler), clean_name(raw_batter)
            if not bowler or not batter: continue
            
            runs, is_four, is_six, is_wicket = 0, 0, 0, 0
            is_wd, is_nb, is_b, is_lb = 0, 0, 0, 0
            zone, angle, dismissal_desc = "Unknown", None, "Not Out"

            for key, mapped_data in zone_mapping.items():
                if key in desc.lower():
                    zone, angle = mapped_data["name"], mapped_data["angle"]
                    break

            run_match = re.search(r"(\d+)\s+run", outcome_segment)
            if run_match: runs = int(run_match.group(1))
                
            if "four" in outcome_segment or "4 run" in outcome_segment: is_four, runs = 1, 4
            elif "six" in outcome_segment or "6 run" in outcome_segment or "maximum" in outcome_segment: is_six, runs = 1, 6
            
            if "wide" in outcome_segment: is_wd = runs if runs > 0 else 1; runs = is_wd
            elif "no ball" in outcome_segment: is_nb = 1; runs = runs + 1 if runs > 0 else 1
            elif "leg bye" in outcome_segment: is_lb = runs if runs > 0 else 1; runs = is_lb
            elif "bye" in outcome_segment and "leg" not in outcome_segment: is_b = runs if runs > 0 else 1; runs = is_b
            
            if "out" in outcome_segment or "thats out" in outcome_segment.replace("'", ""): 
                is_wicket = 1
                try:
                    dismissal_desc = desc.split(',')[1].split('!!')[0].strip().replace("out ", "") + f" b {bowler}"
                except:
                    dismissal_desc = f"b {bowler}"

            raw_ball_events.append({
                "inning_id": current_inning_id, "over_exact": current_over, "over_num": int(current_over) if current_over > 0 else 0,
                "bowler": bowler, "batter": batter, "runs": runs, "wicket": is_wicket, "dismissal": dismissal_desc,
                "is_wd": is_wd, "is_nb": is_nb, "is_b": is_b, "is_lb": is_lb,
                "4s": is_four, "6s": is_six, "zone": zone, "angle": angle
            })
            
    inning_teams = {}
    for inn in set([b['inning_id'] for b in raw_ball_events]):
        team_votes = {}
        for b in raw_ball_events:
            if b['inning_id'] == inn:
                t = playing_xi.get(b['batter'])
                if t: team_votes[t] = team_votes.get(t, 0) + 1
        
        if team_votes:
            inning_teams[inn] = max(team_votes, key=team_votes.get)
        else:
            idx = inn - 1
            inning_teams[inn] = team_names[idx] if idx < len(team_names) else f"Team {inn}"

    ball_events = []
    for b in raw_ball_events:
        b['team'] = inning_teams[b['inning_id']]
        ball_events.append(b)
                    
    df = pd.DataFrame(ball_events)
    if not df.empty:
        # FIX: Sort ascending to ensure true chronological order per team innings
        df = df.sort_values(['team', 'over_exact'], ascending=[True, True]).reset_index(drop=True)
    return df, match_title, playing_xi, team_names

@st.cache_data
def parse_pdf(uploaded_file):
    all_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text: all_lines.extend([line.strip() for line in text.split("\n") if line.strip()])
    return process_lines(all_lines)

@st.cache_data
def parse_url(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return pd.DataFrame(), "Failed to fetch URL", {}, []
    soup = BeautifulSoup(resp.content, 'html.parser')
    all_lines = [el.text.strip() for el in soup.find_all(True) if el.text.strip()]
    return process_lines(all_lines)

def calculate_partnerships(df):
    partnerships = []
    for team in df['team'].unique():
        team_df = df[df['team'] == team].copy()
        team_df['part_id'] = team_df['wicket'].shift().fillna(0).cumsum()
        
        for pid, group in team_df.groupby('part_id'):
            batters = group['batter'].unique()
            if len(batters) > 2:
                batters = group.groupby('batter')['runs'].sum().nlargest(2).index.tolist()
            
            b1 = batters[0] if len(batters) > 0 else "Unknown"
            b2 = batters[1] if len(batters) > 1 else ""
            
            b1_r = group[(group['batter'] == b1) & (group['is_wd']==0) & (group['is_nb']==0) & (group['is_lb']==0) & (group['is_b']==0)]['runs'].sum()
            b1_b = len(group[(group['batter'] == b1) & (group['is_wd']==0)])
            b2_r = group[(group['batter'] == b2) & (group['is_wd']==0) & (group['is_nb']==0) & (group['is_lb']==0) & (group['is_b']==0)]['runs'].sum() if b2 else 0
            b2_b = len(group[(group['batter'] == b2) & (group['is_wd']==0)]) if b2 else 0
            
            partnerships.append({
                'team': team, 'total_runs': group['runs'].sum(), 'total_balls': len(group[group['is_wd']==0]),
                'b1': b1, 'b1_runs': b1_r, 'b1_balls': b1_b,
                'b2': b2, 'b2_runs': b2_r, 'b2_balls': b2_b
            })
    return pd.DataFrame(partnerships)

# --- 3. CHART GENERATORS ---
def draw_manhattan_with_wickets(df):
    manhattan = df.groupby(['over_num', 'team']).agg(runs=('runs', 'sum'), wickets=('wicket', 'sum')).reset_index()
    fig = px.bar(manhattan, x='over_num', y='runs', color='team', barmode='group', template="plotly_dark", color_discrete_sequence=['#9d174d', '#1e3a8a'])
    
    wickets_df = manhattan[manhattan['wickets'] > 0]
    if not wickets_df.empty:
        fig.add_trace(go.Scatter(
            x=wickets_df['over_num'], y=wickets_df['runs'] + 0.8,
            mode='markers+text', text='W', textfont=dict(color='white', size=10, weight='bold'),
            marker=dict(color='#dc2626', size=16, symbol='circle'), name='Wicket', showlegend=False
        ))
        
    fig.update_layout(xaxis_title="Overs", yaxis_title="Runs", plot_bgcolor='#111827', paper_bgcolor='#111827', margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def draw_zone_wagon_wheel(df):
    zone_data = df[df['zone'] != 'Unknown'].groupby(['zone', 'angle'])['runs'].sum().reset_index()
    fig = go.Figure()
    
    fig.update_layout(
        polar=dict(
            bgcolor='#a3e635',
            radialaxis=dict(visible=False, range=[0, 10]),
            angularaxis=dict(direction="clockwise", rotation=0, showticklabels=False, showgrid=False)
        ),
        showlegend=False, template="plotly_dark", margin=dict(t=20, b=20, l=20, r=20), paper_bgcolor='#111827'
    )
    fig.add_trace(go.Scatterpolar(r=[0, 2, 0, 2], theta=[0, 180, 0, 0], mode='lines', line=dict(color='#d9f99d', width=4)))
    
    if not zone_data.empty:
        fig.add_trace(go.Scatterpolar(
            r=[6] * len(zone_data), theta=zone_data['angle'], mode='markers+text',
            marker=dict(color='white', size=35, opacity=0.9),
            text=zone_data['runs'], textfont=dict(color='#111827', size=14, weight='bold'), hoverinfo="text", hovertext=zone_data['zone']
        ))
    return fig

# --- 4. DASHBOARD UI ---
st.sidebar.markdown("### 📥 INGEST MATCH DATA")
uploaded_pdf = st.sidebar.file_uploader("Upload Match PDF", type=["pdf"])
match_url = st.sidebar.text_input("Or Paste Cricbuzz URL:")

df, match_title, playing_xi, team_names = pd.DataFrame(), "", {}, []

if uploaded_pdf is not None:
    df, match_title, playing_xi, team_names = parse_pdf(uploaded_pdf)
elif match_url:
    with st.spinner("SCRAPING MATCH URL..."):
        df, match_title, playing_xi, team_names = parse_url(match_url)

if not df.empty:
    st.markdown(f"### {match_title}")
    
    teams = sorted(df['team'].unique().tolist())
    view_team = st.radio("Select View", ["Match Overview (Both)"] + teams, horizontal=True)
    display_df = df if view_team == "Match Overview (Both)" else df[df['team'] == view_team]
    
    col1, col2, col3, col4 = st.columns(4)
    total_r = display_df["runs"].sum()
    total_b = len(display_df[display_df["is_wd"]==0])
    col1.markdown(f'<div class="metric-box"><div class="metric-title">Score</div><div class="metric-value">{total_r}/{display_df["wicket"].sum()}</div></div>', unsafe_allow_html=True)
    col2.markdown(f'<div class="metric-box"><div class="metric-title">Overs</div><div class="metric-value">{(total_b // 6) + (total_b % 6)/10}</div></div>', unsafe_allow_html=True)
    col3.markdown(f'<div class="metric-box"><div class="metric-title">Run Rate</div><div class="metric-value">{((total_r / (total_b / 6)) if total_b > 0 else 0):.2f}</div></div>', unsafe_allow_html=True)
    col4.markdown(f'<div class="metric-box"><div class="metric-title">Boundaries</div><div class="metric-value">{display_df[display_df["4s"]==1].shape[0]} <span style="font-size:14px;color:#9ca3af;">(4s)</span> | {display_df[display_df["6s"]==1].shape[0]} <span style="font-size:14px;color:#9ca3af;">(6s)</span></div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    tab_scorecard, tab_dash, tab_squad = st.tabs(["📝 Match Scorecard", "📊 Pit-Wall Analytics", "👥 Squads & Playing XI"])

    with tab_scorecard:
        if view_team == "Match Overview (Both)":
            st.warning("Select a specific Team from the radio buttons above to view the detailed scorecard.")
        else:
            st.markdown(f'<div class="section-card"><h4 style="color:#10b981;">{view_team} Innings</h4>', unsafe_allow_html=True)
            
            batters_df = display_df.copy()
            batters_df['bat_runs'] = batters_df.apply(lambda x: 0 if x['is_wd'] or x['is_lb'] or x['is_b'] else (x['runs'] - x['is_nb'] if x['is_nb'] else x['runs']), axis=1)
            batters_df['bat_balls'] = batters_df.apply(lambda x: 0 if x['is_wd'] else 1, axis=1)
            
            batting_stats = batters_df.groupby("batter").agg(
                Runs=("bat_runs", "sum"), Balls=("bat_balls", "sum"), Fours=("4s", "sum"), Sixes=("6s", "sum"), Dismissal=("dismissal", "last")
            ).reset_index()
            
            batting_stats['SR'] = ((batting_stats['Runs'] / batting_stats['Balls']) * 100).round(2).fillna(0)
            batting_stats = batting_stats[['batter', 'Dismissal', 'Runs', 'Balls', 'Fours', 'Sixes', 'SR']]
            batting_stats.columns = ['Batter', ' ', 'R', 'B', '4s', '6s', 'SR']
            st.dataframe(batting_stats, use_container_width=True, hide_index=True)
            
            wides = display_df['is_wd'].sum()
            no_balls = display_df['is_nb'].sum()
            leg_byes = display_df['is_lb'].sum()
            byes = display_df['is_b'].sum()
            total_extras = wides + no_balls + leg_byes + byes
            
            st.markdown(f"**Extras:** {total_extras} (b {byes}, lb {leg_byes}, w {wides}, nb {no_balls})")
            st.markdown(f"**Total:** {total_r}-{display_df['wicket'].sum()} ({(total_b // 6)}.{total_b % 6} Overs)")
            
            if playing_xi:
                team_roster = [p for p, t in playing_xi.items() if t == view_team]
                batted_players = batting_stats['Batter'].tolist()
                did_not_bat = [p for p in team_roster if p not in batted_players]
                if did_not_bat:
                    st.markdown(f"**Did not Bat:** {', '.join(did_not_bat)}")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f'<h4>Bowling</h4>', unsafe_allow_html=True)

            overs_grouped = display_df.groupby(['bowler', 'over_num'])['runs'].sum().reset_index()
            maidens_calc = overs_grouped[overs_grouped['runs'] == 0].groupby('bowler').size().reset_index(name='M')
            
            bowling_stats = display_df.groupby("bowler").agg(
                Total_Balls=("is_wd", lambda x: (x==0).sum()), 
                R=("runs", "sum"), W=("wicket", "sum"), NB=("is_nb", "sum"), WD=("is_wd", "sum")
            ).reset_index()
            
            bowling_stats = pd.merge(bowling_stats, maidens_calc, on='bowler', how='left').fillna(0)
            bowling_stats['O'] = (bowling_stats['Total_Balls'] // 6).astype(str) + "." + (bowling_stats['Total_Balls'] % 6).astype(str)
            bowling_stats['ECO'] = (bowling_stats['R'] / (bowling_stats['Total_Balls'] / 6)).round(2)
            bowling_stats = bowling_stats[['bowler', 'O', 'M', 'R', 'W', 'NB', 'WD', 'ECO']]
            bowling_stats.columns = ['Bowler', 'O', 'M', 'R', 'W', 'NB', 'WD', 'ECO']
            
            st.dataframe(bowling_stats, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with tab_dash:
        c_left, c_right = st.columns([2, 1])
        with c_left:
            st.markdown('<div class="section-card"><h4>Manhattan / Worm</h4>', unsafe_allow_html=True)
            tabs = st.tabs(["Manhattan", "Worm"])
            with tabs[0]: st.plotly_chart(draw_manhattan_with_wickets(display_df), use_container_width=True)
            with tabs[1]:
                worm = display_df.groupby(['over_exact', 'team'])['runs'].sum().groupby(level=1).cumsum().reset_index()
                fig_worm = px.line(worm, x='over_exact', y='runs', color='team', template="plotly_dark", color_discrete_sequence=['#9d174d', '#1e3a8a'])
                fig_worm.update_layout(plot_bgcolor='#111827', paper_bgcolor='#111827', xaxis_title="Overs", yaxis_title="Cumulative Runs")
                st.plotly_chart(fig_worm, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with c_right:
            st.markdown('<div class="section-card"><h4>Wagon Wheel</h4>', unsafe_allow_html=True)
            st.plotly_chart(draw_zone_wagon_wheel(display_df), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-card"><h4>Partnerships</h4>', unsafe_allow_html=True)
        part_df = calculate_partnerships(display_df)
        
        if not part_df.empty:
            for idx, row in part_df.iterrows():
                b1_pct = (row['b1_runs'] / row['total_runs'] * 100) if row['total_runs'] > 0 else 50
                b2_pct = (row['b2_runs'] / row['total_runs'] * 100) if row['total_runs'] > 0 else 50
                st.markdown(f"""
                <div style="margin-bottom: 25px;">
                    <div style="text-align: center; font-weight: bold; margin-bottom: 5px;">{row['total_runs']} ({row['total_balls']})</div>
                    <div class="part-container">
                        <div><b>{row['b1']}</b> <br> {row['b1_runs']} ({row['b1_balls']})</div>
                        <div style="text-align: right;"><b>{row['b2']}</b> <br> {row['b2_runs']} ({row['b2_balls']})</div>
                    </div>
                    <div class="part-bar-bg"><div class="part-bar-left" style="width: {b1_pct}%;"></div><div class="part-bar-right" style="width: {b2_pct}%;"></div></div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_squad:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        if len(team_names) >= 2:
            t1, t2 = team_names[0], team_names[1]
            t1_players = [p for p, t in playing_xi.items() if t == t1]
            t2_players = [p for p, t in playing_xi.items() if t == t2]
            col_t1, col_t2 = st.columns(2)
            
            with col_t1:
                st.markdown(f'<div class="roster-header" style="background-color: rgba(139, 92, 246, 0.1); color: #8b5cf6; border: 1px solid #8b5cf6;">{t1}</div>', unsafe_allow_html=True)
                for p in t1_players:
                    st.markdown(f'<div class="roster-card"><div class="roster-avatar">👤</div><div><div class="roster-name">{p}</div><div class="roster-role">Player</div></div></div>', unsafe_allow_html=True)
                    
            with col_t2:
                st.markdown(f'<div class="roster-header" style="background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid #3b82f6;">{t2}</div>', unsafe_allow_html=True)
                for p in t2_players:
                    st.markdown(f'<div class="roster-card"><div class="roster-avatar">👤</div><div><div class="roster-name">{p}</div><div class="roster-role">Player</div></div></div>', unsafe_allow_html=True)
        else:
            st.info("Playing XI data could not be extracted from this source.")
        st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("Awaiting Match PDF upload or URL input...")
