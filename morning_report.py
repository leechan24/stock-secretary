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

# 환경 변수 로드
load_dotenv()

def clean_val(key):
    """변수 안의 쓰레기 문자 완벽 제거"""
    val = os.getenv(key, "")
    if not val: return ""
    return re.sub(r'[^a-zA-Z0-9:\-_]', '', val).strip()

api_key = clean_val("GEMINI_API_KEY")
telegram_token = clean_val("TELEGRAM_BOT_TOKEN")
telegram_chat_id = clean_val("TELEGRAM_CHAT_ID")
naver_id = clean_val("NAVER_CLIENT_ID")
naver_secret = clean_val("NAVER_CLIENT_SECRET")

# 최신 클라이언트 생성
client = genai.Client(api_key=api_key)

def get_market_status():
    try:
        df_fx = yf.Ticker("KRW=X").history(period="5d")
        df_vix = yf.Ticker("^VIX").history(period="5d")
        curr_rate = df_fx['Close'].iloc[-1]
        prev_rate = df_fx['Close'].iloc[-2]
        rate_chg = ((curr_rate - prev_rate) / prev_rate) * 100
        curr_vix = df_vix['Close'].iloc[-1]
        
        # 비중 로직
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
    m = get_market_status()
    
    rate_symbol = "▲" if m['rate_chg_pct'] > 0 else "▼" if m['rate_chg_pct'] < 0 else "-"
    
    sectors = {"XLK": "반도체", "XLE": "에너지", "XLV": "바이오"}
    us_perf = []
    for s, name in sectors.items():
        try:
            h = yf.Ticker(s).history(period="2d")
            c = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
            us_perf.append(f"{name}({round(c,2)}%)")
        except: pass

    try:
        res = requests.get("https://finance.naver.com/sise/theme.naver", headers={'User-Agent': 'Mozilla/5.0'})
        kr_themes = [a.text for a in BeautifulSoup(res.text, 'html.parser').select('.col_type1 a')[:10]]
    except:
        kr_themes = ["테마 로딩 실패"]

    try:
        print(f"🤖 쥐사장 AI 분석 중... (Model: gemini-2.0-flash)")
        
        prompt = f"""
        너는 대한민국 최고의 주식 일타강사 '쥐사장'이야. 1,000만 원 투자자(원금) 기준으로 리포트를 작성해. 
        반드시 텔레그램용 <b>, <i> 태그만 써라. <html> 등은 금지!

        데이터: 시장상태({m}), 미장({us_perf}), 국장테마({kr_themes})
        
        [작성 규칙]
        1. 도입부: "🔥 <b>자, 우리 슈퍼개미 제자들! 쥐사장이야!</b>"
        2. 📊 시장 주요 지표:
           - 환율: {m['usd_krw']}원 ({rate_symbol}{abs(m['rate_chg_pct'])}%)
           - VIX 지수: {m['vix']}
           - <b>[오늘의 총 투입 비중: {m['total_weight']}]</b> 
        3. 테마 분석 (원픽, 투픽 2개 작성):
           - <b>[오늘의 원픽 테마: 테마명]</b>
           - 대장주 3개: <b>종목명(코드)</b> 형식
           - 전략: 합산 비중 {m['total_weight'].split('%')[0]}% 이내 / 금액 {int(10000000 * 0.1)}원 내외 분할 매수
           - <b>전략:</b> 매수가 / 1차 매도가 / 손절가 제시. [NEWS_QUERY: 테마명] 태그 포함.
        4. 마무리: "오늘도 원칙 매매! 성투하시길 바랍니다.!"
        """
        
        response = client.models.generate_content(
            model="gemini-flash-latest", 
            contents=prompt
        )
        report_content = response.text
        
        queries = re.findall(r"\[NEWS_QUERY: (.+?)\]", report_content)
        for q in queries:
            report_content = report_content.replace(f"[NEWS_QUERY: {q}]", f"📰 <b>뉴스:</b>\n{get_naver_news(q)}")

        print("📨 발송 시도...")
        full_msg = f"📅 <b>{m['date']} 프리미엄 브리핑</b>\n\n" + report_content
        
        # 텔레그램 URL 조립 (가장 안전한 방식)
        telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"

        res = requests.post(
            telegram_url,
            json={"chat_id": telegram_chat_id, "text": full_msg, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15
        )

        if res.status_code == 200:
            print("✨ 최종 성공! 텔레그램 확인해봐!")
        else:
            print(f"⚠️ 전송 실패({res.status_code}), 복구 모드 가동...")
            clean_msg = f"⚠️ [복구] {m['date']} 브리핑\n\n" + re.sub('<[^>]*>', '', full_msg)
            requests.post(telegram_url, json={"chat_id": telegram_chat_id, "text": clean_msg})

    except Exception as e:
        print(f"❌ 중대 오류 발생: {e}")
