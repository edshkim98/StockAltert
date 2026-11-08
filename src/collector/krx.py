"""한국 수급 어댑터 — 네이버 모바일 금융 API.

index/KOSPI/trend  : 코스피 투자자별 순매수, 최신 하루만 (단위 억원) → 엔진이 state.json에 이력 누적
stock/{code}/trend : 일별 종목별 외국인·기관 순매수 (단위 주)

실패하면 errors에 남기고 빈 값 — 가격 규칙은 yfinance(.KS)로 계속 돈다.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

log = logging.getLogger(__name__)

BASE = "https://m.stock.naver.com/api"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120", "Referer": "https://m.stock.naver.com/"}


def _num(s) -> float:
    """'+5,207' / '-26,892' → float"""
    return float(str(s).replace(",", "").replace("+", "")) if s not in (None, "", "-") else 0.0


def _get(path: str, days: int) -> list[dict]:
    r = requests.get(f"{BASE}/{path}", params={"pageSize": days, "page": 1}, headers=UA, timeout=15)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):          # 지수 엔드포인트는 최신 하루만 dict로 줌
        data = [data]
    if not isinstance(data, list):
        raise ValueError(f"unexpected payload: {str(data)[:80]}")
    return sorted(data, key=lambda x: x.get("bizdate", ""))  # 오래된 것부터


def fetch_krx(krx_codes: Iterable[str], days: int, errors: list[str]) -> dict:
    out = {"foreign_net": [], "stock_foreign_net": {}, "dates": [], "stock_dates": {}}

    # 1) 코스피 전체 외국인 순매수 (억원 → 원)
    try:
        rows = _get("index/KOSPI/trend", days)
        out["foreign_net"] = [_num(x.get("foreignValue")) * 1e8 for x in rows]
        out["dates"] = [x.get("bizdate") for x in rows]
    except Exception as e:  # noqa: BLE001
        errors.append(f"naver KOSPI trend failed: {type(e).__name__}: {str(e)[:80]}")

    # 2) 종목별 외국인 순매수 (주)
    for code in sorted(set(krx_codes)):
        try:
            rows = _get(f"stock/{code}/trend", days)
            out["stock_foreign_net"][code] = [_num(x.get("foreignerPureBuyQuant")) for x in rows]
            out["stock_dates"][code] = [x.get("bizdate") for x in rows]
        except Exception as e:  # noqa: BLE001
            errors.append(f"naver {code} trend failed: {type(e).__name__}: {str(e)[:80]}")
    return out
