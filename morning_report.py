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

# 2. 리스크 지표 수집 (환율 및 VIX)
def get_risk_indicators():
    print("📉 리스크 지표 분석 중...")
    try:
        # 환율(USD/KRW) 및 VIX(공포지수) 수집
        usd_krw = yf.Ticker("KRW=X").history(period="1d")['Close'].iloc[-1]
        vix = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
        
        status = "안정"
        if usd_krw > 1350 or vix > 22:
            status = "주의 (현금 비중 확대 및 보수적 접근)"
        
        return {
            "usd_krw": round(usd_krw, 2),
            "vix": round(vix, 2),
            "risk_status": status
        }
    except:
        return {"usd_krw": 0, "vix": 0, "risk_status": "데이터 확인 불가"}

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

# 4. JSON 데이터 저장 함수
def save_to_history(new_data):
    file_path = "history.json"
    history = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []
    
    history.append(new_data)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)
    print(f"💾 {file_path}에 데이터 누적 완료!")

# 5. 시장 데이터 수집 (미국 섹터 & 한국 테마)
def get_market_data():
    print("📊 시장 데이터 수집 중...")
    sectors = {"XLE": "에너지", "XLK": "IT/반도체", "XLI": "산업재", "XLY": "소비재"}
    us_perf = []
    for s, name in sectors.items():
        hist = yf.Ticker(s).history(period="2d")
        chg = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
        us_perf.append(f"{name}({round(chg,2)}%)")
    
    res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    kr_themes = [a.text for a in soup.select('.col_type1 a')[:10]]
    
    return us_perf, kr_themes

# 6. 메인 실행부
if __name__ == "__main__":
    try:
        # 데이터 수집
        risk = get_risk_indicators()
        us_perf, kr_themes = get_market_data()
        
        # AI 분석
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        prompt = f"""
        너는 베테랑 투자 전략가야. 아래 데이터를 보고 텔레그램 리포트를 HTML로 작성해줘.
        환율/리스크: {risk}
        미국섹터: {us_perf}
        한국테마: {kr_themes}

        작성 규칙:
        1. 리스크 상태를 최상단에 강조해서 적어줄 것.
        2. 급등 예상 테마 2개를 선정하고 각각 [NEWS_QUERY: 검색어]를 포함할 것.
        3. 말투는 친절하면서도 전문적으로.
        """
        
        report_text = model.generate_content(prompt).text
        
        # 뉴스 치환
        queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_text)
        for q in queries:
            news = get_naver_news(q)
            report_text = report_text.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>관련 뉴스:</b>\n{news}")

        # JSON 저장을 위한 데이터 구조 생성
        history_entry = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "risk": risk,
            "us_market": us_perf,
            "predicted_themes": kr_themes[:2], # AI가 뽑은 상위 테마 예시
            "raw_report": report_text
        }
        save_to_history(history_entry)

        # 텔레그램 전송
        final_msg = f"📅 <b>{history_entry['date']} 마켓 브리핑</b>\n\n" + report_text
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                      json={"chat_id": telegram_chat_id, "text": final_msg, "parse_mode": "HTML"})
        
        print("모든 작업이 완료되었습니다!")

    except Exception as e:
        print(f"❗ 오류 발생: {e}")
