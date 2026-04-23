# app.py
import streamlit as st
import pandas as pd
import requests
import sqlite3
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Tuple

KST = timezone(timedelta(hours=9))

def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)

st.set_page_config(page_title="위험도 대시보드", layout="wide", page_icon="🦟")

# ── 전역 CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* 배경 */
    .stApp { background-color: #0f1117; }
    section[data-testid="stSidebar"] { background-color: #161b27; }

    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: #1a1f2e;
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #718096;
        font-weight: 600;
        padding: 8px 20px;
    }
    .stTabs [aria-selected="true"] {
        background: #2d3748 !important;
        color: #e2e8f0 !important;
    }

    /* 카드 공통 */
    .card {
        background: #1a1f2e;
        border-radius: 14px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }

    /* 날씨 스탯 */
    .stat-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 20px;
    }
    .stat-box {
        background: #1a1f2e;
        border-radius: 12px;
        padding: 18px 12px;
        text-align: center;
        border: 1px solid #2d3748;
    }
    .stat-icon { font-size: 1.6rem; }
    .stat-label {
        color: #718096;
        font-size: 0.72rem;
        letter-spacing: .06em;
        text-transform: uppercase;
        margin: 6px 0 4px;
    }
    .stat-value {
        color: #e2e8f0;
        font-size: 1.35rem;
        font-weight: 700;
    }

    /* 위험도 카드 */
    .risk-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 14px;
        margin-bottom: 20px;
    }
    .risk-box {
        border-radius: 14px;
        padding: 20px 22px;
        border-left: 5px solid;
    }
    .risk-title {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: .08em;
        color: #a0aec0;
        margin-bottom: 10px;
    }
    .risk-score {
        font-size: 2.6rem;
        font-weight: 800;
        line-height: 1;
    }
    .risk-score span {
        font-size: 1rem;
        font-weight: 400;
        color: #718096;
    }
    .risk-bar-bg {
        background: #2d3748;
        border-radius: 999px;
        height: 6px;
        margin: 12px 0 8px;
        overflow: hidden;
    }
    .risk-bar-fill {
        height: 100%;
        border-radius: 999px;
        transition: width .4s ease;
    }
    .risk-badge {
        font-size: 0.85rem;
        font-weight: 600;
    }

    /* 섹션 타이틀 */
    .section-title {
        color: #a0aec0;
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .1em;
        margin: 24px 0 10px;
        padding-bottom: 8px;
        border-bottom: 1px solid #2d3748;
    }

    /* 업데이트 타임스탬프 */
    .timestamp {
        color: #4a5568;
        font-size: 0.78rem;
        margin-bottom: 16px;
    }

    /* 입력 필드 */
    .stTextInput input, .stSelectbox select {
        background: #1a1f2e !important;
        border-color: #2d3748 !important;
        color: #e2e8f0 !important;
    }

    /* expander */
    .streamlit-expanderHeader {
        background: #1a1f2e;
        border-radius: 8px;
        color: #a0aec0 !important;
    }

    /* 버튼 */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    /* 차트 배경 투명 */
    .stVegaLiteChart, .stPlotlyChart { background: transparent !important; }
</style>
""", unsafe_allow_html=True)


# ── 헤더 ──────────────────────────────────────────────────────────────────

st.markdown("""
<div style="
    display:flex; align-items:center; justify-content:center;
    gap:16px; padding:28px 0 8px;
