"""
서울 날씨 기반 아이 케어 가이드 — 매일 Telegram으로 전송
------------------------------------------------------
필요한 환경 변수 (GitHub Secrets에 등록):
  OWM_API_KEY   : OpenWeatherMap API 키
  TELEGRAM_TOKEN: Telegram Bot 토큰
  CHAT_ID       : 메시지를 받을 Telegram chat_id

사용 API (모두 무료):
  - OpenWeatherMap Current Weather  : 기온, 날씨, 습도
  - OpenWeatherMap Air Pollution     : PM2.5, PM10
  - OpenWeatherMap UV Index          : 자외선 지수
"""

import os
import json
import datetime
import urllib.request
import urllib.parse

# ── 환경 변수 ──────────────────────────────────────────────
OWM_API_KEY    = os.environ["OWM_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]

# 서울 위도/경도
LAT, LON = 37.5665, 126.9780

# ── 유틸 함수 ──────────────────────────────────────────────
def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


# ── 1. 날씨 데이터 수집 ────────────────────────────────────

def get_weather() -> dict:
    """기온(최저/최고/현재), 날씨 상태, 습도"""
    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={LAT}&lon={LON}&appid={OWM_API_KEY}&units=metric&lang=kr&cnt=24"
    )
    data = fetch_json(url)
    items = data["list"]

    now = datetime.datetime.utcnow()
    today_items = [
        i for i in items
        if datetime.datetime.utcfromtimestamp(i["dt"]).date() == now.date()
    ]
    if not today_items:
        today_items = items[:8]  # fallback

    temps   = [i["main"]["temp"] for i in today_items]
    morning = next((i for i in today_items
                    if 6 <= datetime.datetime.utcfromtimestamp(i["dt"]).hour + 9 <= 10), today_items[0])
    noon    = next((i for i in today_items
                    if 11 <= datetime.datetime.utcfromtimestamp(i["dt"]).hour + 9 <= 15), today_items[min(3, len(today_items)-1)])
    evening = next((i for i in today_items
                    if 17 <= datetime.datetime.utcfromtimestamp(i["dt"]).hour + 9 <= 21), today_items[-1])

    # 날씨 상태 — 비·눈·흐림 여부 판단
    weather_desc = today_items[0]["weather"][0]["description"]
    weather_ids  = [i["weather"][0]["id"] for i in today_items]
    has_rain  = any(200 <= wid < 700 for wid in weather_ids)
    has_cloud = any(wid >= 800 for wid in weather_ids)

    if has_rain:
        condition = "비 또는 소나기"
    elif any(wid == 800 for wid in weather_ids):
        condition = "맑음"
    else:
        condition = "구름 많음"

    return {
        "temp_morning": round(morning["main"]["temp"]),
        "temp_noon"   : round(noon["main"]["temp"]),
        "temp_evening": round(evening["main"]["temp"]),
        "temp_min"    : round(min(temps)),
        "temp_max"    : round(max(temps)),
        "humidity"    : today_items[0]["main"]["humidity"],
        "condition"   : condition,
        "desc"        : weather_desc,
        "has_rain"    : has_rain,
    }


def get_air_quality() -> dict:
    """PM2.5, PM10 수치 및 한국 기준 등급"""
    url = (
        f"https://api.openweathermap.org/data/2.5/air_pollution"
        f"?lat={LAT}&lon={LON}&appid={OWM_API_KEY}"
    )
    data = fetch_json(url)
    comp = data["list"][0]["components"]
    pm25 = round(comp["pm2_5"], 1)
    pm10 = round(comp["pm10"], 1)

    # 한국 환경부 기준 등급
    def pm25_grade(v):
        if v <= 15:  return "좋음"
        if v <= 35:  return "보통"
        if v <= 75:  return "나쁨"
        return "매우나쁨"

    def pm10_grade(v):
        if v <= 30:  return "좋음"
        if v <= 80:  return "보통"
        if v <= 150: return "나쁨"
        return "매우나쁨"

    grade = pm25_grade(pm25)   # 전체 등급은 PM2.5 기준으로 표시
    return {"pm25": pm25, "pm10": pm10, "grade": grade}


def get_uv() -> dict:
    """자외선 지수 및 등급"""
    url = (
        f"https://api.openweathermap.org/data/2.5/uvi"
        f"?lat={LAT}&lon={LON}&appid={OWM_API_KEY}"
    )
    data = fetch_json(url)
    uvi = data["value"]

    def uv_grade(v):
        if v < 3:   return "낮음"
        if v < 6:   return "보통"
        if v < 8:   return "높음"
        if v < 11:  return "매우높음"
        return "위험"

    return {"uvi": round(uvi, 1), "grade": uv_grade(uvi)}


# ── 2. 보고서 작성 ─────────────────────────────────────────

