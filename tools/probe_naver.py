"""네이버 금융 수급 엔드포인트 탐색. 실행: python tools/probe_naver.py
어느 URL이 살아 있고 어떤 필드가 오는지 출력. 결과 전체를 그대로 공유."""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120", "Referer": "https://m.stock.naver.com/"}

CANDIDATES = [
    # 코스피 지수 투자자별 동향 (모바일 API)
    "https://m.stock.naver.com/api/index/KOSPI/trend?pageSize=5&page=1",
    "https://m.stock.naver.com/api/index/KOSPI/investorTrend?pageSize=5&page=1",
    # 종목별 외국인/기관 순매수 (모바일 API)
    "https://m.stock.naver.com/api/stock/005930/trend?pageSize=5&page=1",
    "https://m.stock.naver.com/api/stock/000660/trend?pageSize=5&page=1",
    # PC 금융 투자자별 매매동향 (HTML)
    "https://finance.naver.com/sise/sise_trans_style.naver",
    "https://finance.naver.com/sise/investorDealTrendDay.nhn?bizdate=20261106&sosok=",
    # 종목별 외국인 보유/순매수 (HTML)
    "https://finance.naver.com/item/frgn.naver?code=005930",
]

for url in CANDIDATES:
    try:
        r = requests.get(url, headers=UA, timeout=10)
        ct = r.headers.get("content-type", "")
        print(f"\n=== {r.status_code} {url}\n    content-type: {ct}")
        if r.status_code != 200:
            continue
        if "json" in ct:
            data = r.json()
            first = data[0] if isinstance(data, list) and data else data
            print("    sample:", json.dumps(first, ensure_ascii=False)[:400])
        else:
            txt = r.text
            print("    외국인 in page:", "외국인" in txt, "| length:", len(txt))
    except Exception as e:  # noqa: BLE001
        print(f"\n=== FAIL {url}\n    {type(e).__name__}: {str(e)[:120]}")