">
    <div style="text-align:center;">
        <a href="https://www.weather.go.kr/w/weather/forecast/short-term.do"
           target="_blank" style="text-decoration:none;">
            <div style="
                font-size:2rem; font-weight:900; letter-spacing:.12em;
                background:linear-gradient(90deg,#667eea,#764ba2);
                -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                font-family:'Segoe UI',sans-serif;
            ">기상청</div>
        </a>
        <div style="color:#4a5568; font-size:.72rem; letter-spacing:.2em; margin-top:2px;">
            구리시 날씨 예보
        </div>
    </div>
    <div style="width:1px; height:40px; background:#2d3748;"></div>
    <div>
        <div style="
            font-size:1.5rem; font-weight:800; color:#e2e8f0;
            font-family:'Segoe UI',sans-serif;
        ">위험도 대시보드</div>
        <div style="color:#4a5568; font-size:.72rem; letter-spacing:.08em;">
            FOOD SPOILAGE &amp; COCKROACH RISK
        </div>
    </div>
</div>
<hr style="border-color:#1a1f2e; margin:0 0 20px;">
""", unsafe_allow_html=True)


# ── 유틸 함수 ─────────────────────────────────────────────────────────────

_SECTION = (
    '<div style="color:#a0aec0;font-size:0.78rem;font-weight:700;'
    'text-transform:uppercase;letter-spacing:.1em;'
    'margin:24px 0 10px;padding-bottom:8px;border-bottom:1px solid #2d3748;">'
)
_TS = '<div style="color:#4a5568;font-size:0.78rem;margin-bottom:16px;">'

def _section(title: str) -> str:
    return f'{_SECTION}{title}</div>'

def _timestamp(text: str) -> str:
    return f'{_TS}{text}</div>'

def _risk_color(score: float) -> str:
    if score >= 80: return "#fc8181"
    if score >= 60: return "#f6ad55"
    if score >= 40: return "#f6e05e"
    if score >= 20: return "#68d391"
    return "#4fd1c5"

def _risk_bg(score: float) -> str:
    if score >= 80: return "#2d1515"
    if score >= 60: return "#2d1f10"
    if score >= 40: return "#2d2a10"
    if score >= 20: return "#122d1a"
    return "#102d2b"

def render_weather_stats(weather: dict) -> str:
    stats = [
        ("🌡", "기온",    f"{weather['temperature']:.1f}°C"),
        ("💧", "습도",    f"{weather['humidity']:.0f}%"),
        ("🌧", "강수형태", weather.get('precipitation_type', '없음')),
        ("💨", "풍속",    f"{weather.get('wind_speed', 0):.1f} m/s"),
    ]
    box_style = (
        "background:#1a1f2e; border-radius:12px; padding:18px 12px; "
        "text-align:center; border:1px solid #2d3748; flex:1;"
    )
    boxes = "".join(f"""
        <div style="{box_style}">
            <div style="font-size:1.6rem;">{icon}</div>
            <div style="color:#718096;font-size:0.72rem;letter-spacing:.06em;
                        text-transform:uppercase;margin:6px 0 4px;">{label}</div>
            <div style="color:#e2e8f0;font-size:1.35rem;font-weight:700;">{value}</div>
        </div>""" for icon, label, value in stats)
    return f'<div style="display:flex;gap:12px;margin-bottom:20px;">{boxes}</div>'

def render_risk_cards(c_score: float, c_level: str, c_emoji: str,
                      f_score: float, f_level: str, f_emoji: str) -> str:
    def row(title, score, level, emoji):
        color = _risk_color(score)
        bar = (
            f'<div style="background:#2d3748;border-radius:999px;height:8px;'
            f'min-width:120px;overflow:hidden;">'
            f'<div style="width:{score:.0f}%;height:100%;border-radius:999px;'
            f'background:{color};"></div></div>'
        )
        return (
            f'<tr>'
            f'<td style="padding:12px 16px;color:#e2e8f0;font-size:0.9rem;white-space:nowrap;">{title}</td>'
            f'<td style="padding:12px 16px;text-align:center;font-size:1.2rem;font-weight:700;color:{color};">{score:.0f}</td>'
            f'<td style="padding:12px 16px;">{bar}</td>'
            f'<td style="padding:12px 16px;font-size:0.85rem;font-weight:600;color:{color};white-space:nowrap;">{emoji} {level}</td>'
            f'</tr>'
        )
    header = (
        '<tr style="border-bottom:1px solid #2d3748;">'
        '<th style="padding:10px 16px;text-align:left;color:#718096;font-size:0.75rem;'
        'text-transform:uppercase;letter-spacing:.08em;font-weight:600;">항목</th>'
        '<th style="padding:10px 16px;text-align:center;color:#718096;font-size:0.75rem;'
        'text-transform:uppercase;letter-spacing:.08em;font-weight:600;">점수</th>'
        '<th style="padding:10px 16px;color:#718096;font-size:0.75rem;'
        'text-transform:uppercase;letter-spacing:.08em;font-weight:600;">위험도</th>'
        '<th style="padding:10px 16px;color:#718096;font-size:0.75rem;'
        'text-transform:uppercase;letter-spacing:.08em;font-weight:600;">수준</th>'
        '</tr>'
    )
    rows = (
        row("🪳 바퀴벌레 출현 위험도", c_score, c_level, c_emoji) +
        row("🍖 음식 부패 위험도",     f_score, f_level, f_emoji)
    )
    return (
        '<table style="width:100%;border-collapse:collapse;background:#1a1f2e;'
        'border-radius:12px;overflow:hidden;border:1px solid #2d3748;margin-bottom:20px;">'
        f'<thead>{header}</thead>'
        f'<tbody>{rows}</tbody>'
        '</table>'
    )


# ── 기상청 KMA API ─────────────────────────────────────────────────────────

KMA_CITY_GRIDS = {
    "구리시": (62, 123),
    "서울":   (60, 127),
    "부산":   (98, 76),
    "대구":   (89, 90),
    "인천":   (55, 124),
}

def _pty_desc(code: str) -> str:
    return {'0':'없음','1':'비','2':'비/눈','3':'눈',
            '5':'빗방울','6':'빗방울눈날림','7':'눈날림'}.get(code, '알 수 없음')

class KMAWeatherAPI:
    def __init__(self, service_key: str, nx: int, ny: int):
        self.service_key = service_key
        self.base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
        self.nx = nx
        self.ny = ny

    def get_current_weather(self):
        base_dt = self._base_dt()
        params = {
            'serviceKey': self.service_key,
            'pageNo': '1', 'numOfRows': '1000', 'dataType': 'JSON',
            'base_date': base_dt.strftime('%Y%m%d'),
            'base_time': base_dt.strftime('%H00'),
            'nx': self.nx, 'ny': self.ny,
        }
        try:
            r = requests.get(f"{self.base_url}/getUltraSrtNcst", params=params, timeout=10)
            return self._parse(r.json())
        except Exception as e:
            st.error(f"API 호출 오류: {e}")
            return None

    def _base_dt(self) -> datetime:
        dt = now_kst()
        if dt.minute < 40:
            dt -= timedelta(hours=1)
        return dt.replace(minute=0, second=0, microsecond=0)

    def _parse(self, data: dict):
        header = data['response']['header']
        if header['resultCode'] != '00':
            st.error(f"API 오류: {header['resultMsg']}")
            return None
        result = {}
        for item in data['response']['body']['items']['item']:
            cat, val = item['category'], item['obsrValue']
            if cat == 'T1H':   result['temperature'] = float(val)
            elif cat == 'REH': result['humidity'] = float(val)
            elif cat == 'PTY':
                result['precipitation_type'] = _pty_desc(val)
                result.setdefault('precipitation', 0.0 if val == '0' else 1.0)
            elif cat == 'WSD': result['wind_speed'] = float(val)
            elif cat == 'RN1':
                try:    result['precipitation'] = float(val)
                except: result['precipitation'] = 0.0
        result.setdefault('precipitation', 0.0)
        result.setdefault('wind_speed', 0.0)
        result['update_time'] = now_kst().strftime('%Y-%m-%d %H:%M:%S')
        return result


# ── 위험도 분석 ────────────────────────────────────────────────────────────

class RiskAnalyzer:
    _cockroach_temp = (25, 30)
    _cockroach_hum  = (60, 80)
    _spoilage_temp  = 20
    _spoilage_hum   = 70

    def calculate_cockroach_risk(self, temperature: float, humidity: float) -> float:
        t = self._temp_score(temperature, self._cockroach_temp)
        h = self._hum_score(humidity,    self._cockroach_hum)
        return round(min(100, max(0, t * 0.6 + h * 0.4)), 2)

    def calculate_food_spoilage_risk(self, temperature: float, humidity: float) -> float:
        t_risk   = max(0, (temperature - self._spoilage_temp) * 3)
        h_risk   = max(0, (humidity    - self._spoilage_hum)  * 2)
        combined = t_risk + h_risk
        if temperature > 25 and humidity > 75:
            combined *= 1.5
        return round(min(100, combined), 2)

    def _temp_score(self, temp, r):
        lo, hi = r
        if lo <= temp <= hi: return 100
        return max(0, 100-(lo-temp)*10) if temp < lo else max(0, 100-(temp-hi)*8)

    def _hum_score(self, hum, r):
        lo, hi = r
        if lo <= hum <= hi: return 100
        return max(0, 100-(lo-hum)*2) if hum < lo else max(0, 100-(hum-hi)*3)

    def risk_level(self, score: float) -> tuple:
        if score >= 80: return "매우 높음", "🔴"
        if score >= 60: return "높음",     "🟠"
        if score >= 40: return "보통",     "🟡"
        if score >= 20: return "낮음",     "🟢"
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
                city TEXT, timestamp DATETIME,
                temperature REAL, humidity REAL,
                precipitation_type TEXT, wind_speed REAL,
                cockroach_risk REAL, food_spoilage_risk REAL
            )
        ''')
        conn.commit(); conn.close()

    def save(self, city: str, weather: dict, risks: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO weather_data
            (city,timestamp,temperature,humidity,precipitation_type,
             wind_speed,cockroach_risk,food_spoilage_risk)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (city, weather['update_time'],
              weather['temperature'], weather['humidity'],
              weather.get('precipitation_type','없음'),
              weather.get('wind_speed', 0),
              risks['cockroach_risk'], risks['food_spoilage_risk']))
        conn.commit(); conn.close()

    def get_recent(self, city: str, hours: int = 24) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query(
            f"SELECT * FROM weather_data WHERE city=? "
            f"AND timestamp >= datetime('now','-{hours} hours') ORDER BY timestamp",
            conn, params=(city,))
        conn.close()
        return df


# ── Open-Meteo 위험도 함수 ─────────────────────────────────────────────────

def cockroach_risk(temp: float, hum: float, precip: float = 0.0, is_foggy: bool = False) -> Tuple[int, str]:
    score = 0
    if temp < 15:    score += 5
    elif temp < 20:  score += 15
    elif temp < 27:  score += 40
    elif temp <= 33: score += 60
    elif temp < 40:  score += 50
    else:            score += 20
    if hum >= 70:    score += 15
    elif hum >= 60:  score += 8
    if precip > 0:   score += 10
    if is_foggy:     score += 8
    score = min(100, score)
    if score < 20:   label = "Low"
    elif score < 40: label = "Moderate"
    elif score < 60: label = "Caution"
    elif score < 80: label = "High"
    else:            label = "Very High"
    return score, label

def spoilage_risk(temp: float, hum: float, precip: float = 0.0) -> Tuple[int, str]:
    score = 0
    if temp < 4.4:   score += 5
    elif temp < 10:  score += 20
    elif temp < 20:  score += 35
    elif temp < 32:  score += 70
    elif temp < 40:  score += 85
    elif temp <= 60: score += 80
    else:            score += 40
    if hum >= 70:    score += 15
    elif hum >= 60:  score += 8
    if precip > 0:   score += 12
    score = min(100, score)
    if score < 20:   label = "Low"
    elif score < 40: label = "Moderate"
    elif score < 60: label = "Caution"
    elif score < 80: label = "High"
    else:            label = "Very High"
    return score, label

OPEN_METEO_CITIES = {
    "구리시": (37.5986, 127.1394),
    "서울":   (37.5665, 126.9780),
    "부산":   (35.1796, 129.0756),
    "대구":   (35.8714, 128.5893),
    "인천":   (37.4563, 126.7052),
}

@st.cache_data(ttl=3600)
def fetch_open_meteo(lat: float, lon: float) -> pd.DataFrame | None:
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,weather_code",
            "timezone": "Asia/Seoul", "forecast_days": 2,
        }, timeout=10)
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
    df["Cockroach_Risk"]    = c_scores; df["Cockroach_Level"]  = c_labels
    df["Food_Spoilage_Risk"]= f_scores; df["Spoilage_Level"]   = f_labels
    return df


# ── 사이드바 ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="padding:8px 0 20px;">
        <div style="color:#667eea; font-size:1.1rem; font-weight:700;">⚙️ 설정</div>
    </div>
    """, unsafe_allow_html=True)

    api_key = st.text_input(
        "기상청 API 키",
        type="password",
        placeholder="서비스 키를 입력하세요",
        help="공공데이터포털(data.go.kr)에서 발급받은 인증키",
    )
    kma_city = st.selectbox("KMA 도시", list(KMA_CITY_GRIDS.keys()))

    st.divider()
    st.markdown("<div style='color:#4a5568; font-size:0.72rem;'>데이터 출처</div>", unsafe_allow_html=True)
    st.markdown("<div style='color:#718096; font-size:0.8rem;'>• 기상청 초단기실황 API<br>• Open-Meteo (무료)</div>", unsafe_allow_html=True)


