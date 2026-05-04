import os
import requests
import json
import re
import time
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
import yfinance as yf
from dotenv import load_dotenv
from google import genai
import exchange_calendars as xcals  # 휴장일 체크용

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

# --- [추가] 국장 휴장 여부 확인 함수 ---
def is_kr_market_open():
    try:
        # 한국 거래소(XKRX) 달력 기준
        krx = xcals.get_calendar("XKRX")
        today = datetime.now().strftime("%Y-%m-%d")
        return krx.is_session(today)
    except:
        # 에러 발생 시 안전하게 '열림'으로 가정하거나 평일 여부로 판단
        return datetime.now().weekday() < 5

def save_to_history(date, picks, market_data, history_file="history.json"):
    """오늘의 마켓 지표와 추천 종목을 history.json에 통합 저장"""
    history_data = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except: history_data = []

    history_data = [item for item in history_data if item['date'] != date]
    
    history_data.append({
        "date": date,
        "market": market_data,
        "picks": picks
    })

    history_data.sort(key=lambda x: x['date'])

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
    print(f"📁 {date} 통합 데이터가 history.json에 기록되었습니다.")

def get_market_status():
    try:
        # 데이터 시점이 아닌 '오늘 리포트 발행일'을 기준으로 설정
        today_str = datetime.now().strftime("%Y-%m-%d")
        
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
            "date": today_str,
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
    print("🐭 쥐사장 분석기 가동!")
    
    market_open = is_kr_market_open()
    m = get_market_status()
    
    # 1. 미장 섹터 분석 (휴장 상관없이 수행)
    sectors = {"XLK": "반도체", "XLE": "에너지", "XLV": "바이오", "XLB": "소재", "XLI": "산업재"}
    us_perf = []
    for s, name in sectors.items():
        try:
            h = yf.Ticker(s).history(period="2d")
            c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
            us_perf.append(f"{name}({round(c,2)}%)")
        except: pass

    all_picks_for_history = []
    refined_themes = []

    # 2. 휴장일 여부에 따른 분기 처리
    if not market_open:
        report_header = f"🚩 <b>오늘은 국장 휴장일입니다.</b>\n"
        report_instruction = "오늘은 휴장일이니 매매는 쉬고, 미장 흐름을 통해 다음 전략을 구상해라."
        print("🚩 오늘은 휴장일입니다. 리포트만 생성하고 기록은 스킵합니다.")
    else:
        report_header = f"📅 <b>{m['date']} 프리미엄 브리핑</b>\n"
        report_instruction = "전일 종가를 기준으로 구체적인 가격([숫자]원)을 계산해서 전략을 제시해라."
        
        # 국장 데이터 수집 (장 열릴 때만 수행)
        try:
            res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
            theme_elements = soup.select('.col_type1 a')[:5]
            
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
                    
                    if isinstance(s_price, int):
                        all_picks_for_history.append({
                            "name": s_name, "code": s_code,
                            "base_price": s_price, "theme": theme_name
                        })
                refined_themes.append({"theme": theme_name, "stocks": stock_info})
        except:
            refined_themes = ["국장 데이터 로드 실패"]

    # 3. AI 분석 및 리포트 생성
    try:
        print(f"🤖 쥐사장 AI 분석 중...")
        prompt = f"""
        너는 대한민국 최고의 주식 일타강사 '쥐사장'이야. 
        [분석 데이터]
        1. 시장 지표: {m}
        2. 어제 미장 섹터 성적표: {us_perf}
        3. 오늘 국장 테마 및 종목: {refined_themes if market_open else '휴장'}

        [작성 지시]
        - {report_instruction}
        - 도입부: "🔥 <b>자, 우리 슈퍼개미 제자들! 쥐사장이야!</b>"
        - 📊 <b>미장/지표 브리핑:</b> 미장 성적과 지표 요약.
        - 마무리: "원칙 매매! 성투하시길 바랍니다.!"
        """
        
        response = client.models.generate_content(model="gemini-flash-latest", contents=prompt)
        report_content = response.text

        # 뉴스 매칭 (장 열릴 때만 수행)
        if market_open:
            queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_content)
            for q in queries:
                report_content = report_content.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>뉴스:</b>\n{get_naver_news(q)}")

        full_msg = report_header + report_content
        
        # 텔레그램 발송
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                      json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML", "disable_web_page_preview": True})
        
        # 4. 데이터 저장 (장 열릴 때만 수행하여 타율 왜곡 방지)
        if market_open:
            save_to_history(m['date'], all_picks_for_history, m)
            print("✨ 리포트 발송 및 통합 데이터 기록 완료!")
        else:
            print("✨ 휴장일 리포트 발송 완료 (기록 제외)")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")