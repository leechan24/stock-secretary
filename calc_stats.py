import json
import os
import yfinance as yf
from datetime import datetime, timedelta

def get_current_price(code):
    try:
        suffix = ".KS" if not (code.endswith(".KS") or code.endswith(".KQ")) else ""
        stock = yf.Ticker(f"{code}{suffix}")
        # '종가' 기준으로 가져오기 위해 마지막 종가 데이터 추출
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        return None
    except:
        return None

def calculate_avg_profit(history_data, days_back):
    # 오늘이 2026-05-01이라면, days_back만큼 이전 날짜 계산
    target_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    relevant_picks = []
    for day in history_data:
        # 해당 기간 이후에 추천된 종목들만 필터링
        if day['date'] >= target_date:
            relevant_picks.extend(day['picks'])
    
    if not relevant_picks:
        return 0.0

    total_profit = 0.0
    count = 0
    
    for pick in relevant_picks:
        curr_p = get_current_price(pick['code'])
        if curr_p and pick.get('base_price', 0) > 0:
            # 현실적인 수익률: (현재가 - 추천가) / 추천가
            profit = ((curr_p - pick['base_price']) / pick['base_price']) * 100
            total_profit += profit
            count += 1
            
    return round(total_profit / count, 2) if count > 0 else 0.0

def run_stats_engine():
    if not os.path.exists("history.json"):
        return

    with open("history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    stats = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "performance": {
            "oneDay": calculate_avg_profit(history_data, 1), # 어제 추천주 성적
            "oneWeek": calculate_avg_profit(history_data, 7), # 이번 주 성적
            "oneMonth": calculate_avg_profit(history_data, 30), # 이번 달 성적
            "sixMonth": calculate_avg_profit(history_data, 180)  # 반년 성적
        }
    }

    with open("stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_stats_engine()