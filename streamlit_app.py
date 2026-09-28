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
        
        /* F1 Pulsing Telemetry Animation */
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

# --- 2. ADVANCED CRICKET PARSER ---
@st.cache_data
def robust_pdf_parser(uploaded_file):
    ball_events = []
    current_over = 0.0
    
    # 360-degree mapping for True Wagon Wheel
    zone_mapping = {
        "cover": {"name": "Cover", "angle": 300}, 
        "extra cover": {"name": "Extra Cover", "angle": 315}, 
        "point": {"name": "Point", "angle": 270}, 
        "backward point": {"name": "Point", "angle": 250},
        "third man": {"name": "Third Man", "angle": 225}, 
        "fine leg": {"name": "Fine Leg", "angle": 135}, 
        "square leg": {"name": "Square Leg", "angle": 90}, 
        "mid-wicket": {"name": "Mid-Wicket", "angle": 60}, 
        "midwicket": {"name": "Mid-Wicket", "angle": 60}, 
        "mid-on": {"name": "Mid-On", "angle": 30}, 
        "mid-off": {"name": "Mid-Off", "angle": 330}, 
        "long-on": {"name": "Long-On", "angle": 15},
        "long-off": {"name": "Long-Off", "angle": 345}, 
        "straight": {"name": "Straight", "angle": 0}
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
                    bowler, batter, desc = ball_match.groups()
                    desc_lower = desc.lower()
                    
                    runs, is_four, is_six, is_wicket, is_extra, is_dot = 0, 0, 0, 0, 0, 0
                    zone, angle = "Unknown", None

                    for key, mapped_data in zone_mapping.items():
                        if key in desc_lower:
                            zone = mapped_data["name"]
                            angle = mapped_data["angle"]
                            break

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
                        if run_match: 
                            runs = int(run_match.group(1))
                            
                    # Calculate Dot Balls
                    if runs == 0 and not is_extra and not is_wicket:
                        is_dot = 1

                    # Phase Calculation (Powerplay, Middle, Death)
                    phase = "Middle Overs (11-40)"
                    if current_over < 10.0:
                        phase = "Powerplay (1-10)"
                    elif current_over >= 40.0:
                        phase = "Death Overs (41-50)"

                    ball_events.append({
                        "over_exact": current_over,
                        "over_num": int(current_over) if current_over > 0 else 0,
                        "phase": phase,
                        "bowler": bowler.strip(),
                        "batter": batter.strip(),
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

# --- 3. DASHBOARD UI ---
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
        
        dot_pct = (df["dot"].sum() / len(df)) * 100
        c5.markdown(f'<div class="f1-card"><div class="f1-metric-title">Dot Ball %</div><div class="f1-metric-value">{dot_pct:.1f}%</div></div>', unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["📊 Advanced Scorecards", "📈 Match Visuals (Worm & Manhattan)", "🎡 Spatial Wagon Wheel", "👤 Player Profiles"])

        with tab1:
            st.subheader("🏏 Batting Analytics")
            batting = df.groupby("batter").agg(
                Runs=("runs", "sum"), Balls=("runs", "count"), Fours=("4s", "sum"), Sixes=("6s", "sum"), Dots=("dot", "sum")
            ).reset_index().sort_values(by="Runs", ascending=False)
            batting['Strike Rate'] = ((batting['Runs'] / batting['Balls']) * 100).round(2)
            batting['Boundary %'] = (((batting['Fours']*4 + batting['Sixes']*6) / batting['Runs']) * 100).round(1).fillna(0)
            batting['Dot %'] = ((batting['Dots'] / batting['Balls']) * 100).round(1)
            st.dataframe(batting[['batter', 'Runs', 'Balls', 'Strike Rate', 'Fours', 'Sixes', 'Boundary %', 'Dot %']], use_container_width=True, hide_index=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            st.subheader("🎯 Bowling Analytics")
            bowling = df.groupby("bowler").agg(
                Balls=("over_exact", "count"), Wickets=("wicket", "sum"), Conceded=("runs", "sum"), Dots=("dot", "sum")
            ).reset_index().sort_values(by="Wickets", ascending=False)
            bowling['Overs'] = (bowling['Balls'] // 6) + (bowling['Balls'] % 6) / 10
            bowling['Economy'] = (bowling['Conceded'] / (bowling['Balls'] / 6)).round(2)
            bowling['Strike Rate'] = (bowling['Balls'] / bowling['Wickets']).round(1).replace(float('inf'), '-')
            st.dataframe(bowling[['bowler', 'Overs', 'Conceded', 'Wickets', 'Economy', 'Strike Rate', 'Dots']], use_container_width=True, hide_index=True)

        with tab2:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("📈 The Worm (Cumulative Runs)")
                fig_worm = px.line(df, x="over_exact", y="cumulative_runs", template="plotly_dark", color_discrete_sequence=['#e10600'])
                wickets_df = df[df['wicket'] == 1]
                if not wickets_df.empty:
                    fig_worm.add_trace(go.Scatter(x=wickets_df['over_exact'], y=wickets_df['cumulative_runs'], mode='markers', marker=dict(color='white', size=10, symbol='x'), name='Fall of Wicket'))
                fig_worm.update_layout(xaxis_title="Overs", yaxis_title="Runs")
                st.plotly_chart(fig_worm, use_container_width=True)
                
            with col_b:
                st.subheader("🏙️ Manhattan (Runs per Over)")
                manhattan = df.groupby('over_num')['runs'].sum().reset_index()
                fig_man = px.bar(manhattan, x='over_num', y='runs', template="plotly_dark", color_discrete_sequence=['#e10600'])
                fig_man.update_layout(xaxis_title="Over", yaxis_title="Runs Scored")
                st.plotly_chart(fig_man, use_container_width=True)
                
            st.subheader("⏱️ Phase-wise Analysis")
            phase_stats = df.groupby("phase").agg(Runs=("runs", "sum"), Wickets=("wicket", "sum"), Balls=("runs", "count")).reset_index()
            phase_stats['Run Rate'] = (phase_stats['Runs'] / (phase_stats['Balls'] / 6)).round(2)
            fig_phase = px.bar(phase_stats, x="phase", y="Runs", text="Run Rate", template="plotly_dark", color_discrete_sequence=['#3182ce'], title="Runs by Match Phase (Text = Run Rate)")
            st.plotly_chart(fig_phase, use_container_width=True)

        with tab3:
            st.subheader("🎡 True Wagon Wheel (Boundary Tracking)")
            st.markdown("Visualizing the precise angles of 4s and 6s based on commentary zones.")
            boundaries_df = df[(df['4s'] == 1) | (df['6s'] == 1)].dropna(subset=['angle'])
            
            if not boundaries_df.empty:
                boundaries_df['Run Type'] = boundaries_df.apply(lambda x: 'SIX' if x['6s'] == 1 else 'FOUR', axis=1)
                
                fig_polar = px.scatter_polar(
                    boundaries_df, r="runs", theta="angle", color="Run Type",
                    color_discrete_map={'SIX': '#e10600', 'FOUR': '#f59e0b'},
                    hover_name="batter", hover_data=["bowler", "over_exact"],
                    template="plotly_dark", size="runs", size_max=15
                )
                fig_polar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=False, range=[0, 7]), 
                        angularaxis=dict(direction="clockwise", rotation=0, tickmode="array", tickvals=[0, 45, 90, 135, 180, 225, 270, 315], ticktext=["Straight", "Mid-Wicket", "Square Leg", "Fine Leg", "Keeper", "Third Man", "Point", "Cover"])
                    ), margin=dict(t=40, b=40, l=40, r=40)
                )
                st.plotly_chart(fig_polar, use_container_width=True)
            else:
                st.info("No spatial boundary data could be extracted for a Wagon Wheel.")

        with tab4:
            st.subheader("🔍 Deep-Dive Player Analytics")
            selected_player = st.selectbox("Select Batter or Bowler:", sorted(list(set(df["batter"]).union(set(df["bowler"])))))
            
            if selected_player:
                p_bat = df[df["batter"] == selected_player]
                if not p_bat.empty:
                    st.markdown(f"**{selected_player}'s Boundary Wagon Wheel**")
                    p_bdry = p_bat[(p_bat['4s'] == 1) | (p_bat['6s'] == 1)].dropna(subset=['angle'])
                    if not p_bdry.empty:
                        p_bdry['Run Type'] = p_bdry.apply(lambda x: 'SIX' if x['6s'] == 1 else 'FOUR', axis=1)
                        fig_p = px.scatter_polar(p_bdry, r="runs", theta="angle", color="Run Type", color_discrete_map={'SIX': '#e10600', 'FOUR': '#f59e0b'}, template="plotly_dark", size="runs", size_max=15)
                        fig_p.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 7]), angularaxis=dict(direction="clockwise", rotation=0, tickmode="array", tickvals=[0, 45, 90, 135, 180, 225, 270, 315], ticktext=["Straight", "Mid-Wicket", "Square Leg", "Fine Leg", "Keeper", "Third Man", "Point", "Cover"])))
                        st.plotly_chart(fig_p, use_container_width=True)
                    else:
                        st.write("No boundaries recorded to plot.")
                
                st.markdown("**Ball-by-Ball Match Log**")
                st.dataframe(df[(df["batter"] == selected_player) | (df["bowler"] == selected_player)][["over_exact", "phase", "description", "runs", "wicket", "dot"]].sort_values(by="over_exact"), use_container_width=True, hide_index=True)
