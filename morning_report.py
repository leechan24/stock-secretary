import requests
from bs4 import BeautifulSoup
import yfinance as yf
import json
import os
import google.generativeai as genai

# 1. 설정: 환경 변수에서 키들을 가져옵니다. (GitHub Secrets 설정 필수)
api_key = os.getenv("GEMINI_API_KEY")
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

genai.configure(api_key=api_key)

# 2. 미국 섹터 데이터 수집 함수
def get_us_sector_performance():
    print("🇺🇸 미장 섹터별 흐름 분석 중...")
    SECTOR_MAP = {
        "XLK": "IT/반도체", "XLV": "헬스케어", "XLF": "금융",
        "XLY": "소비재/자동차", "XLI": "산업재/기계", "XLE": "에너지/정유",
        "XLB": "원자재/구리", "XLP": "필수소비재"
    }
    performance = []
    for symbol, name in SECTOR_MAP.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                change = ((hist['Close'].iloc[1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                performance.append(f"{name}: {round(change, 2)}%")
        except:
            continue
    return performance

# 3. 한국 테마 데이터 수집 함수
def get_kr_themes():
    print("🔍 국장 테마 수집 중...")
    url = "https://finance.naver.com/sise/theme.naver"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    return [tag.text for tag in soup.select('.col_type1 a')[:15]]

# 4. AI 애널리스트 분석 함수
def ask_ai_analyst(us_data, kr_themes):
    print("🤖 AI 애널리스트가 맥락을 분석 중입니다...")
    
    # 개발자님 환경에 최적화된 모델 선택
    target_model = 'models/gemini-2.5-flash' 
    model = genai.GenerativeModel(target_model)
    
    prompt = f"""
    너는 대한민국 최고의 주식 전략가야. 아래 데이터를 보고 오늘 국장에서 급등할 테마 3개를 골라줘.
    미국 섹터 성적이 한국의 어떤 '공급망'이나 '관련주'로 연결되는지 논리적으로 분석해.

    [미국 시장 성적]
    {us_data}

    [한국 테마 리스트]
    {kr_themes}

    형식:
    1. 추천 테마: 
    2. 이유(맥락): 
    3. 관련 종목 예시:
    """
    
    response = model.generate_content(prompt)
    return response.text

# 5. 텔레그램 전송 함수
def send_telegram_message(message):
    if not telegram_token or not telegram_chat_id:
        print("⚠️ 텔레그램 설정이 비어있어 메시지를 보내지 않습니다.")
        return

    print("📤 텔레그램으로 브리핑 전송 중...")
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    
    # 마크다운 문법 적용 (볼드체 등)
    payload = {
        "chat_id": telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ 텔레그램 전송 완료!")
        else:
            print(f"❌ 전송 실패: {response.text}")
    except Exception as e:
        print(f"❌ 전송 중 오류 발생: {e}")

# 6. 메인 실행부
if __name__ == "__main__":
    if not api_key:
        print("❗ 에러: GEMINI_API_KEY 환경 변수가 없습니다.")
    else:
        try:
            us_data = get_us_sector_performance()
            kr_themes = get_kr_themes()
            
            report = ask_ai_analyst(us_data, kr_themes)
            
            # 최종 메시지 구성
            full_report = f"📢 *오늘의 AI 주식 비서 브리핑*\n\n{report}"
            
            # 터미널 출력 및 텔레그램 전송
            print("\n" + "="*40)
            print(full_report)
            print("="*40)
            
            send_telegram_message(full_report)
            
        except Exception as e:
            print(f"❗ 시스템 오류 발생: {e}")
