import re
import pandas as pd
import pdfplumber
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- 1. CONFIGURATION & F1 VISUAL THEME ---
st.set_page_config(
    page_title="CRIC-F1 // Advanced Cricket Analytics",
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
        .f1-metric-value { font-size: 28px; font-weight: 900; color: #ffffff; font-family: 'Courier New', monospace; }
        
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(225, 6, 0, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(225, 6, 0, 0); }
            100% { box-shadow: 0 0 0 0 rgba(225, 6, 0, 0); }
        }
        .live-dot {
            height: 12px; width: 12px; background-color: #e10600; border-radius: 50%; display: inline-block; animation: pulse 1.5s infinite; margin-right: 8px;
        }
        h1, h2, h3 { font-weight: 900; letter-spacing: -0.5px; color: #ffffff; text-transform: uppercase; }
        .stDataFrame { border: 1px solid #2d3748; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 2. ADVANCED CRICKET PARSER & NAME CLEANER ---
def clean_player_name(name):
    # Strip random punctuation and ensure it's a realistic name length
    name = re.sub(r'[^A-Za-z\s\-]', '', str(name)).strip()
    # Filter out weird commentary sentences that slipped through
    if len(name) > 22 or len(name) < 3 or " run" in name.lower() or " out" in name.lower():
        return None
    return name

@st.cache_data
def robust_pdf_parser(uploaded_file):
    ball_events = []
    current_over = 0.0
    
    # 360-degree mapping for True Wagon Wheel Angles
    zone_mapping = {
        "extra cover": {"name": "Extra Cover", "angle": 315}, 
        "cover": {"name": "Cover", "angle": 300}, 
        "backward point": {"name": "Point", "angle": 250},
        "point": {"name": "Point", "angle": 270}, 
        "third man": {"name": "Third Man", "angle": 225}, 
        "fine leg": {"name": "Fine Leg", "angle": 135}, 
        "square leg": {"name": "Square Leg", "angle": 90}, 
        "mid-wicket": {"name": "Mid-Wicket", "angle": 60}, 
        "midwicket": {"name": "Mid-Wicket", "angle": 60}, 
        "mid-on": {"name": "Mid-On", "angle": 30}, 
        "mid on": {"name": "Mid-On", "angle": 30}, 
        "long-on": {"name": "Long-On", "angle": 15},
        "long on": {"name": "Long-On", "angle": 15},
        "straight": {"name": "Straight", "angle": 0},
        "mid-off": {"name": "Mid-Off", "angle": 330}, 
        "mid off": {"name": "Mid-Off", "angle": 330},
        "long-off": {"name": "Long-Off", "angle": 345}, 
        "long off": {"name": "Long-Off", "angle": 345},
    }

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
                
            for line in text.split("\n"):
                line = line.strip()
                if not line: continue
                
                over_match = re.match(r"^(\d+\.\d+)$", line)
                if over_match:
                    current_over = float(over_match.group(1))
                    continue
                    
                ball_match = re.search(r"^([A-Za-z\s\.\-\']+)\s+to\s+([A-Za-z\s\.\-\']+),\s+(.*)", line)
                
                if ball_match:
                    raw_bowler, raw_batter, desc = ball_match.groups()
                    
                    bowler = clean_player_name(raw_bowler)
                    batter = clean_player_name(raw_batter)
                    
                    if not bowler or not batter: 
                        continue # Skip false positives
                        
                    desc_lower = desc.lower()
                    runs, is_four, is_six, is_wicket, is_extra, is_dot = 0, 0, 0, 0, 0, 0
                    zone, angle = "Unknown", None

                    # Find shot direction
                    for key, mapped_data in zone_mapping.items():
                        if key in desc_lower:
                            zone = mapped_data["name"]
                            angle = mapped_data["angle"]
                            break

                    # Event outcomes
                    if "4 run" in desc_lower or "four" in desc_lower:
                        is_four, runs = 1, 4
                    elif "6 run" in desc_lower or "six" in desc_lower or "maximum" in desc_lower:
                        is_six, runs = 1, 6
                    elif "wide" in desc_lower or "no ball" in desc_lower or "leg bye" in desc_lower:
                        is_extra, runs = 1, 1
                        
                    desc_start = " ".join(desc_lower.split()[:12])
                    if any(w in desc_start for w in ["out", "caught", "bowled", "lbw", "stumped", "run out"]):
                        is_wicket = 1

                    if not is_four and not is_six and not is_extra:
                        run_match = re.search(r"(\d+)\s+run", desc_lower)
                        if run_match: runs = int(run_match.group(1))
                            
                    if runs == 0 and not is_extra and not is_wicket:
                        is_dot = 1

                    phase = "Middle Overs (11-40)"
                    if current_over < 10.0: phase = "Powerplay (1-10)"
                    elif current_over >= 40.0: phase = "Death Overs (41-50)"

                    ball_events.append({
                        "over_exact": current_over,
                        "over_num": int(current_over) if current_over > 0 else 0,
                        "phase": phase,
                        "bowler": bowler,
                        "batter": batter,
                        "runs": runs,
                        "4s": is_four,
                        "6s": is_six,
                        "dot": is_dot,
                        "wicket": is_wicket,
                        "extra": is_extra,
                        "zone": zone,
                        "angle": angle,
                        "description": desc.strip(),
                    })
                    
    return pd.DataFrame(ball_events)

# --- 3. WAGON WHEEL GENERATOR ---
def draw_wagon_wheel(df_boundaries, title):
    fig = go.Figure()
    
    # Draw ropes from middle to boundary for each shot
    for idx, row in df_boundaries.iterrows():
        run_val = row['runs']
        angle = row['angle']
        color = '#e10600' if run_val == 6 else '#f59e0b'
        name = 'SIX' if run_val == 6 else 'FOUR'
        
        fig.add_trace(go.Scatterpolar(
            r=[0, run_val], # Line from center (0) to distance (4 or 6)
            theta=[angle, angle],
            mode='lines+markers',
            line=dict(color=color, width=3),
            marker=dict(color=color, size=[0, 8]), # Marker only at the end of the rope
            name=name,
            hoverinfo="text",
            text=[None, f"{row['batter']} hit {name} to {row['zone']}"]
        ))
        
    fig.update_layout(
        title=dict(text=title, font=dict(color="white", size=16)),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 6.5], showticklabels=False, gridcolor="#2d3748"), 
            angularaxis=dict(
                direction="clockwise", rotation=0, tickmode="array", 
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315], 
                ticktext=["Straight", "Mid-Wicket", "Square Leg", "Fine Leg", "Keeper", "Third Man", "Point", "Cover"],
                gridcolor="#2d3748", linecolor="#2d3748"
            ),
            bgcolor="#15181e"
        ), 
        showlegend=False, template="plotly_dark", margin=dict(t=50, b=40, l=40, r=40),
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


