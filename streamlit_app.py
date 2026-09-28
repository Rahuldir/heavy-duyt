import re
import pandas as pd
import pdfplumber
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- 1. CONFIGURATION & F1 ANIMATED STYLING ---
st.set_page_config(
    page_title="CRIC-F1 // Advanced Telemetry",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for F1 styling and CSS Animations (Pulsing Live dots)
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
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 2. ADVANCED PARSER WITH 360-DEGREE SPATIAL MAPPING ---
@st.cache_data
def robust_pdf_parser(uploaded_file):
    ball_events = []
    current_over = 0.0
    
    # Map text zones to 360-degree angles for the True Wagon Wheel
    # 0 = Straight down ground, 90 = Square Leg, 180 = Fine Leg/Keeper, 270 = Point
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
                    
                    runs, is_four, is_six, is_wicket, is_extra = 0, 0, 0, 0, 0
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
                        if run_match: runs = int(run_match.group(1))

                    ball_events.append({
                        "over_exact": current_over,
                        "over_num": int(current_over) if current_over > 0 else 0,
                        "bowler": bowler.strip(),
                        "batter": batter.strip(),
                        "runs": runs,
                        "4s": is_four,
                        "6s": is_six,
                        "wicket": is_wicket,
                        "extra": is_extra,
                        "zone": zone,
                        "angle": angle,
                        "description": desc.strip(),
                    })
                    
    return pd.DataFrame(ball_events)

# --- 3. DASHBOARD UI & ANIMATED CHARTS ---
st.sidebar.markdown("### 🛑 PIT WALL // UPLOAD")
uploaded_pdf = st.sidebar.file_uploader("Ingest Match PDF", type=["pdf"])

st.markdown('<h1><span class="live-dot"></span> CRIC-F1 // LIVE TELEMETRY</h1>', unsafe_allow_html=True)
st.markdown("_High-performance spatial tracking and animated data pipelines._")
st.markdown("---")

if uploaded_pdf is not None:
    with st.spinner("CALIBRATING SENSORS..."):
        df = robust_pdf_parser(uploaded_pdf)

    if not df.empty:
        df = df.sort_values('over_exact').reset_index(drop=True)
        df['cumulative_runs'] = df['runs'].cumsum() # For the animated race trace

        # Top Row Telemetry
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(f'<div class="f1-card"><div class="f1-metric-title">Total Runs</div><div class="f1-metric-value">{df["runs"].sum()}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="f1-card"><div class="f1-metric-title">Wickets</div><div class="f1-metric-value">{df["wicket"].sum()}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="f1-card"><div class="f1-metric-title">Boundaries</div><div class="f1-metric-value">{df["4s"].sum() + df["6s"].sum()}</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="f1-card"><div class="f1-metric-title">Max Sector (Over)</div><div class="f1-metric-value">{df.groupby("over_num")["runs"].sum().max()}</div></div>', unsafe_allow_html=True)
        c5.markdown(f'<div class="f1-card"><div class="f1-metric-title">Balls Logged</div><div class="f1-metric-value">{len(df)}</div></div>', unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["🎡 Boundary Wagon Wheel", "📈 Animated Race Trace", "📊 Leaderboards"])

        with tab1:
            st.subheader("🏎️ Boundary Spatial Tracker (4s & 6s)")
            boundaries_df = df[(df['4s'] == 1) | (df['6s'] == 1)].copy()
            boundaries_df = boundaries_df.dropna(subset=['angle']) # Only plot if we know the direction
            
            if not boundaries_df.empty:
                # Create a true Polar Scatter Chart for boundaries
                boundaries_df['Run Type'] = boundaries_df.apply(lambda x: 'SIX' if x['6s'] == 1 else 'FOUR', axis=1)
                
                fig_polar = px.scatter_polar(
                    boundaries_df, 
                    r="runs", 
                    theta="angle", 
                    color="Run Type",
                    color_discrete_map={'SIX': '#e10600', 'FOUR': '#f59e0b'},
                    hover_name="batter",
                    hover_data=["bowler", "over_exact"],
                    template="plotly_dark",
                    size="runs",
                    size_max=15
                )
                fig_polar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=False, range=[0, 7]), 
                        angularaxis=dict(direction="clockwise", rotation=0, tickmode="array", tickvals=[0, 45, 90, 135, 180, 225, 270, 315], ticktext=["Straight", "Mid-Wicket", "Square Leg", "Fine Leg", "Keeper", "Third Man", "Point", "Cover"])
                    ),
                    margin=dict(t=40, b=40, l=40, r=40)
                )
                st.plotly_chart(fig_polar, use_container_width=True)
            else:
                st.warning("No directional boundary data found in this text.")

        with tab2:
            st.subheader("🏁 Animated Match Progression (Race Trace)")
            # Animated Line Chart over time
            animated_trace = px.line(
                df, x="over_exact", y="cumulative_runs", 
                title="Cumulative Runs Telemetry",
                template="plotly_dark",
                labels={"over_exact": "Overs", "cumulative_runs": "Total Score"},
                color_discrete_sequence=['#e10600']
            )
            # Add markers for wickets
            wickets_df = df[df['wicket'] == 1]
            if not wickets_df.empty:
                animated_trace.add_trace(
                    go.Scatter(x=wickets_df['over_exact'], y=wickets_df['cumulative_runs'],
                    mode='markers', marker=dict(color='white', size=10, symbol='x'), name='Wicket / Pit Stop')
                )
            st.plotly_chart(animated_trace, use_container_width=True)

        with tab3:
            col_b, col_w = st.columns(2)
            with col_b:
                st.markdown("### Top Drivers (Batting)")
                batting = df.groupby("batter").agg(Runs=("runs", "sum"), Balls=("runs", "count"), Fours=("4s", "sum"), Sixes=("6s", "sum")).reset_index().sort_values(by="Runs", ascending=False)
                st.dataframe(batting, use_container_width=True, hide_index=True)
            with col_w:
                st.markdown("### Top Engineers (Bowling)")
                bowling = df.groupby("bowler").agg(Wickets=("wicket", "sum"), Conceded=("runs", "sum")).reset_index().sort_values(by="Wickets", ascending=False)
                st.dataframe(bowling, use_container_width=True, hide_index=True)
