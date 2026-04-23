# app.py
import streamlit as st
import pandas as pd
import requests
import sqlite3
import os
import tempfile
from datetime import datetime, timedelta
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


# ── 기상청 KMA API ─────────────────────────────────────────────────────────

KMA_CITY_GRIDS = {
    "구리시": (62, 123),
    "서울": (60, 127),
    "부산": (98, 76),
    "대구": (89, 90),
    "인천": (55, 124),
}


def _pty_desc(code: str) -> str:
    return {
        '0': '없음', '1': '비', '2': '비/눈', '3': '눈',
        '5': '빗방울', '6': '빗방울눈날림', '7': '눈날림',
    }.get(code, '알 수 없음')


class KMAWeatherAPI:
    def __init__(self, service_key: str, nx: int, ny: int):
        self.service_key = service_key
        self.base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
        self.nx = nx
        self.ny = ny

    def get_current_weather(self):
        now = datetime.now()
        base_time = self._get_base_time(now)
        params = {
            'serviceKey': self.service_key,
            'pageNo': '1',
            'numOfRows': '1000',
            'dataType': 'JSON',
            'base_date': now.strftime('%Y%m%d'),
            'base_time': base_time,
            'nx': self.nx,
            'ny': self.ny,
        }
        try:
            r = requests.get(f"{self.base_url}/getUltraSrtNcst", params=params, timeout=10)
            return self._parse(r.json())
        except Exception as e:
            st.error(f"API 호출 오류: {e}")
            return None

    def _get_base_time(self, dt: datetime) -> str:
        if dt.minute < 40:
            dt = dt - timedelta(hours=1)
        return dt.strftime('%H00')

    def _parse(self, data: dict):
        header = data['response']['header']
        if header['resultCode'] != '00':
            st.error(f"API 오류: {header['resultMsg']}")
            return None
        result = {}
        for item in data['response']['body']['items']['item']:
            cat, val = item['category'], item['obsrValue']
            if cat == 'T1H':
                result['temperature'] = float(val)
            elif cat == 'REH':
                result['humidity'] = float(val)
            elif cat == 'PTY':
                result['precipitation_type'] = _pty_desc(val)
                result.setdefault('precipitation', 0.0 if val == '0' else 1.0)
            elif cat == 'WSD':
                result['wind_speed'] = float(val)
            elif cat == 'RN1':
                try:
                    result['precipitation'] = float(val)
                except ValueError:
                    result['precipitation'] = 0.0
        result.setdefault('precipitation', 0.0)
        result.setdefault('wind_speed', 0.0)
        result['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return result


# ── 위험도 분석 ────────────────────────────────────────────────────────────

class RiskAnalyzer:
    _cockroach_temp = (25, 30)
    _cockroach_hum = (60, 80)
    _spoilage_temp = 20
    _spoilage_hum = 70

    def calculate_cockroach_risk(self, temperature: float, humidity: float) -> float:
        t = self._temp_score(temperature, self._cockroach_temp)
        h = self._hum_score(humidity, self._cockroach_hum)
        return round(min(100, max(0, t * 0.6 + h * 0.4)), 2)

    def calculate_food_spoilage_risk(self, temperature: float, humidity: float) -> float:
        t_risk = max(0, (temperature - self._spoilage_temp) * 3)
        h_risk = max(0, (humidity - self._spoilage_hum) * 2)
        combined = t_risk + h_risk
        if temperature > 25 and humidity > 75:
            combined *= 1.5
        return round(min(100, combined), 2)

    def _temp_score(self, temp: float, r: tuple) -> float:
        lo, hi = r
        if lo <= temp <= hi:
            return 100
        return max(0, 100 - (lo - temp) * 10) if temp < lo else max(0, 100 - (temp - hi) * 8)

    def _hum_score(self, hum: float, r: tuple) -> float:
        lo, hi = r
        if lo <= hum <= hi:
            return 100
        return max(0, 100 - (lo - hum) * 2) if hum < lo else max(0, 100 - (hum - hi) * 3)

    def risk_level(self, score: float) -> tuple:
        if score >= 80:  return "매우 높음", "🔴"
        if score >= 60:  return "높음",     "🟠"
        if score >= 40:  return "보통",     "🟡"
        if score >= 20:  return "낮음",     "🟢"
        return "매우 낮음", "🔵"


# ── 날씨 이력 저장 (SQLite) ────────────────────────────────────────────────

class WeatherDataManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(tempfile.gettempdir(), "guri_weather.db")
        self.db_path = db_path
        conn = sqlite3.connect(db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT,
                timestamp DATETIME,
                temperature REAL,
                humidity REAL,
                precipitation_type TEXT,
                wind_speed REAL,
                cockroach_risk REAL,
                food_spoilage_risk REAL
            )
        ''')
        conn.commit()
        conn.close()

    def save(self, city: str, weather: dict, risks: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO weather_data
            (city, timestamp, temperature, humidity, precipitation_type,
             wind_speed, cockroach_risk, food_spoilage_risk)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            city, weather['update_time'],
            weather['temperature'], weather['humidity'],
            weather.get('precipitation_type', '없음'),
            weather.get('wind_speed', 0),
            risks['cockroach_risk'], risks['food_spoilage_risk'],
        ))
        conn.commit()
        conn.close()

    def get_recent(self, city: str, hours: int = 24) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(
            f"SELECT * FROM weather_data WHERE city=? AND timestamp >= datetime('now', '-{hours} hours') ORDER BY timestamp",
            conn, params=(city,)
        )
        conn.close()
        return df


# ── Open-Meteo 위험도 함수 ─────────────────────────────────────────────────

def cockroach_risk(temp: float, hum: float, precip: float = 0.0, is_foggy: bool = False) -> Tuple[int, str]:
    score = 0
    if temp < 15:       score += 5
    elif temp < 20:     score += 15
    elif temp < 27:     score += 40
    elif temp <= 33:    score += 60
    elif temp < 40:     score += 50
    else:               score += 20
    if hum >= 70:       score += 15
    elif hum >= 60:     score += 8
    if precip > 0:      score += 10
    if is_foggy:        score += 8
    score = min(100, score)
    if score < 20:      label = "Low"
    elif score < 40:    label = "Moderate"
    elif score < 60:    label = "Caution"
    elif score < 80:    label = "High"
    else:               label = "Very High"
    return score, label


def spoilage_risk(temp: float, hum: float, precip: float = 0.0) -> Tuple[int, str]:
    score = 0
    if temp < 4.4:      score += 5
    elif temp < 10:     score += 20
    elif temp < 20:     score += 35
    elif temp < 32:     score += 70
    elif temp < 40:     score += 85
    elif temp <= 60:    score += 80
    else:               score += 40
    if hum >= 70:       score += 15
    elif hum >= 60:     score += 8
    if precip > 0:      score += 12
    score = min(100, score)
    if score < 20:      label = "Low"
    elif score < 40:    label = "Moderate"
    elif score < 60:    label = "Caution"
    elif score < 80:    label = "High"
    else:               label = "Very High"
    return score, label


# ── Open-Meteo 데이터 수집 ─────────────────────────────────────────────────

OPEN_METEO_CITIES = {
    "구리시": (37.5986, 127.1394),
    "서울": (37.5665, 126.9780),
    "부산": (35.1796, 129.0756),
    "대구": (35.8714, 128.5893),
    "인천": (37.4563, 126.7052),
}


@st.cache_data(ttl=3600)
def fetch_open_meteo(lat: float, lon: float) -> pd.DataFrame | None:
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
        return pd.DataFrame({
            "time": pd.to_datetime(h["time"]),
            "Temperature (°C)": h["temperature_2m"],
            "Humidity (%)": h["relative_humidity_2m"],
            "Precipitation (mm)": h["precipitation"],
            "weather_code": h["weather_code"],
        })
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


# ── 자동 갱신 fragments ────────────────────────────────────────────────────

@st.fragment(run_every=timedelta(hours=1))
def kma_live_section(api_key: str, kma_city: str):
    if st.button("🔄 지금 새로고침", type="primary", key="kma_refresh"):
        st.rerun(scope="fragment")

    nx, ny = KMA_CITY_GRIDS[kma_city]
    analyzer = RiskAnalyzer()
    db = WeatherDataManager()

    with st.spinner("기상청 데이터 조회 중..."):
        weather = KMAWeatherAPI(api_key, nx, ny).get_current_weather()

    if not weather:
        return

    risks = {
        'cockroach_risk': analyzer.calculate_cockroach_risk(weather['temperature'], weather['humidity']),
        'food_spoilage_risk': analyzer.calculate_food_spoilage_risk(weather['temperature'], weather['humidity']),
    }
    db.save(kma_city, weather, risks)

    c_level, c_emoji = analyzer.risk_level(risks['cockroach_risk'])
    f_level, f_emoji = analyzer.risk_level(risks['food_spoilage_risk'])

    st.caption(f"기준 시각: {weather['update_time']} | 매 1시간 자동 갱신")
    st.subheader("🚨 현재 위험도")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🌡 기온", f"{weather['temperature']:.1f}°C")
    col2.metric("💧 습도", f"{weather['humidity']:.0f}%")
    col3.metric("🌧 강수형태", weather.get('precipitation_type', '없음'))
    col4.metric("🪳 바퀴벌레 위험도", f"{risks['cockroach_risk']:.0f}/100", f"{c_emoji} {c_level}")
    col5.metric("🍖 음식 부패 위험도", f"{risks['food_spoilage_risk']:.0f}/100", f"{f_emoji} {f_level}")

    history = db.get_recent(kma_city, 24)
    if not history.empty:
        st.subheader("📈 24시간 위험도 추이")
        history['timestamp'] = pd.to_datetime(history['timestamp'])
        st.line_chart(history.set_index('timestamp')[['cockroach_risk', 'food_spoilage_risk']])

        with st.expander("📋 저장된 이력 데이터"):
            st.dataframe(
                history[['timestamp', 'temperature', 'humidity',
                          'precipitation_type', 'wind_speed',
                          'cockroach_risk', 'food_spoilage_risk']]
            )


@st.fragment(run_every=timedelta(hours=1))
def open_meteo_section(city: str):
    if st.button("🔄 지금 새로고침", type="primary", key="meteo_refresh"):
        st.cache_data.clear()
        st.rerun(scope="fragment")

    lat, lon = OPEN_METEO_CITIES[city]
    with st.spinner("기상 데이터 수집 중..."):
        df = fetch_open_meteo(lat, lon)

    if df is None:
        st.error("기상 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
        return

    df = apply_risk(df)
    now = datetime.now()
    past = df[df["time"] <= now]
    current = past.iloc[-1] if not past.empty else df.iloc[0]

    st.caption(f"마지막 업데이트: {now.strftime('%Y-%m-%d %H:%M')} | 기준 시각: {current['time'].strftime('%Y-%m-%d %H:00')} | 매 1시간 자동 갱신")

    st.subheader("🚨 현재 위험도")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("기온", f"{current['Temperature (°C)']:.1f}°C")
    col2.metric("습도", f"{current['Humidity (%)']:.0f}%")
    col3.metric("🪳 바퀴벌레 위험도", f"{current['Cockroach_Risk']}/100", current["Cockroach_Level"])
    col4.metric("🍖 음식 부패 위험도", f"{current['Food_Spoilage_Risk']}/100", current["Spoilage_Level"])

    st.subheader("📈 48시간 위험도 추이")
    st.line_chart(df.set_index("time")[["Cockroach_Risk", "Food_Spoilage_Risk"]])

    st.subheader("📊 시간별 데이터")
    display_cols = ["time", "Temperature (°C)", "Humidity (%)", "Precipitation (mm)",
                    "Cockroach_Risk", "Cockroach_Level", "Food_Spoilage_Risk", "Spoilage_Level"]
    st.dataframe(
        df[display_cols].style
        .format({"Temperature (°C)": "{:.1f}", "Humidity (%)": "{:.1f}", "Precipitation (mm)": "{:.1f}"})
        .map(lambda _: "font-weight: bold", subset=["Cockroach_Risk", "Food_Spoilage_Risk"])
    )

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


# ── UI ────────────────────────────────────────────────────────────────────

tab_kma, tab_live, tab_upload = st.tabs([
    "🌡 기상청 실시간 (KMA)", "🌐 Open-Meteo", "📂 엑셀 파일 업로드",
])

# ── Tab 1: 기상청 KMA API ──────────────────────────────────────────────────
with tab_kma:
    col_key, col_city = st.columns([4, 2])
    with col_key:
        api_key = st.text_input(
            "기상청 API 서비스 키",
            type="password",
            help="공공데이터포털(data.go.kr)에서 발급받은 인증키를 입력하세요.",
        )
    with col_city:
        kma_city = st.selectbox("도시", list(KMA_CITY_GRIDS.keys()), key="kma_city")

    if not api_key:
        st.info("기상청 공공데이터 포털(data.go.kr)에서 발급받은 API 서비스 키를 입력하세요.")
    else:
        kma_live_section(api_key, kma_city)

# ── Tab 2: Open-Meteo ─────────────────────────────────────────────────────
with tab_live:
    city = st.selectbox("도시 선택", list(OPEN_METEO_CITIES.keys()))
    open_meteo_section(city)

# ── Tab 3: 엑셀 업로드 ────────────────────────────────────────────────────
with tab_upload:
    uploaded_file = st.file_uploader("날씨 엑셀 파일 업로드", type=["xlsx"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file)

        temp_candidates  = [c for c in df.columns if "temp" in c.lower() or "기온" in c]
        hum_candidates   = [c for c in df.columns if "hum"  in c.lower() or "습도" in c]
        precip_candidates = [c for c in df.columns if "prec" in c.lower() or "강수" in c]

        if not temp_candidates:
            st.error("온도 컬럼을 찾을 수 없습니다. 컬럼명에 'temp' 또는 '기온'이 포함되어야 합니다.")
            st.stop()
        if not hum_candidates:
            st.error("습도 컬럼을 찾을 수 없습니다. 컬럼명에 'hum' 또는 '습도'가 포함되어야 합니다.")
            st.stop()

        temp_col   = temp_candidates[0]
        hum_col    = hum_candidates[0]
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

        df[["Cockroach_Risk", "Cockroach_Level"]]     = df.apply(_cockroach, axis=1)
        df[["Food_Spoilage_Risk", "Spoilage_Level"]]  = df.apply(_spoilage, axis=1)

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
