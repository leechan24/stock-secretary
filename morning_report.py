import requests
from bs4 import BeautifulSoup
import yfinance as yf
import json
import os
import google.generativeai as genai

# [중요] 보안을 위해 API 키를 직접 적지 않고 시스템 환경 변수에서 가져옵니다.
# 로컬 테스트 시에는 터미널에 set GEMINI_API_KEY=내키 입력 필요
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# 1. 미국 섹터 데이터 수집 함수
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

# 2. 한국 테마 데이터 수집 함수
def get_kr_themes():
    print("🔍 국장 테마 수집 중...")
    url = "https://finance.naver.com/sise/theme.naver"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    return [tag.text for tag in soup.select('.col_type1 a')[:15]]

# 3. AI 애널리스트 분석 함수
def ask_ai_analyst(us_data, kr_themes):
    print("🤖 AI 애널리스트가 맥락을 분석 중입니다...")
    
    # 개발자님 환경에서 확인된 사용 가능한 모델을 사용합니다.
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

# 4. 메인 실행부
if __name__ == "__main__":
    if not api_key:
        print("❗ 에러: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    else:
        try:
            us_data = get_us_sector_performance()
            kr_themes = get_kr_themes()
            
            report = ask_ai_analyst(us_data, kr_themes)
            
            print("\n" + "="*40)
            print("📢 오늘의 AI 주식 비서 브리핑")
            print(report)
            print("="*40)
            
        except Exception as e:
            print(f"❗ 오류 발생: {e}")