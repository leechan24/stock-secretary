import os
import requests
import json
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
import yfinance as yf
from dotenv import load_dotenv
from google import genai

load_dotenv()

def clean_val(key):
    val = os.getenv(key, "")
    if not val: return ""
    return re.sub(r'[^a-zA-Z0-9:\-_]', '', val).strip()

api_key = clean_val("GEMINI_API_KEY")
telegram_token = clean_val("TELEGRAM_BOT_TOKEN")
telegram_chat_id = clean_val("TELEGRAM_CHAT_ID")
naver_id = clean_val("NAVER_CLIENT_ID")
naver_secret = clean_val("NAVER_CLIENT_SECRET")

client = genai.Client(api_key=api_key)

def get_market_status():
    try:
        df_fx = yf.Ticker("KRW=X").history(period="5d")
        df_vix = yf.Ticker("^VIX").history(period="5d")
        curr_rate = df_fx['Close'].iloc[-1]
        prev_rate = df_fx['Close'].iloc[-2]
        rate_chg = ((curr_rate - prev_rate) / prev_rate) * 100
        curr_vix = df_vix['Close'].iloc[-1]
        
        if rate_chg > 0.6 or curr_vix > 25:
            status, weight = "경계 🚨", "0%~5% (관망)"
        elif rate_chg > 0.2 or curr_vix > 20:
            status, weight = "주의 ⚠️", "10%~15% (방망이 짧게)"
        else:
            status, weight = "안정 ✅", "20%~40% (공격적 투자)"
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "usd_krw": round(curr_rate, 2),
            "rate_chg_pct": round(rate_chg, 2),
            "vix": round(curr_vix, 2),
            "status": status,
            "total_weight": weight
        }
    except:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "status": "확인불가", "usd_krw": 0, "vix": 0, "rate_chg_pct": 0, "total_weight": "데이터 확인 불가"}

def get_stock_price(ticker):
    try:
        import logging
        logging.getLogger('yfinance').disabled = True
        formatted_ticker = ticker if "." in ticker else f"{ticker}.KS"
        stock = yf.Ticker(formatted_ticker)
        hist = stock.history(period="1d", raise_errors=False)
        if hist.empty:
            stock = yf.Ticker(f"{ticker}.KQ")
            hist = stock.history(period="1d", raise_errors=False)
        if not hist.empty:
            return int(hist['Close'].iloc[-1])
    except: pass
    return "가격 확인 불가"

def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=3&sort=sim"
    headers = {"X-Naver-Client-Id": naver_id, "X-Naver-Client-Secret": naver_secret}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            items = res.json().get('items', [])
            return "\n".join([f"  • {re.sub('<[^>]*>', '', item['title'])}" for item in items])
    except: return "  • 뉴스를 불러오지 못했습니다."
    return "  • 관련 뉴스가 없습니다."

if __name__ == "__main__":
    print("🐭 쥐사장 분석기 통합 버전 가동!")
    m = get_market_status()
    
    # [추가] 미장 섹터 분석 로직 다시 부활!
    sectors = {"XLK": "반도체", "XLE": "에너지", "XLV": "바이오", "XLB": "소재", "XLI": "산업재"}
    us_perf = []
    for s, name in sectors.items():
        try:
            h = yf.Ticker(s).history(period="2d")
            c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
            us_perf.append(f"{name}({round(c,2)}%)")
        except: pass

    # 국장 테마 및 전일 종가 수집
    try:
        res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        theme_elements = soup.select('.col_type1 a')[:5]
        
        refined_themes = []
        for te in theme_elements:
            theme_name = te.text
            theme_url = "https://finance.naver.com" + te['href']
            t_res = requests.get(theme_url, headers={'User-Agent': 'Mozilla/5.0'})
            t_soup = BeautifulSoup(t_res.text, 'html.parser')
            stock_tags = t_soup.select('.name_area a')[:5]
            
            stock_info = []
            for s in stock_tags:
                s_name = s.text
                s_code = re.search(r'code=(\d+)', s['href']).group(1)
                s_price = get_stock_price(s_code)
                stock_info.append(f"{s_name}({s_code}): 전일종가 {s_price}원")
            
            refined_themes.append({"theme": theme_name, "stocks": stock_info})
    except:
        refined_themes = ["국장 데이터 로드 실패"]

    try:
        print(f"🤖 쥐사장 AI 분석 중... (안정화 모델 사용)")
        
        # 프롬프트에 미장 데이터(us_perf)를 명시적으로 전달!
        prompt = f"""
        너는 대한민국 최고의 주식 일타강사 '쥐사장'이야. 
        미장 섹터 흐름과 국장 테마/전일 종가 데이터를 매칭해서 1,000만 원 투자자용 리포트를 써라.

        [분석 데이터]
        1. 시장 지표: {m}
        2. 어제 미장 섹터 성적표: {us_perf}
        3. 오늘 국장 테마 및 종목별 전일 종가: {refined_themes}
        
        [작성 지시]
        - 도입부에서 미장 성적표를 언급하며 오늘의 전체적인 시장 분위기를 쥐사장 말투로 설명해.
        - 미장에서 강했던 섹터와 연관된 국장 테마가 있다면 '원픽'으로 우선 고려해.
        - 전략은 반드시 제공된 '전일 종가'를 기준으로 구체적인 가격([숫자]원)을 계산해서 제시해.
        - 테마별 대장주는 5개.
        - 텔레그램용 <b>, <i> 태그만 사용.
        - [NEWS_QUERY: 테마명] 태그 포함.

        [형식]
        - 도입부: "🔥 <b>자, 우리 슈퍼개미 제자들! 쥐사장이야!</b>"
        - 📊 <b>미장/지표 브리핑:</b> (미장 성적과 환율/VIX를 섞어서 짧고 굵게!)
        - <b>[오늘의 원픽/투픽 테마]:</b>
        - 전략 (전일 종가 기준 구체적 가격 포함)
        - [NEWS_QUERY: 테마명]
        - 마무리: "오늘도 원칙 매매! 성투하시길 바랍니다. 찍찍!"
        """
        
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt
        )
        report_content = response.text
        
        queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_content)
        for q in queries:
            report_content = report_content.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>뉴스:</b>\n{get_naver_news(q)}")

        full_msg = f"📅 <b>{m['date']} 프리미엄 브리핑</b>\n\n" + report_content
        telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"

        requests.post(telegram_url, json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML", "disable_web_page_preview": True})
        print("✨ 미장 흐름 반영 리포트 발송 완료!")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
