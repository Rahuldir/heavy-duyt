import re
import pandas as pd
import pdfplumber
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- 1. CONFIGURATION & F1 VISUAL THEME ---
st.set_page_config(
    page_title="CRIC-F1 // Pit-Wall Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #050505; color: #f1f5f9; font-family: 'Segoe UI', Roboto, sans-serif; }
        [data-testid="stSidebar"] { background-color: #0f1115; border-right: 1px solid #2d3748; }
        .f1-card { background: linear-gradient(135deg, #15181e 0%, #0d0f13 100%); border: 1px solid #2d3748; border-left: 4px solid #e10600; padding: 16px; border-radius: 8px; margin-bottom: 12px; }
        .f1-metric-title { font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #8792a3; font-weight: 800; }
        .f1-metric-value { font-size: 26px; font-weight: 900; color: #ffffff; font-family: 'Courier New', monospace; }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(225, 6, 0, 0.7); } 70% { box-shadow: 0 0 0 10px rgba(225, 6, 0, 0); } 100% { box-shadow: 0 0 0 0 rgba(225, 6, 0, 0); } }
        .live-dot { height: 12px; width: 12px; background-color: #e10600; border-radius: 50%; display: inline-block; animation: pulse 1.5s infinite; margin-right: 8px; }
        h1, h2, h3 { font-weight: 900; letter-spacing: -0.5px; color: #ffffff; text-transform: uppercase; }
        .stDataFrame { border: 1px solid #2d3748; border-radius: 8px; }
        div.row-widget.stRadio > div { flex-direction: row; background-color: #15181e; padding: 10px; border-radius: 8px; border: 1px solid #2d3748;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 2. STRICT 2-PASS PARSER (ACCURATE WICKETS & ZONES) ---
def clean_name(name):
    name = re.sub(r'\(.*?\)', '', str(name))
    clean = re.sub(r'[^A-Za-z\s\-]', '', name).strip()
    return clean if 2 < len(clean) < 25 else None

@st.cache_data
def robust_pdf_parser(uploaded_file):
    all_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend([line.strip() for line in text.split("\n") if line.strip()])

    # PASS 1: Extract Playing XIs
    playing_xi, team_names = {}, []
    match_title = "Match Overview"
    
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

    # PASS 2: Strict Ball Extraction
    ball_events = []
    current_over = -1.0
    fallback_innings_counter = 1
    
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
            if current_over != -1.0 and new_over > current_over + 10.0:
                fallback_innings_counter += 1
            current_over = new_over
            continue
            
        ball_match = re.search(r"^([^,]+)\s+to\s+([^,]+),\s+(.*)", line)
        if ball_match:
            raw_bowler, raw_batter, desc = ball_match.groups()
            desc_lower = desc.lower()
            
            # Isolate the exact outcome (e.g., "1 run", "FOUR", "out") which is strictly before the next comma
            outcome_segment = desc_lower.split(',')[0].strip()
            
            if not any(k in outcome_segment for k in ['run', 'four', 'six', 'maximum', 'out', 'wide', 'no ball', 'bye']):
                continue
                
            bowler, batter = clean_name(raw_bowler), clean_name(raw_batter)
            if not bowler or not batter: continue
            
            team_batting = playing_xi.get(batter, f"Innings {fallback_innings_counter}")
            runs, is_four, is_six, is_wicket, is_extra, is_dot = 0, 0, 0, 0, 0, 0
            zone, angle = "Unknown", None

            # Check the ENTIRE description for the wagon wheel zone
            for key, mapped_data in zone_mapping.items():
                if key in desc_lower:
                    zone, angle = mapped_data["name"], mapped_data["angle"]
                    break

            # Process Strict Outcomes
            if "four" in outcome_segment or "4 run" in outcome_segment: is_four, runs = 1, 4
            elif "six" in outcome_segment or "6 run" in outcome_segment or "maximum" in outcome_segment: is_six, runs = 1, 6
            elif "wide" in outcome_segment or "no ball" in outcome_segment or "bye" in outcome_segment: is_extra, runs = 1, 1
            
            # Exact wicket detection
            if "out" in outcome_segment or "thats out" in outcome_segment.replace("'", ""): is_wicket = 1

            if not is_four and not is_six and not is_extra:
                run_match = re.search(r"(\d+)\s+run", outcome_segment)
                if run_match: runs = int(run_match.group(1))
                    
            if "no run" in outcome_segment: is_dot = 1

            ball_events.append({
                "team": team_batting, "over_exact": current_over, "over_num": int(current_over) if current_over > 0 else 0,
                "bowler": bowler, "batter": batter, "runs": runs,
                "4s": is_four, "6s": is_six, "dot": is_dot, "wicket": is_wicket, "extra": is_extra,
                "zone": zone, "angle": angle, "description": desc.strip(),
            })
                    
    df = pd.DataFrame(ball_events)
    if not df.empty:
        df = df.sort_values(['team', 'over_exact']).reset_index(drop=True)
        df['team_cumulative_runs'] = df.groupby('team')['runs'].cumsum()
    return df, match_title


# --- 3. WAGON WHEEL & CHART GENERATORS ---
def draw_wagon_wheel(df_boundaries, title):
    fig = go.Figure()
    for idx, row in df_boundaries.iterrows():
        run_val, angle = row['runs'], row['angle']
        color = '#e10600' if run_val == 6 else '#f59e0b'
        name = 'SIX' if run_val == 6 else 'FOUR'
        
        fig.add_trace(go.Scatterpolar(
            r=[0, run_val], theta=[angle, angle], mode='lines+markers',
            line=dict(color=color, width=3, dash='solid'), marker=dict(color=color, size=[0, 9], symbol='circle'),
            opacity=0.85, name=name, hoverinfo="text", text=[None, f"{row['batter']} hit {name} to {row['zone']}"]
        ))
        
    fig.update_layout(
        title=dict(text=title, font=dict(color="white", size=16)),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 6.5], showticklabels=False, gridcolor="#2d3748"), 
            angularaxis=dict(direction="clockwise", rotation=0, tickmode="array", tickvals=[0, 45, 90, 135, 180, 225, 270, 315], ticktext=["Straight", "Mid-Wicket", "Square Leg", "Fine Leg", "Keeper", "Third Man", "Point", "Cover"], gridcolor="#2d3748", linecolor="#2d3748"), bgcolor="#15181e"
        ), showlegend=False, template="plotly_dark", margin=dict(t=50, b=40, l=40, r=40), paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


# --- 4. DASHBOARD UI ---
st.sidebar.markdown("### 🛑 PIT-WALL CONTROL")
uploaded_pdf = st.sidebar.file_uploader("Upload Match PDF", type=["pdf"])
st.markdown('<h1><span class="live-dot"></span> CRIC-F1 // PIT-WALL ANALYTICS</h1>', unsafe_allow_html=True)

if uploaded_pdf is not None:
    with st.spinner("SYNCING TEAM ROSTERS & BALL DATA..."):
        df, match_title = robust_pdf_parser(uploaded_pdf)

    st.markdown(f"_{match_title} | Strict Outcome Verification Active._")
    st.markdown("---")

    if not df.empty:
        teams_list = df['team'].unique().tolist()
        selected_team = st.radio("Select Batting Team View:", teams_list + ["Compare Match Overview"], horizontal=True)
        
        display_df = df if selected_team == "Compare Match Overview" else df[df['team'] == selected_team].copy()

        total_runs, total_balls = display_df["runs"].sum(), len(display_df[display_df['extra'] == 0])
        current_rr = (total_runs / (total_balls / 6)) if total_balls > 0 else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(f'<div class="f1-card"><div class="f1-metric-title">Score</div><div class="f1-metric-value">{total_runs}/{display_df["wicket"].sum()}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="f1-card"><div class="f1-metric-title">Run Rate</div><div class="f1-metric-value">{current_rr:.2f}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="f1-card"><div class="f1-metric-title">Overs</div><div class="f1-metric-value">{(total_balls // 6) + (total_balls % 6)/10}</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="f1-card"><div class="f1-metric-title">Boundaries</div><div class="f1-metric-value">{display_df["4s"].sum()} <span style="font-size:14px;color:#8792a3;">(4s)</span> | {display_df["6s"].sum()} <span style="font-size:14px;color:#8792a3;">(6s)</span></div></div>', unsafe_allow_html=True)
        c5.markdown(f'<div class="f1-card"><div class="f1-metric-title">Dot Ball %</div><div class="f1-metric-value">{((display_df["dot"].sum() / len(display_df)) * 100) if len(display_df) > 0 else 0:.1f}%</div></div>', unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["📊 Full Scorecards", "🏙️ Manhattan & Wagon Wheel", "👤 Player Deep-Dive"])

        with tab1:
            if selected_team == "Compare Match Overview":
                st.warning("Please select a specific Team from the toggle above to view the detailed scorecard.")
            else:
                st.subheader(f"🏏 Batting Scorecard - {selected_team}")
                dismissed_batters = display_df[display_df['wicket'] == 1]['batter'].unique().tolist()
                
                batting = display_df.groupby("batter").agg(Runs=("runs", "sum"), Balls=("runs", "count"), Fours=("4s", "sum"), Sixes=("6s", "sum")).reset_index()
                batting['Status'] = batting['batter'].apply(lambda x: "Out" if x in dismissed_batters else "Not Out")
                batting['Strike Rate'] = ((batting['Runs'] / batting['Balls']) * 100).round(2)
                batting = batting.sort_values(by="Runs", ascending=False)
                st.dataframe(batting[['batter', 'Status', 'Runs', 'Balls', 'Fours', 'Sixes', 'Strike Rate']], use_container_width=True, hide_index=True)
                
                st.subheader("🎯 Bowling Scorecard")
                bowling = display_df.groupby("bowler").agg(Balls=("over_exact", "count"), Wickets=("wicket", "sum"), Conceded=("runs", "sum")).reset_index().sort_values(by="Wickets", ascending=False)
                bowling['Overs'] = (bowling['Balls'] // 6) + (bowling['Balls'] % 6) / 10
                bowling['Economy'] = (bowling['Conceded'] / (bowling['Balls'] / 6)).round(2)
                st.dataframe(bowling[['bowler', 'Overs', 'Conceded', 'Wickets', 'Economy']], use_container_width=True, hide_index=True)

        with tab2:
            col_m, col_w = st.columns(2)
            with col_m:
                st.subheader("🏙️ Manhattan (Runs per Over)")
                if selected_team == "Compare Match Overview":
                    manhattan = display_df.groupby(['over_num', 'team'])['runs'].sum().reset_index()
                    fig_man = px.bar(manhattan, x='over_num', y='runs', color='team', barmode='group', template="plotly_dark", color_discrete_sequence=['#e10600', '#3182ce'])
                else:
                    manhattan = display_df.groupby('over_num')['runs'].sum().reset_index()
                    fig_man = px.bar(manhattan, x='over_num', y='runs', template="plotly_dark", color_discrete_sequence=['#e10600'])
                fig_man.update_layout(xaxis_title="Over Number", yaxis_title="Runs Scored")
                st.plotly_chart(fig_man, use_container_width=True)
                
            with col_w:
                st.subheader("🎡 True Wagon Wheel (Flying Ropes)")
                boundaries_df = display_df[(display_df['4s'] == 1) | (display_df['6s'] == 1)].dropna(subset=['angle'])
                if not boundaries_df.empty:
                    fig_ww = draw_wagon_wheel(boundaries_df, f"Boundaries - {selected_team}")
                    st.plotly_chart(fig_ww, use_container_width=True)
                else:
                    st.info("No spatial boundary data detected for this view.")
                    
            st.markdown("---")
            st.subheader("🎯 Spatial Zone Analytics (Shot %)")
            col_pie1, col_pie2 = st.columns([1, 2])
            
            zone_data = display_df[display_df['zone'] != 'Unknown']['zone'].value_counts().reset_index()
            zone_data.columns = ['Zone', 'Shots Played']
            
            with col_pie1:
                st.dataframe(zone_data, use_container_width=True, hide_index=True)
            with col_pie2:
                if not zone_data.empty:
                    fig_pie = px.pie(zone_data, names='Zone', values='Shots Played', hole=0.5, template="plotly_dark", color_discrete_sequence=px.colors.sequential.Reds_r)
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No shot direction data available for pie chart.")

        with tab3:
            st.subheader("🔍 Player Telemetry & Wagon Wheel")
            valid_players = sorted(list(set(display_df["batter"]).union(set(display_df["bowler"]))))
            selected_player = st.selectbox("Select Player:", valid_players)
            
            if selected_player:
                p_bat = display_df[display_df["batter"] == selected_player]
                if not p_bat.empty:
                    p_bdry = p_bat[(p_bat['4s'] == 1) | (p_bat['6s'] == 1)].dropna(subset=['angle'])
                    if not p_bdry.empty:
                        fig_p_ww = draw_wagon_wheel(p_bdry, f"{selected_player}'s Boundary Ropes")
                        st.plotly_chart(fig_p_ww, use_container_width=True)
                
                player_logs = display_df[(display_df["batter"] == selected_player) | (display_df["bowler"] == selected_player)]
                player_logs_sorted = player_logs[["team", "over_exact", "description", "runs", "wicket"]].sort_values(by=["team", "over_exact"])
                st.dataframe(player_logs_sorted, use_container_width=True, hide_index=True)
