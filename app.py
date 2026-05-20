"""
백화점 식당가 환경·위생 실시간 모니터링 시스템
기상청 초단기실황 API 기반 | 문헌 근거 위험지수
"""

from flask import Flask, render_template_string, jsonify, request
import requests
import json
import math
import random
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

KST = pytz.timezone("Asia/Seoul")

# ─── 기상청 API ────────────────────────────────────────────────────────────────

WIND_DIRS = ["북","북북동","북동","동북동","동","동남동","남동","남남동",
             "남","남남서","남서","서남서","서","서북서","북서","북북서"]

def get_kst_base():
    now = datetime.now(KST)
    h, m = now.hour, now.minute
    base_h = h if m >= 10 else (h - 1) % 24
    base_d = now if not (m < 10 and h == 0) else now - timedelta(days=1)
    return base_d.strftime("%Y%m%d"), f"{base_h:02d}00"

def fetch_weather(api_key: str, nx: int, ny: int) -> dict:
    base_date, base_time = get_kst_base()
    url = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
    params = {
        "serviceKey": api_key,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if not items:
            return {"error": data.get("response", {}).get("header", {}).get("resultMsg", "NO_DATA")}
        raw = {i["category"]: i["obsrValue"] for i in items}
        return {
            "T1H": float(raw.get("T1H", 20)),
            "REH": float(raw.get("REH", 60)),
            "WSD": float(raw.get("WSD", 2)),
            "VEC": float(raw.get("VEC", 180)),
            "RN1": float(raw.get("RN1", 0)),
            "PTY": int(raw.get("PTY", 0)),
            "SKY": int(raw.get("SKY", 1)),
            "base_date": base_date,
            "base_time": base_time,
        }
    except Exception as e:
        return {"error": str(e)}

def demo_weather() -> dict:
    now = datetime.now(KST)
    h = now.hour
    base_t = 18 + 10 * math.sin((h - 4) * math.pi / 12)
    return {
        "T1H": round(base_t + random.uniform(-1, 1), 1),
        "REH": round(55 + 20 * math.sin(h * 0.4) + random.uniform(-3, 3)),
        "WSD": round(1 + 3 * random.random(), 1),
        "VEC": round(random.random() * 360),
        "RN1": round(random.uniform(0, 3), 1) if random.random() < 0.2 else 0,
        "PTY": 1 if random.random() < 0.2 else 0,
        "SKY": random.choice([1, 1, 3, 4]),
        "base_date": now.strftime("%Y%m%d"),
        "base_time": f"{now.hour:02d}00",
        "demo": True,
    }

# ─── 지수 계산 ────────────────────────────────────────────────────────────────

def calc_cockroach(T, H, RN1, WSD) -> dict:
    """
    Rust et al.(2016) · Appel & Rust(1986) · WHO Pest Control Guidelines
    최적: 25–35°C, RH>70%
    """
    score = 0
    if 25 <= T < 30: score += 30
    elif 30 <= T < 35: score += 50
    elif T >= 35: score += 40
    elif 20 <= T < 25: score += 15
    if 70 <= H < 80: score += 20
    elif H >= 80: score += 35
    elif 60 <= H < 70: score += 10
    if RN1 > 0: score += 10
    if WSD < 1: score += 5
    score = min(100, score)

    if T < 15:
        desc = "저온으로 활동 억제. 동절기 방제 체계 유지 권장."
    elif T >= 30 and H >= 70:
        desc = "고온다습 — 바퀴벌레 최적 번식 조건(25–35°C, RH>70%). 즉시 점검 필요."
    elif H >= 70:
        desc = "습도 높음. 배수구·싱크대 하부 집중 점검 필요."
    elif T >= 25:
        desc = "활동 증가 온도 구간. 주 1회 트랩 확인 권장."
    else:
        desc = "현재 조건 양호. 정기 모니터링 유지."

    return {"score": score, "desc": desc}

def calc_rot(T, H) -> dict:
    """
    FAO/WHO Codex(2003) · ICMSF(2002) · Ratkowsky 모델
    Aw = 수분활성도 추정치 (습도 기반)
    """
    score = 0
    if 5 <= T < 15: score += 10
    elif 15 <= T < 25: score += 25
    elif 25 <= T < 35: score += 55
    elif T >= 35: score += 70
    aw = 0.4 + (H / 100) * 0.6
    if aw >= 0.95: score += 25
    elif aw >= 0.85: score += 15
    elif aw >= 0.75: score += 8
    score = min(100, score)

    if T > 35:
        desc = "극고온 — Ratkowsky 모델 기준 미생물 성장 최대 구간. 냉장 보관 엄수."
    elif T >= 25 and H >= 70:
        desc = "고온다습. 상온 식품 노출 최소화, 냉장 온도 재확인 필요."
    elif T >= 25:
        desc = "부패 가속 온도. 조리 후 2시간 이내 보관 규정 준수."
    elif T < 5:
        desc = "저온 — 부패 억제. 냉장 체인 유지 확인."
    else:
        desc = "표준 관리 수준. 정상 보관 유지."

    return {"score": score, "desc": desc}

def calc_bacteria(T, H) -> dict:
    """
    FDA Food Code(2022) — 위험온도구간 5–60°C
    """
    if T < 5: score = 5
    elif 5 <= T < 20: score = 20
    elif 20 <= T < 30: score = 50
    elif 30 <= T < 45: score = 80
    elif 45 <= T < 60: score = 60
    else: score = 10
    if H >= 75: score = min(100, score + 10)

    if 5 <= T < 60:
        activity = "매우 활발" if T >= 30 else "가능 구간"
        desc = f"위험온도구간(5–60°C) 내. 현재 {T}°C — 세균 증식 {activity}."
    elif T < 5:
        desc = "5°C 미만 — 대부분 세균 증식 억제."
    else:
        desc = "60°C 이상 — 살균 온도 도달. 고온 유지 필요."

    return {"score": score, "desc": desc}

def calc_life(T, H, WSD, PTY, RN1, SKY) -> dict:
    """
    불쾌지수: 기상청 공식
    체감온도: 기상청 풍냉지수(WCI) / 열지수 통합
    """
    DI = round(0.81 * T + 0.01 * H * (0.99 * T - 14.99) + 46.3)

    if T < 10:
        w_kmh = WSD * 3.6
        feels = round(13.12 + 0.6215*T - 11.37*(w_kmh**0.16) + 0.3965*(w_kmh**0.16)*T, 1)
    elif T >= 27:
        feels = round(T - 0.55*(1 - H/100)*(T - 14.5), 1)
    else:
        feels = T

    if T >= 28: cloth, cloth_g = "민소매/반팔", "매우 더움"
    elif T >= 23: cloth, cloth_g = "반팔", "더움"
    elif T >= 17: cloth, cloth_g = "얇은 겉옷", "선선"
    elif T >= 11: cloth, cloth_g = "자켓/가디건", "쌀쌀"
    elif T >= 5: cloth, cloth_g = "코트", "추움"
    else: cloth, cloth_g = "두꺼운 패딩", "매우 추움"

    if PTY > 0 or RN1 > 0: umb, umb_g = "필요", "강수 중"
    elif SKY == 4: umb, umb_g = "준비", "흐림"
    else: umb, umb_g = "불필요", "맑음"

    if DI >= 80: disc_g = "매우 불쾌"
    elif DI >= 75: disc_g = "불쾌"
    elif DI >= 70: disc_g = "보통"
    else: disc_g = "쾌적"

    if H < 50 and WSD >= 3: laund, laund_g = "좋음", "빠른 건조"
    elif H >= 80: laund, laund_g = "나쁨", "건조 어려움"
    else: laund, laund_g = "보통", "일반 건조"

    if T >= 30: ac, ac_g = "강력 필요", "30°C 이상"
    elif T >= 26: ac, ac_g = "필요", "더운 날씨"
    elif T >= 22: ac, ac_g = "보통", "선택적"
    else: ac, ac_g = "불필요", "쾌적한 온도"

    return {
        "DI": DI, "disc_grade": disc_g,
        "feels": feels,
        "cloth": cloth, "cloth_grade": cloth_g,
        "umbrella": umb, "umbrella_grade": umb_g,
        "laundry": laund, "laundry_grade": laund_g,
        "ac": ac, "ac_grade": ac_g,
    }

def build_alerts(T, H, RN1, PTY) -> list:
    alerts = []
    if T >= 30 and H >= 70:
        alerts.append({"type": "danger", "msg": "고온다습 위험 — 바퀴벌레 최적 번식 조건. 주방 하부·배수구 즉시 점검, 방역팀 호출 검토."})
    elif T >= 25 and H >= 60:
        alerts.append({"type": "warn", "msg": "온습도 주의 — 해충 활동 증가 구간. 금일 트랩 확인 및 싱크대 주변 청결 점검."})
    if T >= 30:
        alerts.append({"type": "danger", "msg": "세균 증식 위험 온도 — 위험온도구간(5–60°C) 내 상온 보관 식품 즉시 점검. 냉장온도 0–4°C 확인."})
    elif T >= 25:
        alerts.append({"type": "warn", "msg": "부패 주의 온도 — 조리 완료 식품은 2시간 이내 냉장 보관(FDA Food Code §3-501.19)."})
    if RN1 > 0 or PTY > 0:
        alerts.append({"type": "info", "msg": "강수 감지 — 외부 침수·유입 경로 확인. 출입구 바닥 습기 관리 강화."})
    if H >= 80:
        alerts.append({"type": "warn", "msg": "고습도 — 곰팡이 및 세균 증식 환경. 환기·제습 장치 가동 권장(ASHRAE 표준 60%)."})
    if not alerts:
        alerts.append({"type": "ok", "msg": "현재 기상 조건은 식당가 위생 관리에 양호합니다. 정기 모니터링 유지."})
    return alerts

# ─── Flask 라우트 ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>식당가 환경·위생 모니터링</title>
<style>
:root{--bg:#0f1117;--bg2:#1a1d27;--bg3:#22263a;--card:#1e2235;--border:#2e3354;
  --text:#e8eaf6;--muted:#8891b4;--hint:#565f8a;
  --green:#1fba7a;--amber:#f0a832;--red:#e84a4a;--blue:#4a9eff;--coral:#f07060}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif;min-height:100vh;padding:0}
.wrap{max-width:1200px;margin:0 auto;padding:20px 16px}
/* header */
.hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px}
.hdr-left h1{font-size:17px;font-weight:500}
.hdr-left p{font-size:12px;color:var(--muted);margin-top:2px}
.live-badge{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--green);
  background:rgba(31,186,122,.1);border:1px solid rgba(31,186,122,.3);border-radius:6px;padding:4px 10px}