def build_report(weather: dict, air: dict, uv: dict) -> str:
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = f"{now_kst.year}년 {now_kst.month}월 {now_kst.day}일 {weekdays[now_kst.weekday()]}요일"

    # 옷차림 조언
    max_t = weather["temp_max"]
    if max_t >= 28:
        clothing = "매우 더운 날씨입니다. 반팔·반바지에 모자를 꼭 씌워주세요. 아이스팩이나 쿨 타월도 챙기면 좋아요."
    elif max_t >= 23:
        clothing = f"낮 최고 {max_t}°C의 초여름 날씨입니다. 아침에는 얇은 가디건, 낮에는 반팔·반바지가 적당해요. 모자는 필수입니다."
    elif max_t >= 18:
        clothing = f"낮 {max_t}°C로 선선합니다. 긴소매 티셔츠에 얇은 점퍼를 준비하고, 아침저녁엔 한 겹 더 입혀주세요."
    else:
        clothing = f"쌀쌀한 날씨입니다. 두꺼운 겉옷과 내복을 챙겨주세요."

    if weather["has_rain"]:
        clothing += " 우산·우비도 반드시 챙겨주세요."

    # 활동 추천
    bad_air = air["grade"] in ("나쁨", "매우나쁨")
    if bad_air:
        outdoor = f"미세먼지 {air['grade']} 수준으로 실외 활동은 자제하세요. 부득이 외출 시 KF94 마스크를 착용해 주세요."
    elif weather["has_rain"]:
        outdoor = "비가 예상되니 오전 중 잠깐 실외 활동 후 실내로 들어오는 것을 권장해요."
    else:
        outdoor = "맑고 공기가 좋아요. 공원이나 놀이터에서 뛰어노는 시간을 충분히 가져보세요."

    indoor = "집에서 색종이 접기나 그림 그리기 — 집중력과 소근육 발달에 도움이 됩니다."

    # 건강 포인트
    health_points = []
    if uv["grade"] in ("높음", "매우높음", "위험"):
        health_points.append(f"☀️ *자외선 {uv['grade']}* — 외출 전 SPF 30+ 자외선 차단제를 발라주고, 모자·양산을 활용하세요.")
    if bad_air:
        health_points.append(f"😷 *미세먼지 {air['grade']}* — 외출 시 마스크 필수, 귀가 후 손·발·얼굴을 바로 씻겨주세요.")
    if weather["has_rain"]:
        health_points.append("🌧️ *비* — 비에 젖으면 즉시 옷을 갈아입혀 체온 저하를 막아주세요.")
    if not health_points:
        health_points.append("오늘은 특별한 주의사항이 없어요. 아이와 즐거운 하루 보내세요! 😊")

    # 육아 팁 (계절별)
    month = now_kst.month
    if month in (6, 7, 8):
        tip = "여름철엔 수분 보충이 중요해요. 외출 전후로 물이나 보리차를 한 컵씩 마시게 해주세요."
    elif month in (9, 10, 11):
        tip = "환절기엔 실내외 온도차에 주의하세요. 얇은 겉옷을 가방에 넣어 다니면 유용합니다."
    elif month in (12, 1, 2):
        tip = "건조한 겨울, 가습기나 젖은 수건으로 실내 습도를 40~60%로 유지해 주세요."
    else:
        tip = "봄철 꽃가루가 많으니 창문을 닫아두고 외출 후 옷을 털어주세요."

    health_str = "\n".join(health_points)

    report = f"""# 🌤 오늘의 아이 케어 가이드 — {date_str}

## 📍 오늘 서울 환경
| 항목 | 수치 |
|---|---|
| 기온 | 아침 {weather['temp_morning']}°C / 낮 {weather['temp_noon']}°C / 저녁 {weather['temp_evening']}°C |
| 날씨 | {weather['condition']} |
| 미세먼지 | PM2.5: {air['pm25']}㎍/㎥ / PM10: {air['pm10']}㎍/㎥ ({air['grade']}) |
| 자외선 | {uv['uvi']} ({uv['grade']}) |
| 습도 | {weather['humidity']}% |

## 👕 오늘 옷차림
{clothing}

## 🏃 오늘 활동 추천
- 실외: {outdoor}
- 실내: {indoor}

## ⚠️ 오늘 건강 포인트
{health_str}

## 💡 오늘의 육아 팁
{tip}"""

    return report


# ── 3. Telegram 전송 ───────────────────────────────────────

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id"   : CHAT_ID,
        "text"      : text,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                print("✅ Telegram 전송 성공")
            else:
                print(f"⚠️ Telegram 오류: {result}")
    except Exception as e:
        # Markdown 파싱 실패 시 plain text로 재시도
        print(f"Markdown 전송 실패 ({e}), plain text로 재시도...")
        payload2 = json.dumps({"chat_id": CHAT_ID, "text": text}).encode("utf-8")
        req2 = urllib.request.Request(url, data=payload2,
                                       headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            print("✅ Plain text 전송 성공")


# ── 메인 ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("📡 날씨 데이터 수집 중...")
    weather = get_weather()
    air     = get_air_quality()
    uv      = get_uv()

    print("📝 보고서 작성 중...")
    report = build_report(weather, air, uv)
    print(report)

    print("📨 Telegram 전송 중...")
    send_telegram(report)
