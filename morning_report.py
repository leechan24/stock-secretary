import requests
from bs4 import BeautifulSoup
import yfinance as yf
import os
import google.generativeai as genai
from pykrx import stock
from datetime import datetime, timedelta
import re

# 1. 환경 변수 설정 (GitHub Secrets)
api_key = os.getenv("GEMINI_API_KEY")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
naver_id = os.getenv("NAVER_CLIENT_ID")
naver_secret = os.getenv("NAVER_CLIENT_SECRET")

genai.configure(api_key=api_key)

# 2. 뉴스 검색 함수
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

# 3. 미국 및 한국 데이터 수집 (기존 로직 유지/강화)
def get_market_data():
    # 미국 섹터 데이터
    sectors = {"XLE": "에너지", "XLK": "IT/반도체", "XLI": "산업재", "XLF": "금융"}
    us_perf = []
    for s, name in sectors.items():
        hist = yf.Ticker(s).history(period="2d")
        chg = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
        us_perf.append(f"{name}({round(chg,2)}%)")
    
    # 한국 테마 리스트 (네이버 금융)
    res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    kr_themes = [a.text for a in soup.select('.col_type1 a')[:10]]
    
    return us_perf, kr_themes

# 4. 메인 실행 및 AI 분석
if __name__ == "__main__":
    us_perf, kr_themes = get_market_data()
    
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    너는 일타 주식 강사야. 아래 데이터를 보고 오늘 국장 급등 테마 2개를 선정해줘.
    결과는 반드시 텔레그램 HTML 형식으로 작성해.
    
    데이터: 미국({us_perf}), 한국테마({kr_themes})
    
    형식 예시:
    🚀 <b>[오늘의 원픽 테마]</b>
    <b>1. 테마명</b>
    - 근거: 내용
    - 대장주: 종목1, 종목2
    [NEWS_QUERY: 검색어]
    """
    
    response = model.generate_content(prompt).text
    
    # 뉴스 키워드 추출 및 치환
    final_report = response
    queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", response)
    for q in queries:
        news_text = get_naver_news(q)
        final_report = final_report.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>관련 뉴스:</b>\n{news_text}")

    # 텔레그램 전송
    full_msg = f"📅 <b>{datetime.now().strftime('%Y-%m-%d')} 프리미엄 브리핑</b>\n\n" + final_report
    requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                  json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML"})
    print("✅ 프리미엄 리포트 전송 완료!")
