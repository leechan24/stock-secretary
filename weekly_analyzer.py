import os
import json
import requests
import yfinance as yf
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai

# 로컬 테스트용 (GitHub Actions에서는 Secrets 환경변수를 직접 읽음)
load_dotenv()

def get_env(key):
    return re.sub(r"[\s'\"\[\]]", "", os.getenv(key, "").strip())

api_key = get_env("GEMINI_API_KEY")
telegram_token = get_env("TELEGRAM_BOT_TOKEN")
telegram_chat_id = get_env("TELEGRAM_CHAT_ID")

client = genai.Client(api_key=api_key)

def get_weekly_performance(picks, start_date):
    results = []
    # 오늘 상한가 데이터를 포함하기 위해 내일 날짜까지 범위 설정
    search_end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    for pick in picks:
        name = pick.get('name', '알수없음')
        code = pick.get('code', '')
        base_price = pick.get('base_price', 0)
        theme = pick.get('theme', '기타')
        try:
            # 코스피/코스닥 구분 시도
            suffix = ".KS" if not (code.endswith(".KS") or code.endswith(".KQ")) else ""
            stock = yf.Ticker(f"{code}{suffix}")
            hist = stock.history(start=start_date, end=search_end)
            
            if hist.empty and suffix == ".KS":
                stock = yf.Ticker(f"{code}.KQ")
                hist = stock.history(start=start_date, end=search_end)

            if not hist.empty:
                # 최고가 캡처 (히스토리 고가 vs 실시간 고가)
                max_p = max(float(hist['High'].max()), float(stock.fast_info.get('dayHigh', 0)))
                profit = ((max_p - base_price) / base_price) * 100
                results.append({"name": name, "theme": theme, "profit": round(profit, 2)})
        except:
            results.append({"name": name, "theme": theme, "profit": 0})
    return results

def run_weekly_analysis():
    print("🚀 쥐사장 일타강사 리포트 엔진 가동!")
    
    if not os.path.exists("history.json"):
        print("❌ history.json 파일을 찾을 수 없습니다.")
        return

    with open("history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    # 이번 주 월요일 기준 필터링
    monday = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    target_history = [h for h in history_data if h['date'] >= monday]

    if not target_history:
        print("⚠️ 이번 주 데이터가 없습니다.")
        return

    total_summary = []
    latest_market = target_history[-1].get('market', {})
    for day in target_history:
        perf = get_weekly_performance(day['picks'], day['date'])
        total_summary.append({"date": day['date'], "performance": perf})

    # AI 프롬프트 - 제자님 맞춤형 구성
    prompt = f"""
    너는 대한민국 주식 일타강사 '쥐사장'이다. 아래 양식에 맞춰 주간 리포트를 작성하라.
    
    [필수 규칙]
    1. '찍'이라는 말투는 절대 사용하지 마라. 전문적이고 자신감 넘치는 말투를 사용하라.
    2. 모든 <b>종목명</b>, <b>테마명</b>, <b>수익률(%)</b> 수치는 반드시 <b> 태그로 감싸라.
    3. 마크다운 기호를 쓰지 말고 오직 <b>와 <i> 태그만 사용하여 문단을 구분하라.

    [리포트 구성 양식]
    🏆 <b>WEEKLY PERFORMANCE REPORT</b>

    1. <b>시장 브리핑 및 대응 전략</b>
    환율(<b>{latest_market.get('exchange_rate', 'N/A')}</b>)과 VIX(<b>{latest_market.get('vix', 'N/A')}</b>) 상황을 기반으로 현재 비중 조절 전략을 제시하라.

    2. [🏆 <b>이번 주 효자 종목</b>]
    수익률 10% 넘긴 종목들을 나열하고 격하게 칭찬하라.
    형식: 1. <b>종목명</b> (<b>테마명</b>): <b>00.00%</b> 수익! (맛깔나는 칭찬 멘트)

    3. [📉 <b>테마별 한 줄 평</b>]
    테마별로 묶어서 흐름을 평가하라. 잘한 놈, 정신 차려야 할 놈을 구분하라.

    4. <b>쥐사장의 한마디</b>
    이 섹션은 네가 데이터(수익률, 시장 상황)를 보고 자유롭게 작성하라. 
    - 수익이 좋으면 자만 방지, 저조하면 복기와 인내 강조.
    - 제자들에게 전하고 싶은 주식 마인드셋 조언을 포함하라.
    - 예시 말투: "제자님들! 시장이 불안할수록 '방망이 짧게'가 핵심입니다. 오늘 수익 본 종목들은 기분 좋게 익절하고, 안 풀린 종목들은 왜 안 갔는지 차트 복기 꼭 하십시오! 공부만이 살길입니다! 내일도 수익 파티 준비됐습니까? 쥐사장만 믿고 따라오십시오!"
    """

    try:
        response = client.models.generate_content(model="gemini-flash-latest", contents=prompt)
        report = response.text.replace("```html", "").replace("```", "").strip()
        
        # 텔레그램 전송
        requests.post(
            f"https://api.telegram.org/bot{telegram_token}/sendMessage",
            json={
                "chat_id": telegram_chat_id, 
                "text": report, 
                "parse_mode": "HTML", 
                "disable_web_page_preview": True
            }
        )
        print("✨ 리포트 발송 완료!")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    run_weekly_analysis()