# ── 자동 갱신 fragments ────────────────────────────────────────────────────

@st.fragment(run_every=timedelta(hours=1))
def kma_live_section(api_key: str, kma_city: str):
    col_info, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("🔄 새로고침", use_container_width=True, key="kma_refresh"):
            st.rerun(scope="fragment")

    nx, ny = KMA_CITY_GRIDS[kma_city]
    analyzer = RiskAnalyzer()
    db = WeatherDataManager()

    with st.spinner("기상청 데이터 조회 중..."):
        weather = KMAWeatherAPI(api_key, nx, ny).get_current_weather()

    if not weather:
        return

    risks = {
        'cockroach_risk':    analyzer.calculate_cockroach_risk(weather['temperature'], weather['humidity']),
        'food_spoilage_risk': analyzer.calculate_food_spoilage_risk(weather['temperature'], weather['humidity']),
    }
    db.save(kma_city, weather, risks)

    c_level, c_emoji = analyzer.risk_level(risks['cockroach_risk'])
    f_level, f_emoji = analyzer.risk_level(risks['food_spoilage_risk'])

    with col_info:
        st.markdown(_timestamp(f"📡 기준 시각: {weather['update_time']} &nbsp;·&nbsp; 매 1시간 자동 갱신"), unsafe_allow_html=True)

    st.markdown(_section("현재 기상 상태"), unsafe_allow_html=True)
    st.markdown(render_weather_stats(weather), unsafe_allow_html=True)

    st.markdown(_section("위험도 분석"), unsafe_allow_html=True)
    st.markdown(
        render_risk_cards(
            risks['cockroach_risk'],    c_level, c_emoji,
            risks['food_spoilage_risk'], f_level, f_emoji,
        ),
        unsafe_allow_html=True,
    )

    history = db.get_recent(kma_city, 24)
    if not history.empty:
        st.markdown("<div style='color:#a0aec0;font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;margin:24px 0 10px;padding-bottom:8px;border-bottom:1px solid #2d3748;'>24시간 추이</div>", unsafe_allow_html=True)
        history['timestamp'] = pd.to_datetime(history['timestamp'])
        h = history.set_index('timestamp')

        col_a, col_b = st.columns(2)
        with col_a:
            st.caption("🌡 기온 (°C)")
            st.line_chart(h[['temperature']], color=["#63b3ed"])
            st.caption("🪳 바퀴벌레 위험도")
            st.line_chart(h[['cockroach_risk']], color=["#fc8181"])
        with col_b:
            st.caption("💧 습도 (%)")
            st.line_chart(h[['humidity']], color=["#68d391"])
            st.caption("🍖 음식 부패 위험도")
            st.line_chart(h[['food_spoilage_risk']], color=["#f6ad55"])
        with st.expander("📋 이력 데이터 보기"):
            st.dataframe(
                history[['timestamp','temperature','humidity',
                          'precipitation_type','wind_speed',
                          'cockroach_risk','food_spoilage_risk']],
                use_container_width=True,
            )


