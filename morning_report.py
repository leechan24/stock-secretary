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

# 2. 시장 리스크 및 변동성 분석
def get_risk_indicators():
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
        return {"date": datetime.now().strftime("%Y-%m-%d"), "risk_level": "데이터 확인 불가", "usd_krw": 0, "vix": 0, "rate_chg_pct": 0}

# 3. 네이버 뉴스 검색 기능
def get_naver_news(query):
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=3&sort=sim"
    headers = {"X-Naver-Client-Id": naver_id, "X-Naver-Client-Secret": naver_secret}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            items = res.json().get('items', [])
            return "\n".join([f"  • {re.sub('<[^>]*>', '', item['title'])}" for item in items])
    except:
        return "  • 뉴스를 불러오지 못했습니다."
    return "  • 관련 뉴스가 없습니다."

# 4. JSON 데이터 누적 저장
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

# 5. 메인 로직
if __name__ == "__main__":
    risk_info = get_risk_indicators()
    
    # 미국 주요 섹터 수익률 수집
    sectors = {"XLE": "에너지", "XLK": "IT/반도체", "XLI": "산업재", "XLB": "소재"}
    us_perf = []
    for s, name in sectors.items():
        h = yf.Ticker(s).history(period="2d")
        c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
        us_perf.append(f"{name}({round(c,2)}%)")
    
    # 국내 인기 테마 수집
    res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    kr_themes = [a.text for a in soup.select('.col_type1 a')[:10]]

    # AI 리포트 생성 (Gemini)
    model = genai.GenerativeModel('models/gemini-2.5-flash') #잠시 테스트때문에 막혀서 하위버전사용
    prompt = f"""
    너는 대한민국 최고의 주식 일타강사 '쥐선생'이야. 
    아래 데이터를 분석해서 제자들에게 리포트를 HTML 형식으로 써줘.
    
    데이터: 리스크({risk_info}), 미장({us_perf}), 국장테마({kr_themes})
    
    [작성 규칙]
    1. 도입부: "🔥 <b>자, 우리 슈퍼개미를 꿈꾸는 제자 여러분! 쥐선생입니다!</b>"로 시작하며 여기까지만 이모지를 사용해.
    2. 지표 정리: 환율, VIX, 미국 섹터 흐름을 깔끔하게 박스 형태로 정리해.
    3. 테마 및 대장주: 
       - 테마 제목은 <b>[오늘의 원픽/투픽 테마: 테마명]</b> 형식으로 아주 굵게 표시해.
       - 핵심 대장주 라인 전체를 굵게 처리해: <b>핵심 대장주: 종목1, 종목2, 종목3</b>
    4. 마무리: 이모지를 절대 쓰지 말고 담백하게 신뢰감을 주며 마무리해.
    
    [출력 양식]
    🔥 <b>자, 우리 슈퍼개미를 꿈꾸는 제자 여러분! 노선생입니다!</b>
    (시장의 흐름을 짚어주는 열정적인 도입부 2~3줄)

    📊 <b>시장 주요 지표 요약</b>
    --------------------------------
    💰 <b>환율:</b> {risk_info['usd_krw']}원 (<b>{risk_info['rate_chg_pct']}%</b>)
    📉 <b>VIX:</b> {risk_info['vix']} (시장 심리: <b>{risk_info['risk_level']}</b>)
    🇺🇸 <b>미국 섹터 흐름:</b> {", ".join(us_perf)}
    --------------------------------

    <b>[오늘의 원픽 테마: 테마명]</b>
    - <b>분석 근거:</b> (내용 상세히)
    - <b>핵심 대장주: 종목1, 종목2, 종목3</b>
    [NEWS_QUERY: 검색어]

    <b>[오늘의 투픽 테마: 테마명]</b>
    - <b>분석 근거:</b> (내용 상세히)
    - <b>핵심 대장주: 종목1, 종목2, 종목3</b>
    [NEWS_QUERY: 검색어]

    제자 여러분, 오늘도 노선생과 함께 성투하시길 바랍니다. 다음 리포트에서 만나요.
    """
    
    report_content = model.generate_content(prompt).text
    
    # 뉴스 키워드 치환
    queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_content)
    for q in queries:
        news_links = get_naver_news(q)
        report_content = report_content.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>관련 뉴스:</b>\n{news_links}")

    # 데이터 저장
    history_entry = {"date": risk_info['date'], "risk_data": risk_info, "report": report_content}
    save_to_history(history_entry)

    # 텔레그램 전송
    full_msg = f"📅 <b>{risk_info['date']} 프리미엄 브리핑</b>\n\n" + report_content
    
    response = requests.post(
        f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
        json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    )
    
    # 실패 시 복구 로직 (HTML 태그 제거 후 재전송)
    if response.status_code != 200:
        clean_msg = f"⚠️ [복구 버전] 📅 {risk_info['date']} 브리핑\n\n" + re.sub('<[^>]*>', '', full_msg)
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                      json={"chat_id": telegram_chat_id, "text": clean_msg})

    print(f"✅ 완료! (Status: {response.status_code})")
