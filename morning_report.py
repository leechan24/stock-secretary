import requests
from bs4 import BeautifulSoup
import yfinance as yf
import os
import google.generativeai as genai
import json
import re
from datetime import datetime

# 1. 환경 변수 설정
api_key = os.getenv("GEMINI_API_KEY")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
naver_id = os.getenv("NAVER_CLIENT_ID")
naver_secret = os.getenv("NAVER_CLIENT_SECRET")

genai.configure(api_key=api_key)

# 2. 상대적 리스크 지표 분석 (최근 추세 기반)
def get_risk_indicators():
    print("📉 시장 변동성 분석 중...")
    try:
        df_fx = yf.Ticker("KRW=X").history(period="5d")
        df_vix = yf.Ticker("^VIX").history(period="5d")
        
        curr_rate = df_fx['Close'].iloc[-1]
        prev_rate = df_fx['Close'].iloc[-2]
        avg_rate = df_fx['Close'].mean()
        curr_vix = df_vix['Close'].iloc[-1]
        
        rate_chg_pct = ((curr_rate - prev_rate) / prev_rate) * 100
        
        risk_level = "안정 ✅"
        if rate_chg_pct > 0.4 or curr_vix > 22:
            risk_level = "주의 ⚠️"
        elif curr_rate > avg_rate * 1.03 or curr_vix > 28:
            risk_level = "경계 🚨"
            
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "usd_krw": round(curr_rate, 2),
            "rate_chg_pct": round(rate_chg_pct, 2),
            "vix": round(curr_vix, 2),
            "risk_level": risk_level
        }
    except:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "risk_level": "확인불가", "usd_krw": 0, "vix": 0, "rate_chg_pct": 0}

# 3. 네이버 뉴스 검색 함수
def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=3&sort=sim"
    headers = {"X-Naver-Client-Id": naver_id, "X-Naver-Client-Secret": naver_secret}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            items = res.json().get('items', [])
            return "\n".join([f"  • {re.sub('<[^>]*>', '', item['title'])}" for item in items])
    except:
        return "  • 관련 뉴스를 불러오지 못했습니다."
    return "  • 관련 뉴스가 없습니다."

# 4. JSON 저장 함수
def save_to_history(new_entry):
    file_path = "history.json"
    history = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: history = []
    history.append(new_entry)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

# 5. 메인 실행
if __name__ == "__main__":
    # 데이터 수집
    risk_info = get_risk_indicators()
    
    sectors = {"XLE": "에너지", "XLK": "IT/반도체", "XLI": "산업재", "XLV": "헬스케어"}
    us_perf = []
    for s, name in sectors.items():
        h = yf.Ticker(s).history(period="2d")
        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
        us_perf.append(f"{name}({round(c,2)}%)")
    
    res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    kr_themes = [a.text for a in soup.select('.col_type1 a')[:10]]

    # AI 분석 (가독성 및 양식 강화)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    너는 구독자 100만 명을 보유한 대한민국 최고의 주식 일타강사야. 
    아래 데이터를 분석해서 제자들에게 '돈이 되는' 리포트를 HTML 형식으로 써줘.
    
    데이터: 리스크({risk_info}), 미장({us_perf}), 국장테마({kr_themes})
    
    [작성 가이드]
    1. 도입부: "🔥 자, 우리 슈퍼개미를 꿈꾸는 제자 여러분!"으로 시작하며 아주 열정적이고 에너제틱하게 작성해.
    2. 시장 지표 정리: 환율, VIX, 미국 섹터 수익률을 아래 [지표 정리 양식]을 사용하여 한눈에 들어오게 정리해.
    3. 테마 분석: 오늘의 '원픽'과 '투픽' 테마를 선정하고, 분석 근거(3줄 이상)와 핵심 대장주 3개를 명확히 적어.
    4. 뉴스: 테마별로 반드시 [NEWS_QUERY: 검색어] 태그를 포함해.
    
    [지표 정리 양식]
    📊 <b>시장 주요 지표 요약</b>
    --------------------------------
    💰 <b>환율:</b> {risk_info['usd_krw']}원 (<b>{risk_info['rate_chg_pct']}%</b>)
    📉 <b>VIX:</b> {risk_info['vix']} (시장 심리: <b>{risk_info['risk_level']}</b>)
    🇺🇸 <b>미국 섹터별 흐름</b>
    • {us_perf[0]} | {us_perf[1]} | {us_perf[2]}
    --------------------------------
    
    [주의] <html>, <style>, <body> 태그 절대 금지! <b>, <i> 태그와 이모지만 사용할 것.
    """
    
    report_content = model.generate_content(prompt).text
    
    # 뉴스 키워드 치환
    queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_content)
    for q in queries:
        news_links = get_naver_news(q)
        report_content = report_content.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>관련 뉴스:</b>\n{news_links}")

    # JSON 데이터 저장
    history_entry = {
        "date": risk_info['date'],
        "risk_data": risk_info,
        "us_market": us_perf,
        "report": report_content
    }
    save_to_history(history_entry)

    # 텔레그램 전송
    full_msg = f"📅 <b>{risk_info['date']} 프리미엄 브리핑</b>\n\n" + report_content
    
    response = requests.post(
        f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
        json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    )
    
    # 실패 시 태그 제거 후 재시도 로직
    if response.status_code != 200:
        clean_msg = f"⚠️ [전송오류 복구 버전]\n" + re.sub('<[^>]*>', '', full_msg)
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                      json={"chat_id": telegram_chat_id, "text": clean_msg})

    print(f"✅ 리포트 전송 완료! (상태 코드: {response.status_code})")
