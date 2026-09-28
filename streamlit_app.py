import re
import pandas as pd
import pdfplumber
import streamlit as st

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


@st.cache_data
def parse_pdf_commentary(uploaded_file):
  ball_events = []
  with pdfplumber.open(uploaded_file) as pdf:
    for page in pdf.pages:
      text = page.extract_text()
      if text:
        for line in text.split("\n"):
          match = re.search(
              r"(\d+\.\d+)\s+([A-Za-z\s\.]+)\s+to\s+([A-Za-z\s\.]+),\s+(.*)",
              line,
          )
          if match:
            over, bowler, batter, desc = match.groups()
            desc_lower = desc.lower()
            runs, is_four, is_six, is_wicket = 0, 0, 0, 0

            if "4 run" in desc_lower or "four" in desc_lower:
              is_four = 1
              runs = 4
            elif "6 run" in desc_lower or "maximum" in desc_lower:
              is_six = 1
              runs = 6
            elif any(
                w in desc_lower
                for w in ["out", "caught", "bowled", "lbw", "run out"]
            ):
              is_wicket = 1

            run_match = re.search(r"(\d+)\s+run", desc_lower)
            if run_match and not is_four and not is_six:
              runs = int(run_match.group(1))

            ball_events.append({
                "over": float(over),
                "bowler": bowler.strip(),
                "batter": batter.strip(),
                "runs": runs,
                "4s": is_four,
                "6s": is_six,
                "wicket": is_wicket,
                "description": desc.strip(),
            })
  return pd.DataFrame(ball_events)


st.sidebar.markdown("### 🛑 RACE CONTROL / UPLOAD")
uploaded_pdf = st.sidebar.file_uploader(
    "Upload Match Commentary (PDF)", type=["pdf"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏎️ TELEMETRY CONFIG")
view_mode = st.sidebar.radio(
    "Select Display Mode",
    [
        "📊 Telemetry Overview (Leaderboards)",
        "📜 Live Feed (Scoring Log)",
        "👤 Driver/Player Deep-Dive",
    ],
)

st.markdown("# 🏎️⚡ CRIC-F1 // LIVE MATCH TELEMETRY & ANALYTICS")
st.markdown(
    "_Cricbuzz structure powered by high-speed motorsport telemetry data"
    " pipelines._"
)
st.markdown("---")

if uploaded_pdf is not None:
  with st.spinner("SYNCHRONIZING SECTORS... Parsing commentary data..."):
    df = parse_pdf_commentary(uploaded_pdf)

  if df.empty:
    st.error(
        "Telemetry Sync Failed: Could not automatically detect standard"
        " commentary patterns in this PDF layout."
    )
  else:
    total_runs = df["runs"].sum()
    total_wickets = df["wicket"].sum()
    total_boundaries_4 = df["4s"].sum()
    total_boundaries_6 = df["6s"].sum()
    total_balls = len(df)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.markdown(
        f'<div class="f1-card"><div class="f1-metric-title">Total'
        f' Runs</div><div class="f1-metric-value">{total_runs}</div></div>',
        unsafe_allow_html=True,
    )
    col2.markdown(
        f'<div class="f1-card"><div class="f1-metric-title">Wickets'
        f' Fallen</div><div class="f1-metric-value">{total_wickets}</div></div>',
        unsafe_allow_html=True,
    )
    col3.markdown(
        f'<div class="f1-card"><div class="f1-metric-title">Total Fours'
        f' (4s)</div><div class="f1-metric-value">{total_boundaries_4}</div></div>',
        unsafe_allow_html=True,
    )
    col4.markdown(
        f'<div class="f1-card"><div class="f1-metric-title">Total Sixes'
        f' (6s)</div><div class="f1-metric-value">{total_boundaries_6}</div></div>',
        unsafe_allow_html=True,
    )
    col5.markdown(
        f'<div class="f1-card"><div class="f1-metric-title">Balls'
        f' Logged</div><div class="f1-metric-value">{total_balls}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("###")

    if view_mode == "📊 Telemetry Overview (Leaderboards)":
      col_left, col_right = st.columns(2)
      with col_left:
        st.subheader("🏁 Top Batting Performance")
        batting_stats = (
            df.groupby("batter")
            .agg(
                Runs=("runs", "sum"),
                Balls=("runs", "count"),
                Fours=("4s", "sum"),
                Sixes=("6s", "sum"),
            )
            .reset_index()
            .sort_values(by="Runs", ascending=False)
        )
        st.dataframe(batting_stats, use_container_width=True, hide_index=True)
      with col_right:
        st.subheader("⚡ Top Bowling / Pit Efficiency")
        bowling_stats = (
            df.groupby("bowler")
            .agg(
                Balls_Bowled=("over", "count"),
                Wickets_Taken=("wicket", "sum"),
                Conceded=("runs", "sum"),
            )
            .reset_index()
            .sort_values(by="Wickets_Taken", ascending=False)
        )
        st.dataframe(bowling_stats, use_keyword=True, use_container_width=True)

    elif view_mode == "📜 Live Feed (Scoring Log)":
      st.subheader("📡 Full Ball-by-Ball Telemetry Stream")
      st.dataframe(df, use_container_width=True, hide_index=True)

    elif view_mode == "👤 Driver/Player Deep-Dive":
      st.subheader("🔍 Individual Player Telemetry Analysis")
      all_players = sorted(list(set(df["batter"]).union(set(df["bowler"]))))
      selected_player = st.selectbox(
          "Select Driver / Player Profile:", all_players
      )

      if selected_player:
        p_bat = df[df["batter"] == selected_player]
        p_bowl = df[df["bowler"] == selected_player]
        c1, c2, c3 = st.columns(3)
        c1.metric("Runs Scored", p_bat["runs"].sum())
        c2.metric("Balls Faced", len(p_bat))
        c3.metric("Wickets Taken", p_bowl["wicket"].sum())

        tab_b1, tab_b2 = st.tabs(["🏏 Batting Log Breakdown", "🎯 Bowling Log"])
        with tab_b1:
          st.dataframe(
              p_bat[["over", "bowler", "runs", "description"]],
              use_container_width=True,
          )
        with tab_b2:
          st.dataframe(
              p_bowl[["over", "batter", "wicket", "description"]],
              use_container_width=True,
          )
else:
  st.info(
      "👉 **Awaiting Data Ingestion:** Upload your commentary PDF file via the"
      " left sidebar to spin up the dashboard analytics."
  )
