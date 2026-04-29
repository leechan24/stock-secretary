import requests
from bs4 import BeautifulSoup
import yfinance as yf
import os
import google.generativeai as genai
import json
import re
from datetime import datetime, timedelta

# 1. 환경 변수 설정
api_key = os.getenv("GEMINI_API_KEY")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
naver_id = os.getenv("NAVER_CLIENT_ID")
naver_secret = os.getenv("NAVER_CLIENT_SECRET")

genai.configure(api_key=api_key)

# 2. 상대적 리스크 지표 분석 (최근 추세 기반)
def get_risk_indicators():
    print("📉 시장 변동성 및 상대적 리스크 분석 중...")
    try:
        # 최근 5거래일 데이터 수집
        usd_krw_ticker = yf.Ticker("KRW=X")
        vix_ticker = yf.Ticker("^VIX")
        
        df_fx = usd_krw_ticker.history(period="5d")
        df_vix = vix_ticker.history(period="5d")
        
        curr_rate = df_fx['Close'].iloc[-1]
        prev_rate = df_fx['Close'].iloc[-2]
        avg_rate = df_fx['Close'].mean()
        curr_vix = df_vix['Close'].iloc[-1]
        
        # 등락률 및 변동성 계산
        rate_chg_pct = ((curr_rate - prev_rate) / prev_rate) * 100
        vix_chg_pct = ((curr_vix - df_vix['Close'].iloc[-2]) / df_vix['Close'].iloc[-2]) * 100
        
        # 리스크 레벨 판단 로직
        risk_level = "보통"
        risk_msg = "현재 시장은 정상적인 변동성 범위 내에 있습니다."
        
        if rate_chg_pct > 0.4 or curr_vix > 22:
            risk_level = "주의"
            risk_msg = "환율 또는 변동성 지수가 급격히 상승 중입니다. 방어적인 태세가 필요합니다."
        if curr_rate > avg_rate * 1.03 or curr_vix > 28:
            risk_level = "경계"
            risk_msg = "시장 심리가 급격히 위축되었습니다. 현금 비중 확보를 권장합니다."
            
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "usd_krw": round(curr_rate, 2),
            "rate_chg_pct": round(rate_chg_pct, 2),
            "vix": round(curr_vix, 2),
            "vix_chg_pct": round(vix_chg_pct, 2),
            "risk_level": risk_level,
            "risk_msg": risk_msg
        }
    except Exception as e:
        print(f"리스크 분석 오류: {e}")
        return {"risk_level": "데이터 확인 불가", "risk_msg": "지표 산출 중 오류가 발생했습니다."}

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

# 4. JSON 데이터 누적 저장 함수
def save_to_history(new_entry):
    file_path = "history.json"
    history = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []
    
    history.append(new_entry)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)
    print(f"💾 history.json 업데이트 완료 (누적 {len(history)}건)")

# 5. 시장 데이터 수집 (미국/한국)
def get_market_data():
    sectors = {"XLE": "에너지", "XLK": "IT/반도체", "XLI": "산업재", "XLB": "소재"}
    us_perf = []
    for s, name in sectors.items():
        hist = yf.Ticker(s).history(period="2d")
        chg = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
        us_perf.append(f"{name}({round(chg,2)}%)")
    
    res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    kr_themes = [a.text for a in soup.select('.col_type1 a')[:10]]
    
    return us_perf, kr_themes

# 6. 메인 실행
if __name__ == "__main__":
    risk_info = get_risk_indicators()
    us_perf, kr_themes = get_market_data()
    
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    너는 투자 전략가야. 아래 데이터를 보고 텔레그램 리포트를 HTML로 써줘.
    
    [데이터]
    - 시장 리스크: {risk_info}
    - 미국 섹터 흐름: {us_perf}
    - 국내 인기 테마: {kr_themes}
    
    [작성 가이드]
    1. 상단에 현재 리스크 레벨({risk_info['risk_level']})에 따른 투자 태세를 먼저 한 줄로 요약해줘.
    2. 국장 테마 2개를 선정하고 각각 분석 근거와 대장주를 적어줘.
    3. 각 테마 끝에 반드시 [NEWS_QUERY: 검색어]를 넣어줘.
    """
    
    report_content = model.generate_content(prompt).text
    
    # 뉴스 키워드 치환
    queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_content)
    for q in queries:
        news_links = get_naver_news(q)
        report_content = report_content.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>최신 뉴스:</b>\n{news_links}")

    # JSON 데이터 생성 및 저장
    history_entry = {
        "date": risk_info['date'],
        "risk_data": risk_info,
        "us_market": us_perf,
        "kr_themes": kr_themes,
        "report": report_content
    }
    save_to_history(history_entry)

    # 텔레그램 전송
    full_msg = f"🔔 <b>{risk_info['date']} 마켓 리스크 관리 브리핑</b>\n" + report_content
    requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                  json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML"})
    
    print("오늘의 브리핑 및 데이터 저장 완료!")
