import re
import pandas as pd
import pdfplumber
import streamlit as st
import plotly.express as px

# 1. Page Configuration & F1 Paddock Styling
st.set_page_config(
    page_title="CRIC-F1 // Telemetry & Match Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp { background-color: #0b0e14; color: #f1f5f9; font-family: 'Segoe UI', Roboto, sans-serif; }
        [data-testid="stSidebar"] { background-color: #121824; border-right: 1px solid #1e293b; }
        .f1-card { background: linear-gradient(135deg, #161f30 0%, #0f172a 100%); border: 1px solid #1e293b; border-left: 4px solid #e10600; padding: 16px; border-radius: 6px; margin-bottom: 12px; }
        .f1-metric-title { font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #94a3b8; font-weight: 700; }
        .f1-metric-value { font-size: 26px; font-weight: 800; color: #ffffff; font-family: monospace; }
        h1, h2, h3 { font-weight: 800; letter-spacing: -0.5px; color: #ffffff; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 2. PDF Commentary Engine Parser (Updated for Cricbuzz Multi-Line Layout)
@st.cache_data
def parse_pdf_commentary(uploaded_file):
    ball_events = []
    current_over = 0.0
    
    # Zones for simulated Wagon Wheel
    field_zones = ["cover", "point", "third man", "fine leg", "square leg", "mid-wicket", "mid-on", "mid-off", "long-on", "long-off", "straight"]

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.split("\n"):
                    line = line.strip()
                    
                    # Catch standalone over numbers (e.g., "41.2")
                    over_match = re.match(r"^(\d+\.\d+)$", line)
                    if over_match:
                        current_over = float(over_match.group(1))
                        continue
                        
                    # Match commentary text (e.g., "Alzarri Joseph to Virat Kohli, FOUR...")
                    match = re.search(
                        r"^([A-Za-z\s\.\-]+)\s+to\s+([A-Za-z\s\.\-]+),\s+(.*)",
                        line,
                    )
                    
                    if match:
                        bowler, batter, desc = match.groups()
                        desc_lower = desc.lower()
                        runs, is_four, is_six, is_wicket = 0, 0, 0, 0
                        zone = "Unknown"

                        # Extract Wagon Wheel Zone
                        for z in field_zones:
                            if z.replace("-", "") in desc_lower.replace("-", ""):
                                zone = z.title()
                                break

                        # Event Logic
                        if "4 run" in desc_lower or "four" in desc_lower:
                            is_four = 1
                            runs = 4
                        elif "6 run" in desc_lower or "six" in desc_lower or "maximum" in desc_lower:
                            is_six = 1
                            runs = 6
                        elif any(w in desc_lower.split()[:8] for w in ["out", "caught", "bowled", "lbw", "stumped"]):
                            is_wicket = 1

                        # Standard runs
                        run_match = re.search(r"(\d+)\s+run", desc_lower)
                        if run_match and not is_four and not is_six:
                            runs = int(run_match.group(1))

                        ball_events.append({
                            "over_exact": current_over,
                            "over_num": int(current_over),
                            "bowler": bowler.strip(),
                            "batter": batter.strip(),
                            "runs": runs,
                            "4s": is_four,
                            "6s": is_six,
                            "wicket": is_wicket,
                            "zone": zone,
                            "description": desc.strip(),
                        })
    return pd.DataFrame(ball_events)


# 3. App UI & Logic
st.sidebar.markdown("### 🛑 RACE CONTROL / UPLOAD")
uploaded_pdf = st.sidebar.file_uploader("Upload Match Commentary (PDF)", type=["pdf"])

st.markdown("# 🏎️⚡ CRIC-F1 // LIVE MATCH TELEMETRY & ANALYTICS")
st.markdown("_High-speed motorsport telemetry data pipelines for cricket._")
st.markdown("---")

if uploaded_pdf is not None:
    with st.spinner("SYNCHRONIZING SECTORS... Parsing commentary data..."):
        df = parse_pdf_commentary(uploaded_pdf)

    if df.empty:
        st.error("Telemetry Sync Failed: Check if the PDF contains standard ball-by-ball commentary.")
    else:
        # Top Row Telemetry Cards
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.markdown(f'<div class="f1-card"><div class="f1-metric-title">Total Runs</div><div class="f1-metric-value">{df["runs"].sum()}</div></div>', unsafe_allow_html=True)
        col2.markdown(f'<div class="f1-card"><div class="f1-metric-title">Wickets</div><div class="f1-metric-value">{df["wicket"].sum()}</div></div>', unsafe_allow_html=True)
        col3.markdown(f'<div class="f1-card"><div class="f1-metric-title">Fours (4s)</div><div class="f1-metric-value">{df["4s"].sum()}</div></div>', unsafe_allow_html=True)
        col4.markdown(f'<div class="f1-card"><div class="f1-metric-title">Sixes (6s)</div><div class="f1-metric-value">{df["6s"].sum()}</div></div>', unsafe_allow_html=True)
        col5.markdown(f'<div class="f1-card"><div class="f1-metric-title">Balls Logged</div><div class="f1-metric-value">{len(df)}</div></div>', unsafe_allow_html=True)

        # Tab Navigation
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Scorecard & Leaderboards", 
            "📈 Manhattan & Wagon Wheel", 
            "👤 Player Deep-Dive", 
            "📜 Live Commentary Feed"
        ])

        with tab1:
            col_left, col_right = st.columns(2)
            with col_left:
                st.subheader("🏁 Batting Scorecard")
                batting_stats = df.groupby("batter").agg(
                    Runs=("runs", "sum"), Balls=("runs", "count"), Fours=("4s", "sum"), Sixes=("6s", "sum")
                ).reset_index().sort_values(by="Runs", ascending=False)
                batting_stats['Strike Rate'] = ((batting_stats['Runs'] / batting_stats['Balls']) * 100).round(2)
                st.dataframe(batting_stats, use_container_width=True, hide_index=True)
                
            with col_right:
                st.subheader("⚡ Bowling Scorecard")
                bowling_stats = df.groupby("bowler").agg(
                    Balls=("over_exact", "count"), Wickets=("wicket", "sum"), Conceded=("runs", "sum")
                ).reset_index().sort_values(by="Wickets", ascending=False)
                bowling_stats['Overs'] = (bowling_stats['Balls'] // 6) + (bowling_stats['Balls'] % 6) / 10
                bowling_stats['Economy'] = (bowling_stats['Conceded'] / (bowling_stats['Balls'] / 6)).round(2)
                st.dataframe(bowling_stats[['bowler', 'Overs', 'Conceded', 'Wickets', 'Economy']], use_container_width=True, hide_index=True)

        with tab2:
            st.subheader("🏙️ Manhattan Chart (Runs Per Over)")
            manhattan_data = df.groupby('over_num')['runs'].sum().reset_index()
            fig_manhattan = px.bar(manhattan_data, x='over_num', y='runs', labels={'over_num': 'Over', 'runs': 'Runs Scored'}, template="plotly_dark", color_discrete_sequence=['#e10600'])
            st.plotly_chart(fig_manhattan, use_container_width=True)

            st.subheader("🎡 Match Wagon Wheel (Scoring Zones)")
            zone_data = df[df['zone'] != 'Unknown']['zone'].value_counts().reset_index()
            zone_data.columns = ['Zone', 'Shots Played']
            if not zone_data.empty:
                fig_wagon = px.pie(zone_data, names='Zone', values='Shots Played', hole=0.5, template="plotly_dark", color_discrete_sequence=px.colors.sequential.Reds_r)
                st.plotly_chart(fig_wagon, use_container_width=True)
            else:
                st.info("No spatial data detected in commentary for a Wagon Wheel.")

        with tab3:
            st.subheader("🔍 Player Telemetry Profile")
            all_players = sorted(list(set(df["batter"]).union(set(df["bowler"]))))
            selected_player = st.selectbox("Select Driver / Player Profile:", all_players)

            if selected_player:
                p_bat = df[df["batter"] == selected_player]
                p_bowl = df[df["bowler"] == selected_player]
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Runs Scored", p_bat["runs"].sum())
                c2.metric("Strike Rate", round((p_bat["runs"].sum() / len(p_bat) * 100), 2) if len(p_bat) > 0 else 0)
                c3.metric("Wickets Taken", p_bowl["wicket"].sum())
                c4.metric("Bowling Economy", round(p_bowl["runs"].sum() / (len(p_bowl)/6), 2) if len(p_bowl) > 0 else 0)

                if len(p_bat) > 0:
                    st.markdown(f"**{selected_player}'s Scoring Zones (Wagon Wheel)**")
                    p_zones = p_bat[p_bat['zone'] != 'Unknown']['zone'].value_counts().reset_index()
                    p_zones.columns = ['Zone', 'Shots']
                    if not p_zones.empty:
                        fig_p = px.pie(p_zones, names='Zone', values='Shots', hole=0.4, template="plotly_dark")
                        st.plotly_chart(fig_p, use_container_width=True)

                st.markdown("**Recent Ball-by-Ball Involvement**")
                st.dataframe(pd.concat([p_bat, p_bowl]).sort_values(by="over_exact")[["over_exact", "description", "runs", "wicket"]], use_container_width=True, hide_index=True)

        with tab4:
            st.subheader("📡 Full Ball-by-Ball Telemetry Stream")
            st.dataframe(df[["over_exact", "bowler", "batter", "runs", "description"]], use_container_width=True, hide_index=True)
else:
    st.info("👉 **Awaiting Data Ingestion:** Upload your commentary PDF file via the left sidebar to spin up the dashboard analytics.")