@st.fragment(run_every=timedelta(hours=1))
def open_meteo_section(city: str):
    col_info, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("🔄 새로고침", use_container_width=True, key="meteo_refresh"):
            st.cache_data.clear()
            st.rerun(scope="fragment")

    lat, lon = OPEN_METEO_CITIES[city]
    with st.spinner("기상 데이터 수집 중..."):
        df = fetch_open_meteo(lat, lon)

    if df is None:
        st.error("기상 데이터를 불러올 수 없습니다.")
        return

    df = apply_risk(df)
    now = now_kst()
    past = df[df["time"] <= now]
    current = past.iloc[-1] if not past.empty else df.iloc[0]

    with col_info:
        st.markdown(
            _timestamp(f"📡 기준 시각: {current['time'].strftime('%Y-%m-%d %H:00')} "
                       f"&nbsp;·&nbsp; 마지막 업데이트: {now.strftime('%H:%M')} &nbsp;·&nbsp; 매 1시간 자동 갱신"),
            unsafe_allow_html=True,
        )

    # 현재 기상 상태 (Open-Meteo)
    st.markdown(_section("현재 기상 상태"), unsafe_allow_html=True)
    weather_om = {
        'temperature': current["Temperature (°C)"],
        'humidity':    current["Humidity (%)"],
        'precipitation_type': f"{current['Precipitation (mm)']:.1f} mm",
        'wind_speed':  0,
    }
    st.markdown(render_weather_stats(weather_om), unsafe_allow_html=True)

    # 위험도 카드
    cs, cl = int(current["Cockroach_Risk"]),    current["Cockroach_Level"]
    fs, fl = int(current["Food_Spoilage_Risk"]), current["Spoilage_Level"]

    level_map = {"Low":"낮음","Moderate":"보통","Caution":"주의","High":"높음","Very High":"매우 높음"}
    emoji_map = {"Low":"🔵","Moderate":"🟢","Caution":"🟡","High":"🟠","Very High":"🔴"}

    st.markdown(_section("위험도 분석"), unsafe_allow_html=True)
    st.markdown(
        render_risk_cards(
            cs, level_map.get(cl, cl), emoji_map.get(cl, ""),
            fs, level_map.get(fl, fl), emoji_map.get(fl, ""),
        ),
        unsafe_allow_html=True,
    )

    st.markdown(_section("48시간 위험도 추이"), unsafe_allow_html=True)
    st.line_chart(
        df.set_index("time")[["Cockroach_Risk", "Food_Spoilage_Risk"]],
        color=["#fc8181", "#f6ad55"],
    )

    with st.expander("📊 시간별 상세 데이터"):
        display_cols = ["time","Temperature (°C)","Humidity (%)","Precipitation (mm)",
                        "Cockroach_Risk","Cockroach_Level","Food_Spoilage_Risk","Spoilage_Level"]
        st.dataframe(
            df[display_cols].style
            .format({"Temperature (°C)":"{:.1f}","Humidity (%)":"{:.1f}","Precipitation (mm)":"{:.1f}"})
            .map(lambda _: "font-weight:bold", subset=["Cockroach_Risk","Food_Spoilage_Risk"]),
            use_container_width=True,
        )

    with st.expander("📋 48시간 통계 요약"):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**🪳 바퀴벌레 위험도**")
            st.write(f"평균: {df['Cockroach_Risk'].mean():.1f} / 최고: {df['Cockroach_Risk'].max()}")
            st.write(df["Cockroach_Level"].value_counts().rename("시간(h)"))
        with col_b:
            st.markdown("**🍖 음식 부패 위험도**")
            st.write(f"평균: {df['Food_Spoilage_Risk'].mean():.1f} / 최고: {df['Food_Spoilage_Risk'].max()}")
            st.write(df["Spoilage_Level"].value_counts().rename("시간(h)"))