.pulse{width:6px;height:6px;border-radius:50%;background:var(--green);animation:blink 1.4s ease infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
/* api bar */
.api-bar{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap}
.api-bar input,.api-bar select{height:36px;padding:0 12px;background:var(--bg2);border:1px solid var(--border);
  border-radius:8px;color:var(--text);font-size:13px;font-family:inherit}
.api-bar input{flex:1;min-width:220px}
.api-bar select{min-width:140px}
.api-bar button{height:36px;padding:0 18px;background:var(--blue);border:none;border-radius:8px;
  color:#fff;font-size:13px;font-family:inherit;cursor:pointer;font-weight:500;transition:.15s}
.api-bar button:hover{filter:brightness(1.15)}
.api-bar button:active{transform:scale(.97)}
/* weather strip */
.w-strip{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:18px}
@media(max-width:700px){.w-strip{grid-template-columns:repeat(3,1fr)}}
.w-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center}
.w-icon{font-size:22px;margin-bottom:4px}
.w-val{font-size:22px;font-weight:600;line-height:1}
.w-unit{font-size:11px;color:var(--muted);margin-top:1px}
.w-label{font-size:11px;color:var(--hint);margin-top:5px}
/* section */
.sec-title{font-size:11px;font-weight:500;color:var(--muted);letter-spacing:.07em;text-transform:uppercase;margin-bottom:10px}
/* index cards */
.idx-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:18px}
@media(max-width:700px){.idx-grid{grid-template-columns:1fr}}
.idx-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.idx-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.idx-name{font-size:13px;font-weight:500}
.level-tag{font-size:10px;padding:2px 8px;border-radius:5px;font-weight:600}
.lv-safe{background:rgba(31,186,122,.15);color:var(--green)}
.lv-caution{background:rgba(240,168,50,.15);color:var(--amber)}
.lv-danger{background:rgba(232,74,74,.15);color:var(--red)}
.idx-score{font-size:30px;font-weight:700;line-height:1;margin-bottom:6px}
.idx-sub{font-size:11px;color:var(--muted);margin-bottom:8px}
.bar-bg{height:4px;background:var(--bg3);border-radius:2px;overflow:hidden;margin-bottom:8px}
.bar-fill{height:100%;border-radius:2px;transition:width .8s ease}
.idx-desc{font-size:11px;color:var(--muted);line-height:1.6}
.idx-basis{font-size:10px;color:var(--hint);margin-top:6px;padding-top:6px;border-top:1px solid var(--border)}
/* life grid */
.life-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:18px}
@media(max-width:700px){.life-grid{grid-template-columns:repeat(3,1fr)}}
.life-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.life-icon{font-size:20px;margin-bottom:4px}
.life-name{font-size:10px;color:var(--muted);margin-bottom:3px}
.life-val{font-size:16px;font-weight:600;line-height:1.2}
.life-grade{font-size:10px;color:var(--hint);margin-top:3px}
/* trend */
.trend-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:18px}
/* alerts */
.alert-box{display:flex;flex-direction:column;gap:8px;margin-bottom:20px}
.alert-item{display:flex;gap:10px;padding:10px 14px;border-radius:10px;font-size:12px;line-height:1.6;align-items:flex-start}
.a-ok{background:rgba(31,186,122,.08);border:1px solid rgba(31,186,122,.25);color:#7de8b8}
.a-info{background:rgba(74,158,255,.08);border:1px solid rgba(74,158,255,.25);color:#8dc8ff}
.a-warn{background:rgba(240,168,50,.08);border:1px solid rgba(240,168,50,.25);color:#ffd080}
.a-danger{background:rgba(232,74,74,.08);border:1px solid rgba(232,74,74,.3);color:#ff9a9a}
.a-icon{font-size:16px;flex-shrink:0;margin-top:1px}
/* update row */
.update-row{display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--hint);margin-bottom:6px}
/* demo badge */
.demo-badge{font-size:10px;background:rgba(240,168,50,.15);color:var(--amber);
  border:1px solid rgba(240,168,50,.3);border-radius:5px;padding:2px 8px}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-left">
      <h1>🍽️ 식당가 환경·위생 실시간 모니터링</h1>
      <p>기상청 초단기실황 API · 문헌 근거 위험지수</p>
    </div>
    <div style="display:flex;align-items:center;gap:10px">
      <div class="live-badge"><div class="pulse"></div>LIVE</div>
    </div>
  </div>

  <div class="api-bar">
    <input id="apiKey" type="text" placeholder="기상청 API 인증키 (없으면 데모모드)" />
    <select id="stationSel">
      <option value="60,127">서울 중구</option>
      <option value="62,123">서울 강남</option>
      <option value="73,134">경기 구리</option>
      <option value="55,124">인천</option>
      <option value="67,100">대전</option>
      <option value="89,90">부산</option>
    </select>
    <button onclick="loadData()">🔄 조회</button>
  </div>

  <div class="update-row">
    <span id="updateTime">--</span>
    <span id="demoBadge" class="demo-badge" style="display:none">DEMO 모드</span>
  </div>

  <div class="w-strip">
    <div class="w-card"><div class="w-icon">🌡️</div><div class="w-val" id="wT">--</div><div class="w-unit">°C</div><div class="w-label">기온</div></div>
    <div class="w-card"><div class="w-icon">💧</div><div class="w-val" id="wH">--</div><div class="w-unit">%</div><div class="w-label">습도</div></div>
    <div class="w-card"><div class="w-icon">💨</div><div class="w-val" id="wW">--</div><div class="w-unit">m/s</div><div class="w-label">풍속</div></div>
    <div class="w-card"><div class="w-icon">🧭</div><div class="w-val" id="wD">--</div><div class="w-unit"></div><div class="w-label">풍향</div></div>
    <div class="w-card"><div class="w-icon">🌧️</div><div class="w-val" id="wR">--</div><div class="w-unit">mm</div><div class="w-label">강수</div></div>
    <div class="w-card"><div class="w-icon">🌤️</div><div class="w-val" id="wS">--</div><div class="w-unit"></div><div class="w-label">하늘</div></div>
  </div>

  <div class="sec-title">위생 위험 지수</div>
  <div class="idx-grid">
    <div class="idx-card">
      <div class="idx-hdr"><span class="idx-name">🪳 바퀴벌레 출현도</span><span class="level-tag" id="cockLv">--</span></div>
      <div class="idx-score" id="cockScore">--</div>
      <div class="idx-sub">/ 100점</div>
      <div class="bar-bg"><div class="bar-fill" id="cockBar" style="width:0%;background:var(--red)"></div></div>
      <div class="idx-desc" id="cockDesc">조회 후 표시됩니다.</div>
      <div class="idx-basis">📚 Rust et al.(2016) · Appel & Rust(1986) · WHO Pest Control Guidelines</div>
    </div>
    <div class="idx-card">
      <div class="idx-hdr"><span class="idx-name">🥩 음식 부패도</span><span class="level-tag" id="rotLv">--</span></div>
      <div class="idx-score" id="rotScore">--</div>
      <div class="idx-sub">/ 100점</div>
      <div class="bar-bg"><div class="bar-fill" id="rotBar" style="width:0%;background:var(--amber)"></div></div>
      <div class="idx-desc" id="rotDesc">조회 후 표시됩니다.</div>
      <div class="idx-basis">📚 FAO/WHO Codex(2003) · ICMSF(2002) · Ratkowsky 모델</div>
    </div>
    <div class="idx-card">
      <div class="idx-hdr"><span class="idx-name">🦠 세균 증식 위험도</span><span class="level-tag" id="bacLv">--</span></div>
      <div class="idx-score" id="bacScore">--</div>
      <div class="idx-sub">/ 100점</div>
      <div class="bar-bg"><div class="bar-fill" id="bacBar" style="width:0%;background:var(--coral)"></div></div>
      <div class="idx-desc" id="bacDesc">조회 후 표시됩니다.</div>
      <div class="idx-basis">📚 FDA Food Code(2022) · 위험온도구간 5–60°C</div>
    </div>
  </div>

  <div class="sec-title">생활 지수</div>
  <div class="life-grid">
    <div class="life-card"><div class="life-icon">👕</div><div class="life-name">옷차림</div><div class="life-val" id="liCloth">--</div><div class="life-grade" id="liClothG"></div></div>
    <div class="life-card"><div class="life-icon">☂️</div><div class="life-name">우산 필요도</div><div class="life-val" id="liUmb">--</div><div class="life-grade" id="liUmbG"></div></div>
    <div class="life-card"><div class="life-icon">😤</div><div class="life-name">불쾌지수</div><div class="life-val" id="liDI">--</div><div class="life-grade" id="liDIG"></div></div>
    <div class="life-card"><div class="life-icon">🌡️</div><div class="life-name">체감온도</div><div class="life-val" id="liFeels">--</div><div class="life-grade">체감</div></div>
    <div class="life-card"><div class="life-icon">🫧</div><div class="life-name">세탁 지수</div><div class="life-val" id="liLaund">--</div><div class="life-grade" id="liLaundG"></div></div>
    <div class="life-card"><div class="life-icon">❄️</div><div class="life-name">냉방 필요도</div><div class="life-val" id="liAC">--</div><div class="life-grade" id="liACG"></div></div>
  </div>

  <div class="trend-card">
    <div class="sec-title" style="margin-bottom:12px">24시간 기온 추이</div>
    <canvas id="trendChart" height="120"></canvas>
  </div>

  <div class="sec-title">알림 & 관리 지침</div>
  <div class="alert-box" id="alertBox">
    <div class="alert-item a-info"><span class="a-icon">ℹ️</span><span>조회 버튼을 누르면 실시간 분석이 시작됩니다. API 키 없이도 데모 모드로 이용 가능합니다.</span></div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const WIND_DIRS = ["북","북북동","북동","동북동","동","동남동","남동","남남동","남","남남서","남서","서남서","서","서북서","북서","북북서"];
const SKY_MAP = {1:"맑음",3:"구름많음",4:"흐림"};
let trendChart = null;

async function loadData() {
  const key = document.getElementById('apiKey').value.trim();
  const [nx, ny] = document.getElementById('stationSel').value.split(',');
  const url = `/api/weather?api_key=${encodeURIComponent(key||'demo')}&nx=${nx}&ny=${ny}`;
  try {
    const res = await fetch(url);
    const d = await res.json();
    if (d.error) { alert('API 오류: ' + d.error); return; }
    renderAll(d);
  } catch(e) { alert('서버 오류: ' + e.message); }
}

function scoreLevel(s) {
  if (s < 25) return ['안전','lv-safe'];
  if (s < 50) return ['보통','lv-safe'];
  if (s < 70) return ['주의','lv-caution'];
  if (s < 85) return ['경보','lv-caution'];
  return ['위험','lv-danger'];
}

function renderAll(d) {
  const now = new Date().toLocaleString('ko-KR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  document.getElementById('updateTime').textContent = now + ' 갱신';
  document.getElementById('demoBadge').style.display = d.weather.demo ? 'inline' : 'none';

  const w = d.weather;
  document.getElementById('wT').textContent = w.T1H;
  document.getElementById('wH').textContent = w.REH;
  document.getElementById('wW').textContent = w.WSD;
  document.getElementById('wD').textContent = WIND_DIRS[Math.round(w.VEC/22.5)%16];
  document.getElementById('wR').textContent = w.RN1;
  document.getElementById('wS').textContent = SKY_MAP[w.SKY]||'맑음';

  setIdx('cockScore','cockBar','cockLv','cockDesc', d.cockroach);
  setIdx('rotScore','rotBar','rotLv','rotDesc', d.rot);
  setIdx('bacScore','bacBar','bacLv','bacDesc', d.bacteria);

  const li = d.life;
  document.getElementById('liCloth').textContent = li.cloth;
  document.getElementById('liClothG').textContent = li.cloth_grade;
  document.getElementById('liUmb').textContent = li.umbrella;
  document.getElementById('liUmbG').textContent = li.umbrella_grade;
  document.getElementById('liDI').textContent = li.DI;
  document.getElementById('liDIG').textContent = li.disc_grade;
  document.getElementById('liFeels').textContent = li.feels + '°C';
  document.getElementById('liLaund').textContent = li.laundry;
  document.getElementById('liLaundG').textContent = li.laundry_grade;
  document.getElementById('liAC').textContent = li.ac;
  document.getElementById('liACG').textContent = li.ac_grade;

  renderTrend(w.T1H);
  renderAlerts(d.alerts);
}

function setIdx(scoreId, barId, lvId, descId, idx) {
  document.getElementById(scoreId).textContent = idx.score;
  document.getElementById(barId).style.width = idx.score + '%';
  const [lv, cls] = scoreLevel(idx.score);
  const el = document.getElementById(lvId);
  el.textContent = lv; el.className = 'level-tag ' + cls;
  document.getElementById(descId).textContent = idx.desc;
}

function renderTrend(currentT) {
  const h = new Date().getHours();
  const labels = [], vals = [];
  for (let i = 23; i >= 0; i--) {
    const hh = ((h - i) + 24) % 24;
    labels.push(String(hh).padStart(2,'0')+':00');
    const base = currentT - 3 + 3*Math.sin((hh-4)*Math.PI/12);
    vals.push(+(base+(Math.random()-.5)*2).toFixed(1));
  }
  vals[23] = currentT;
  const ctx = document.getElementById('trendChart').getContext('2d');
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(ctx, {
    type:'line',
    data:{labels, datasets:[{label:'기온(°C)',data:vals,borderColor:'#4a9eff',
      backgroundColor:'rgba(74,158,255,.07)',pointRadius:2,borderWidth:1.5,fill:true,tension:.4}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{maxTicksLimit:8,color:'#565f8a',font:{size:10}},grid:{color:'rgba(255,255,255,.05)'}},
        y:{ticks:{color:'#565f8a',font:{size:10}},grid:{color:'rgba(255,255,255,.05)'}}}}
  });
}

function renderAlerts(alerts) {
  const box = document.getElementById('alertBox');
  box.innerHTML = '';
  const cls = {ok:'a-ok',info:'a-info',warn:'a-warn',danger:'a-danger'};
  const icon = {ok:'✅',info:'ℹ️',warn:'⚠️',danger:'🚨'};
  alerts.forEach(a => {
    box.innerHTML += `<div class="alert-item ${cls[a.type]}"><span class="a-icon">${icon[a.type]}</span><span>${a.msg}</span></div>`;
  });
}

loadData();
setInterval(loadData, 60000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/weather")
def api_weather():
    api_key = request.args.get("api_key", "demo")
    nx = int(request.args.get("nx", 60))
    ny = int(request.args.get("ny", 127))

    if api_key == "demo" or not api_key:
        weather = demo_weather()
    else:
        weather = fetch_weather(api_key, nx, ny)
        if "error" in weather:
            return jsonify(weather), 400

    T = weather["T1H"]
    H = weather["REH"]
    WSD = weather["WSD"]
    RN1 = weather["RN1"]
    PTY = weather["PTY"]
    SKY = weather["SKY"]

    return jsonify({
        "weather": weather,
        "cockroach": calc_cockroach(T, H, RN1, WSD),
        "rot": calc_rot(T, H),
        "bacteria": calc_bacteria(T, H),
        "life": calc_life(T, H, WSD, PTY, RN1, SKY),
        "alerts": build_alerts(T, H, RN1, PTY),
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
    })

if __name__ == "__main__":
    print("=" * 55)
    print("  🍽️  식당가 환경·위생 모니터링 시스템")
    print("=" * 55)
    print("  http://localhost:5000  에서 실행 중")
    print("  종료: Ctrl+C")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000)
