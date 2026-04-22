# app.py
import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from typing import Tuple

st.set_page_config(page_title="Risk Dashboard", layout="wide")

st.markdown("""
<div style="
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 20px;
">
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 16px;
        padding: 20px 48px;
        display: inline-block;
        box-shadow: 0 4px 24px rgba(0,0,0,0.4);
        border: 2px solid #e94560;
    ">
        <a href="https://www.google.com" target="_blank" style="text-decoration: none;">
        <span style="
            font-size: 2.6rem;
            font-weight: 900;
            letter-spacing: 0.18em;
            background: linear-gradient(90deg, #e94560, #f5a623, #e94560);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-family: 'Segoe UI', sans-serif;
            cursor: pointer;
        ">김연준</span>
        </a>
        <div style="
            font-size: 0.75rem;
            color: #a0aec0;
            letter-spacing: 0.3em;
            text-align: center;
            margin-top: 4px;
            font-family: 'Segoe UI', sans-serif;
        ">KIM YEON JUN</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.title("🦟 Food Spoilage & Cockroach Risk Dashboard")

# ── 위험도 평가 함수 (노트북 기반, 0~100점제) ──────────────────────────────

def cockroach_risk(temp: float, hum: float, precip: float = 0.0, is_foggy: bool = False) -> Tuple[int, str]:
    """
    바퀴벌레 활동 위험도 (0~100점)
    - 발육 하한: 15°C, 최적 활동: 27~33°C
    - 습도 70% 이상에서 생존성 향상
    - 강수·안개: 서식처 습윤 효과 반영
    """
    score = 0

    if temp < 15:
        score += 5
    elif temp < 20:
        score += 15
    elif temp < 27:
        score += 40
    elif temp <= 33:
        score += 60
    elif temp < 40:
        score += 50
    else:
        score += 20

    if hum >= 70:
        score += 15
    elif hum >= 60:
        score += 8

    if precip > 0:
        score += 10

    if is_foggy:
        score += 8

    score = min(100, score)

    if score < 20:
        label = "Low"
    elif score < 40:
        label = "Moderate"
    elif score < 60:
        label = "Caution"
    elif score < 80:
        label = "High"
    else:
        label = "Very High"

    return score, label


def spoilage_risk(temp: float, hum: float, precip: float = 0.0) -> Tuple[int, str]:
    """
    음식 부패 위험도 (0~100점)
    - USDA FSIS Danger Zone: 4.4~60°C
    - 습도 70% 이상에서 결로·오염 위험 증가
    - 강수: 운반·보관 중 오염 위험 반영
    """
    score = 0

    if temp < 4.4:
        score += 5
    elif temp < 10:
        score += 20
    elif temp < 20:
        score += 35
    elif temp < 32:
        score += 70
    elif temp < 40:
        score += 85
    elif temp <= 60:
        score += 80
    else:
        score += 40

    if hum >= 70:
        score += 15
    elif hum >= 60:
        score += 8

    if precip > 0:
        score += 12

    score = min(100, score)

    if score < 20:
        label = "Low"
    elif score < 40:
        label = "Moderate"
    elif score < 60:
        label = "Caution"
    elif score < 80:
        label = "High"
    else:
        label = "Very High"

    return score, label


# ── Open-Meteo 실시간 데이터 수집 ─────────────────────────────────────────

CITIES = {
    "구리시": (37.5986, 127.1394),
    "서울": (37.5665, 126.9780),
    "부산": (35.1796, 129.0756),
    "대구": (35.8714, 128.5893),
    "인천": (37.4563, 126.7052),
}


@st.cache_data(ttl=1800)
def fetch_weather(lat: float, lon: float) -> pd.DataFrame | None:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,weather_code",
        "timezone": "Asia/Seoul",
        "forecast_days": 2,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame({
            "time": pd.to_datetime(h["time"]),
            "Temperature (°C)": h["temperature_2m"],
            "Humidity (%)": h["relative_humidity_2m"],
            "Precipitation (mm)": h["precipitation"],
            "weather_code": h["weather_code"],
        })
        return df
    except Exception as e:
        st.error(f"데이터 수집 실패: {e}")
        return None


def apply_risk(df: pd.DataFrame) -> pd.DataFrame:
    c_scores, c_labels, f_scores, f_labels = [], [], [], []
    for _, row in df.iterrows():
        is_foggy = row["weather_code"] in [45, 48]
        cs, cl = cockroach_risk(row["Temperature (°C)"], row["Humidity (%)"], row["Precipitation (mm)"], is_foggy)
        fs, fl = spoilage_risk(row["Temperature (°C)"], row["Humidity (%)"], row["Precipitation (mm)"])
        c_scores.append(cs); c_labels.append(cl)
        f_scores.append(fs); f_labels.append(fl)
    df = df.copy()
    df["Cockroach_Risk"] = c_scores
    df["Cockroach_Level"] = c_labels
    df["Food_Spoilage_Risk"] = f_scores
    df["Spoilage_Level"] = f_labels
    return df


# ── UI: 데이터 소스 선택 ──────────────────────────────────────────────────

tab_live, tab_upload = st.tabs(["🌐 실시간 기상 데이터 (Open-Meteo)", "📂 엑셀 파일 업로드"])

# ── Tab 1: 실시간 ─────────────────────────────────────────────────────────
with tab_live:
    city = st.selectbox("도시 선택", list(CITIES.keys()))
    if st.button("데이터 불러오기", type="primary"):
        lat, lon = CITIES[city]
        with st.spinner("기상 데이터 수집 중..."):
            df = fetch_weather(lat, lon)
        if df is not None:
            df = apply_risk(df)
            st.session_state["live_df"] = df

    if "live_df" in st.session_state:
        df = st.session_state["live_df"]

        # 현재 시각 기준 최신 행
        now = datetime.now()
        current = df[df["time"] <= now].iloc[-1] if not df[df["time"] <= now].empty else df.iloc[0]

        st.subheader("🚨 현재 위험도")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("기온", f"{current['Temperature (°C)']:.1f}°C")
        col2.metric("습도", f"{current['Humidity (%)']:.0f}%")
        col3.metric("🪳 바퀴벌레 위험도", f"{current['Cockroach_Risk']}/100", current["Cockroach_Level"])
        col4.metric("🍖 음식 부패 위험도", f"{current['Food_Spoilage_Risk']}/100", current["Spoilage_Level"])

        st.subheader("📈 48시간 위험도 추이")
        chart_df = df.set_index("time")[["Cockroach_Risk", "Food_Spoilage_Risk"]]
        st.line_chart(chart_df)

        st.subheader("📊 시간별 데이터")
        display_cols = ["time", "Temperature (°C)", "Humidity (%)", "Precipitation (mm)",
                        "Cockroach_Risk", "Cockroach_Level", "Food_Spoilage_Risk", "Spoilage_Level"]
        st.dataframe(df[display_cols].style.map(lambda _: "font-weight: bold", subset=["Cockroach_Risk", "Food_Spoilage_Risk"]))

        # 통계 요약
        with st.expander("📋 48시간 통계 요약"):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**🪳 바퀴벌레 활동 위험도**")
                st.write(f"평균: {df['Cockroach_Risk'].mean():.1f} / 최고: {df['Cockroach_Risk'].max()}")
                st.write(df["Cockroach_Level"].value_counts().rename("시간(h)"))
            with col_b:
                st.markdown("**🍖 음식 부패 위험도**")
                st.write(f"평균: {df['Food_Spoilage_Risk'].mean():.1f} / 최고: {df['Food_Spoilage_Risk'].max()}")
                st.write(df["Spoilage_Level"].value_counts().rename("시간(h)"))

# ── Tab 2: 엑셀 업로드 ───────────────────────────────────────────────────
with tab_upload:
    uploaded_file = st.file_uploader("날씨 엑셀 파일 업로드", type=["xlsx"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file)

        temp_candidates = [c for c in df.columns if "temp" in c.lower() or "기온" in c]
        hum_candidates = [c for c in df.columns if "hum" in c.lower() or "습도" in c]
        precip_candidates = [c for c in df.columns if "prec" in c.lower() or "강수" in c]

        if not temp_candidates:
            st.error("온도 컬럼을 찾을 수 없습니다. 컬럼명에 'temp' 또는 '기온'이 포함되어야 합니다.")
            st.stop()
        if not hum_candidates:
            st.error("습도 컬럼을 찾을 수 없습니다. 컬럼명에 'hum' 또는 '습도'가 포함되어야 합니다.")
            st.stop()

        temp_col = temp_candidates[0]
        hum_col = hum_candidates[0]
        precip_col = precip_candidates[0] if precip_candidates else None

        df = df.dropna(subset=[temp_col, hum_col])

        def _cockroach(row):
            p = row[precip_col] if precip_col else 0.0
            score, label = cockroach_risk(row[temp_col], row[hum_col], p)
            return pd.Series({"Cockroach_Risk": score, "Cockroach_Level": label})

        def _spoilage(row):
            p = row[precip_col] if precip_col else 0.0
            score, label = spoilage_risk(row[temp_col], row[hum_col], p)
            return pd.Series({"Food_Spoilage_Risk": score, "Spoilage_Level": label})

        df[["Cockroach_Risk", "Cockroach_Level"]] = df.apply(_cockroach, axis=1)
        df[["Food_Spoilage_Risk", "Spoilage_Level"]] = df.apply(_spoilage, axis=1)

        st.subheader("📊 Data Preview")
        st.dataframe(df.style.map(lambda _: "font-weight: bold", subset=[temp_col]))

        today = datetime.today().date()
        date_candidates = [c for c in df.columns if "date" in c.lower()]
        if date_candidates:
            date_col = date_candidates[0]
            df[date_col] = pd.to_datetime(df[date_col]).dt.date
            today_df = df[df[date_col] == today]
            if not today_df.empty:
                st.subheader("🚨 Today Risk Alert")
                col1, col2 = st.columns(2)
                col1.metric("🪳 Cockroach Risk", f"{today_df.iloc[0]['Cockroach_Risk']}/100", today_df.iloc[0]["Cockroach_Level"])
                col2.metric("🍖 Food Spoilage Risk", f"{today_df.iloc[0]['Food_Spoilage_Risk']}/100", today_df.iloc[0]["Spoilage_Level"])

        st.subheader("📈 Risk Trend")
        st.line_chart(df[["Cockroach_Risk", "Food_Spoilage_Risk"]])

    else:
        st.info("엑셀 파일을 업로드해주세요 (컬럼명에 temp/기온, hum/습도 포함 필요)")
