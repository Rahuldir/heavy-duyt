import re
import pandas as pd
import pdfplumber
import streamlit as st
import plotly.express as px

# --- 1. CONFIGURATION & UI STYLING ---
st.set_page_config(
    page_title="CRIC-F1 // Advanced Match Telemetry",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #0a0a0a; color: #f1f5f9; font-family: 'Segoe UI', Roboto, sans-serif; }
        [data-testid="stSidebar"] { background-color: #111418; border-right: 1px solid #2d3748; }
        .f1-card { background: linear-gradient(135deg, #1a202c 0%, #171923 100%); border: 1px solid #2d3748; border-left: 4px solid #e10600; padding: 16px; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .f1-metric-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; color: #a0aec0; font-weight: 700; }
        .f1-metric-value { font-size: 28px; font-weight: 900; color: #ffffff; font-family: 'Courier New', monospace; }
        h1, h2, h3 { font-weight: 800; letter-spacing: -0.5px; color: #ffffff; }
        .stDataFrame { border: 1px solid #2d3748; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 2. ADVANCED DATA PARSING ENGINE ---
@st.cache_data
def robust_pdf_parser(uploaded_file):
    ball_events = []
    current_over = 0.0
    
    # Extensive Dictionary for Wagon Wheel Zone Detection
    zone_mapping = {
        "cover": "Cover", "extra cover": "Extra Cover", "point": "Point", "backward point": "Point",
        "third man": "Third Man", "fine leg": "Fine Leg", "square leg": "Square Leg", 
        "mid-wicket": "Mid-Wicket", "midwicket": "Mid-Wicket", "mid-on": "Mid-On", "mid on": "Mid-On",
        "mid-off": "Mid-Off", "mid off": "Mid-Off", "long-on": "Long-On", "long on": "Long-On",
        "long-off": "Long-Off", "long off": "Long-Off", "straight": "Straight down the ground"
    }

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
                
            lines = text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # A. Track the over number explicitly (Format: "41.2")
                over_match = re.match(r"^(\d+\.\d+)$", line)
                if over_match:
                    current_over = float(over_match.group(1))
                    continue
                    
                # B. Detect Ball Event (Format: "Bowler to Batter, Result")
                ball_match = re.search(r"^([A-Za-z\s\.\-\']+)\s+to\s+([A-Za-z\s\.\-\']+),\s+(.*)", line)
                
                if ball_match:
                    bowler, batter, desc = ball_match.groups()
                    desc_lower = desc.lower()
                    
                    runs, is_four, is_six, is_wicket, is_extra = 0, 0, 0, 0, 0
                    zone = "Unknown"

                    # Zone Mapping Logic
                    for key, mapped_zone in zone_mapping.items():
                        if key in desc_lower:
                            zone = mapped_zone
                            break

                    # Event Classification Engine
                    if "4 run" in desc_lower or "four" in desc_lower:
                        is_four = 1
                        runs = 4
                    elif "6 run" in desc_lower or "six" in desc_lower or "maximum" in desc_lower:
                        is_six = 1
                        runs = 6
                    elif "wide" in desc_lower or "no ball" in desc_lower or "leg bye" in desc_lower:
                        is_extra = 1
                        runs = 1 # Baseline extra run
                        
                    # Wicket Detection (Checks first 12 words to avoid false positives)
                    desc_start = " ".join(desc_lower.split()[:12])
                    if any(w in desc_start for w in ["out", "caught", "bowled", "lbw", "stumped", "run out", "c ", "b "]):
                        is_wicket = 1

                    # Standard running between the wickets (if no boundary or extra)
                    if not is_four and not is_six and not is_extra:
                        run_match = re.search(r"(\d+)\s+run", desc_lower)
                        if run_match:
                            runs = int(run_match.group(1))

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
                        "description": desc.strip(),
                    })
                    
    return pd.DataFrame(ball_events)

# --- 3. DASHBOARD ARCHITECTURE ---
st.sidebar.markdown("### 🛑 RACE CONTROL")
uploaded_pdf = st.sidebar.file_uploader("Ingest Match Data (PDF)", type=["pdf"])

st.markdown("# 🏎️⚡ CRIC-F1 // ADVANCED MATCH TELEMETRY")
st.markdown("_High-performance data extraction, scoring aggregates, and spatial analysis._")
st.markdown("---")

if uploaded_pdf is not None:
    with st.spinner("Processing Telemetry Data & Generating Visuals..."):
        df = robust_pdf_parser(uploaded_pdf)

    if df.empty:
        st.error("Data Sync Failed: Ensure the PDF contains structured ball-by-ball commentary.")
    else:
        # Core Match Metrics
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(f'<div class="f1-card"><div class="f1-metric-title">Total Runs</div><div class="f1-metric-value">{df["runs"].sum()}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="f1-card"><div class="f1-metric-title">Wickets</div><div class="f1-metric-value">{df["wicket"].sum()}</div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="f1-card"><div class="f1-metric-title">Boundaries (4s/6s)</div><div class="f1-metric-value">{df["4s"].sum()} / {df["6s"].sum()}</div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="f1-card"><div class="f1-metric-title">Extras</div><div class="f1-metric-value">{df["extra"].sum()}</div></div>', unsafe_allow_html=True)
        c5.markdown(f'<div class="f1-card"><div class="f1-metric-title">Total Balls</div><div class="f1-metric-value">{len(df)}</div></div>', unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["📊 Performance Scorecards", "📈 Spatial Analytics (Wagon & Manhattan)", "👤 Driver Profiles"])

        with tab1:
            col_b, col_w = st.columns(2)
            with col_b:
                st.subheader("🏏 Batting Aggregates")
                batting_stats = df.groupby("batter").agg(
                    Runs=("runs", "sum"), Balls=("runs", "count"), Fours=("4s", "sum"), Sixes=("6s", "sum")
                ).reset_index().sort_values(by="Runs", ascending=False)
                batting_stats['SR'] = ((batting_stats['Runs'] / batting_stats['Balls']) * 100).round(2)
                st.dataframe(batting_stats, use_container_width=True, hide_index=True)
                
            with col_w:
                st.subheader("🎯 Bowling Aggregates")
                bowling_stats = df.groupby("bowler").agg(
                    Balls=("over_exact", "count"), Wickets=("wicket", "sum"), Conceded=("runs", "sum")
                ).reset_index().sort_values(by="Wickets", ascending=False)
                bowling_stats['Overs'] = (bowling_stats['Balls'] // 6) + (bowling_stats['Balls'] % 6) / 10
                bowling_stats['Econ'] = (bowling_stats['Conceded'] / (bowling_stats['Balls'] / 6)).round(2)
                st.dataframe(bowling_stats[['bowler', 'Overs', 'Conceded', 'Wickets', 'Econ']], use_container_width=True, hide_index=True)

        with tab2:
            st.subheader("🏙️ Innings Manhattan (Runs per Over)")
            manhattan = df.groupby('over_num')['runs'].sum().reset_index()
            fig_m = px.bar(manhattan, x='over_num', y='runs', template="plotly_dark", color_discrete_sequence=['#e10600'])
            st.plotly_chart(fig_m, use_container_width=True)

            st.subheader("🎡 Match Wagon Wheel (Scoring Zones)")
            zones = df[df['zone'] != 'Unknown']['zone'].value_counts().reset_index()
            zones.columns = ['Zone', 'Shots']
            if not zones.empty:
                fig_w = px.pie(zones, names='Zone', values='Shots', hole=0.5, template="plotly_dark", color_discrete_sequence=px.colors.sequential.Reds_r)
                st.plotly_chart(fig_w, use_container_width=True)

        with tab3:
            st.subheader("🔍 Deep-Dive Player Telemetry")
            selected_player = st.selectbox("Select Player:", sorted(list(set(df["batter"]).union(set(df["bowler"])))))
            if selected_player:
                p_bat = df[df["batter"] == selected_player]
                if not p_bat.empty:
                    st.markdown(f"**Batting Zones for {selected_player}**")
                    p_zones = p_bat[p_bat['zone'] != 'Unknown']['zone'].value_counts().reset_index()
                    p_zones.columns = ['Zone', 'Shots']
                    if not p_zones.empty:
                        st.plotly_chart(px.pie(p_zones, names='Zone', values='Shots', hole=0.4, template="plotly_dark"), use_container_width=True)
                
                st.markdown("**Involvement Log (Batting & Bowling)**")
                st.dataframe(df[(df["batter"] == selected_player) | (df["bowler"] == selected_player)][["over_exact", "description", "runs", "wicket"]].sort_values(by="over_exact"), use_container_width=True, hide_index=True)