# ── UI 탭 ─────────────────────────────────────────────────────────────────

tab_kma, tab_live, tab_upload = st.tabs([
    "🌡 기상청 실시간 (KMA)", "🌐 Open-Meteo", "📂 엑셀 업로드",
])

with tab_kma:
    if not api_key:
        st.markdown("""
        <div style="background:#1a1f2e; border:1px solid #2d3748; border-radius:12px;
                    padding:28px; text-align:center; color:#718096;">
            <div style="font-size:2rem; margin-bottom:12px;">🔑</div>
            <div style="font-size:1rem; font-weight:600; color:#a0aec0; margin-bottom:6px;">
                API 키를 입력해주세요
            </div>
            <div style="font-size:0.85rem;">
                왼쪽 사이드바에서 기상청 API 서비스 키를 입력하면 실시간 데이터를 조회합니다.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        kma_live_section(api_key, kma_city)

with tab_live:
    open_meteo_section(
        st.selectbox("도시 선택", list(OPEN_METEO_CITIES.keys()), key="om_city")
    )

with tab_upload:
    uploaded_file = st.file_uploader(
        "날씨 데이터 업로드", type=["xlsx"],
        help="컬럼명에 temp/기온, hum/습도 포함 필요",
    )

    if not uploaded_file:
        st.markdown("""
        <div style="background:#1a1f2e; border:2px dashed #2d3748; border-radius:12px;
                    padding:40px; text-align:center; color:#4a5568;">
            <div style="font-size:2.5rem; margin-bottom:12px;">📂</div>
            <div style="font-size:1rem; color:#718096; font-weight:600;">엑셀 파일을 업로드하세요</div>
            <div style="font-size:0.82rem; margin-top:8px;">
                필수 컬럼: <code>temp</code> 또는 <code>기온</code> &nbsp;/&nbsp;
                <code>hum</code> 또는 <code>습도</code>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
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

        def _cr(row):
            p = row[precip_col] if precip_col else 0.0
            s, l = cockroach_risk(row[temp_col], row[hum_col], p)
            return pd.Series({"Cockroach_Risk": s, "Cockroach_Level": l})

        def _sr(row):
            p = row[precip_col] if precip_col else 0.0
            s, l = spoilage_risk(row[temp_col], row[hum_col], p)
            return pd.Series({"Food_Spoilage_Risk": s, "Spoilage_Level": l})

        df[["Cockroach_Risk","Cockroach_Level"]]    = df.apply(_cr, axis=1)
        df[["Food_Spoilage_Risk","Spoilage_Level"]] = df.apply(_sr, axis=1)

        today = now_kst().date()
        date_candidates = [c for c in df.columns if "date" in c.lower()]
        if date_candidates:
            date_col = date_candidates[0]
            df[date_col] = pd.to_datetime(df[date_col]).dt.date
            today_df = df[df[date_col] == today]
            if not today_df.empty:
                row = today_df.iloc[0]
                cs = float(row['Cockroach_Risk'])
                fs = float(row['Food_Spoilage_Risk'])
                cl = str(row['Cockroach_Level'])
                fl = str(row['Spoilage_Level'])
                level_map = {"Low":"낮음","Moderate":"보통","Caution":"주의","High":"높음","Very High":"매우 높음"}
                emoji_map = {"Low":"🔵","Moderate":"🟢","Caution":"🟡","High":"🟠","Very High":"🔴"}
                st.markdown(_section("오늘 위험도"), unsafe_allow_html=True)
                st.markdown(
                    render_risk_cards(
                        cs, level_map.get(cl, cl), emoji_map.get(cl, ""),
                        fs, level_map.get(fl, fl), emoji_map.get(fl, ""),
                    ),
                    unsafe_allow_html=True,
                )

        st.markdown(_section("위험도 추이"), unsafe_allow_html=True)
        st.line_chart(
            df[["Cockroach_Risk","Food_Spoilage_Risk"]],
            color=["#fc8181","#f6ad55"],
        )

        with st.expander("📊 데이터 미리보기"):
            st.dataframe(
                df.style.map(lambda _: "font-weight:bold", subset=[temp_col]),
                use_container_width=True,
            )