# --- 4. DASHBOARD UI ---
st.sidebar.markdown("### 🛑 MATCH CONTROL")
uploaded_pdf = st.sidebar.file_uploader("Upload Match PDF", type=["pdf"])

st.markdown('<h1><span class="live-dot"></span> CRIC-F1 // ADVANCED MATCH ANALYTICS</h1>', unsafe_allow_html=True)
st.markdown("_High-performance spatial tracking and deep cricket telemetry._")
st.markdown("---")

if uploaded_pdf is not None:
    with st.spinner("CALIBRATING SENSORS..."):
        df = robust_pdf_parser(uploaded_pdf)

    if not df.empty:
        df = df.sort_values('over_exact').reset_index(drop=True)
        df['cumulative_runs'] = df['runs'].cumsum()
        
        total_runs = df["runs"].sum()
        total_balls = len(df[df['extra'] == 0])
        current_rr = (total_runs / (total_balls / 6)) if total_balls > 0 else 0

        # Top Row Metrics
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(f'<div class="f1-card"><div class="f1-metric-title">Score</div><div class="f1-metric-value">{total_runs}/{df["wicket"].sum()}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="f1-card"><div class="f1-metric-title">Run Rate</div><div class="f1-metric-value">{current_rr:.2f}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="f1-card"><div class="f1-metric-title">Overs</div><div class="f1-metric-value">{(total_balls // 6) + (total_balls % 6)/10}</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="f1-card"><div class="f1-metric-title">Boundaries</div><div class="f1-metric-value">{df["4s"].sum()} <span style="font-size:14px;color:#8792a3;">(4s)</span> | {df["6s"].sum()} <span style="font-size:14px;color:#8792a3;">(6s)</span></div></div>', unsafe_allow_html=True)
        c5.markdown(f'<div class="f1-card"><div class="f1-metric-title">Dot Ball %</div><div class="f1-metric-value">{((df["dot"].sum() / len(df)) * 100):.1f}%</div></div>', unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["📊 Scorecards", "📈 Match Visuals", "👤 Player Deep-Dive"])

        with tab1:
            st.subheader("🏏 Batting Analytics")
            batting = df.groupby("batter").agg(
                Runs=("runs", "sum"), Balls=("runs", "count"), Fours=("4s", "sum"), Sixes=("6s", "sum"), Dots=("dot", "sum")
            ).reset_index().sort_values(by="Runs", ascending=False)
            batting['Strike Rate'] = ((batting['Runs'] / batting['Balls']) * 100).round(2)
            st.dataframe(batting[['batter', 'Runs', 'Balls', 'Strike Rate', 'Fours', 'Sixes', 'Dots']], use_container_width=True, hide_index=True)
            
            st.subheader("🎯 Bowling Analytics")
            bowling = df.groupby("bowler").agg(
                Balls=("over_exact", "count"), Wickets=("wicket", "sum"), Conceded=("runs", "sum"), Dots=("dot", "sum")
            ).reset_index().sort_values(by="Wickets", ascending=False)
            bowling['Overs'] = (bowling['Balls'] // 6) + (bowling['Balls'] % 6) / 10
            bowling['Economy'] = (bowling['Conceded'] / (bowling['Balls'] / 6)).round(2)
            st.dataframe(bowling[['bowler', 'Overs', 'Conceded', 'Wickets', 'Economy', 'Dots']], use_container_width=True, hide_index=True)

        with tab2:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("📈 The Worm (Cumulative Runs)")
                fig_worm = px.line(df, x="over_exact", y="cumulative_runs", template="plotly_dark", color_discrete_sequence=['#e10600'])
                st.plotly_chart(fig_worm, use_container_width=True)
                
            with col_b:
                st.subheader("🎡 True Wagon Wheel (Match)")
                boundaries_df = df[(df['4s'] == 1) | (df['6s'] == 1)].dropna(subset=['angle'])
                if not boundaries_df.empty:
                    fig_ww = draw_wagon_wheel(boundaries_df, "All Match Boundaries")
                    st.plotly_chart(fig_ww, use_container_width=True)
                else:
                    st.info("No spatial boundary data detected.")

        with tab3:
            st.subheader("🔍 Deep-Dive Player Analytics")
            
            # Clean list of Playing XI only
            valid_players = sorted(list(set(df["batter"]).union(set(df["bowler"]))))
            selected_player = st.selectbox("Select Player from Playing XI:", valid_players)
            
            if selected_player:
                p_bat = df[df["batter"] == selected_player]
                if not p_bat.empty:
                    p_bdry = p_bat[(p_bat['4s'] == 1) | (p_bat['6s'] == 1)].dropna(subset=['angle'])
                    if not p_bdry.empty:
                        fig_p_ww = draw_wagon_wheel(p_bdry, f"{selected_player}'s Boundary Ropes")
                        st.plotly_chart(fig_p_ww, use_container_width=True)
                    else:
                        st.write(f"No boundaries hit by {selected_player} to map.")
                
                st.markdown(f"**Ball-by-Ball Involvement ({selected_player})**")
                st.dataframe(df[(df["batter"] == selected_player) | (df["bowler"] == selected_player)][["over_exact", "phase", "description", "runs", "wicket", "dot"]].sort_values(by="over_exact"), use_container_width=True, hide_index=True)
