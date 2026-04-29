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

# 2. 상대적 리스크 지표 분석
def get_risk_indicators():
    print("📉 리스크 분석 중...")
    try:
        df_fx = yf.Ticker("KRW=X").history(period="5d")
        df_vix = yf.Ticker("^VIX").history(period="5d")
        
        curr_rate = df_fx['Close'].iloc[-1]
        prev_rate = df_fx['Close'].iloc[-2]
        avg_rate = df_fx['Close'].mean()
        curr_vix = df_vix['Close'].iloc[-1]
        
        rate_chg_pct = ((curr_rate - prev_rate) / prev_rate) * 100
        
        risk_level = "보통"
        if rate_chg_pct > 0.4 or curr_vix > 22:
            risk_level = "주의"
        elif curr_rate > avg_rate * 1.03 or curr_vix > 28:
            risk_level = "경계"
            
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "usd_krw": round(curr_rate, 2),
            "rate_chg_pct": round(rate_chg_pct, 2),
            "vix": round(curr_vix, 2),
            "risk_level": risk_level
        }
    except:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "risk_level": "확인불가", "usd_krw": 0, "vix": 0}

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
    risk_info = get_risk_indicators()
    
    # 미국 섹터 수익률 수집
    sectors = {"XLE": "에너지", "XLK": "IT/반도체", "XLI": "산업재"}
    us_perf = []
    for s, name in sectors.items():
        h = yf.Ticker(s).history(period="2d")
        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
        us_perf.append(f"{name}({round(c,2)}%)")
    
    # 국장 테마 수집
    res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    kr_themes = [a.text for a in soup.select('.col_type1 a')[:10]]

    # AI 분석 (프롬프트 강화)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    prompt = f"""
    너는 투자 전략가야. 아래 데이터를 보고 '텔레그램 메시지용' 리포트를 작성해줘.
    
    데이터: 리스크({risk_info}), 미장({us_perf}), 국장테마({kr_themes})
    
    [필수 규칙]
    1. <html>, <head>, <body>, <style> 태그는 절대 사용 금지.
    2. 텔레그램용 HTML(<b>, <i>, <a>)과 이모지만 사용할 것.
    3. 리스크 레벨({risk_info['risk_level']})에 따른 대응 전략을 첫 줄에 요약할 것.
    4. 테마 2개를 선정하고 각각 [NEWS_QUERY: 검색어]를 포함할 것.
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
        "report": report_content
    }
    save_to_history(history_entry)

    # 텔레그램 전송 (실패 대비 로직 포함)
    full_msg = f"🔔 <b>{risk_info['date']} 마켓 브리핑</b>\n\n" + report_content
    
    response = requests.post(
        f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
        json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    )
    
    if response.status_code != 200:
        # 전송 실패 시 태그 제거 후 재시도
        clean_msg = f"⚠️ [전송오류 복구]\n" + re.sub('<[^>]*>', '', full_msg)
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                      json={"chat_id": telegram_chat_id, "text": clean_msg})

    print(f"✅ 실행 완료 (Status: {response.status_code})")
