"""Yahoo Finance adapter (yfinance). 15~20분 지연 데이터."""
from __future__ import annotations

import logging
from typing import Iterable

import yfinance as yf

log = logging.getLogger(__name__)

METRIC_KEYS = ("trailingPE", "forwardPE", "priceToBook", "targetMeanPrice")
_INDEX_PREFIXES = ("^",)


def _is_index_or_fx(ticker: str) -> bool:
    return ticker.startswith(_INDEX_PREFIXES) or "=" in ticker or "-USD" in ticker


def fetch_quotes(tickers: Iterable[str], errors: list[str]) -> dict:
    """Return {ticker: {...}} for every ticker; failures are logged into `errors`."""
    tickers = sorted(set(tickers))
    out: dict[str, dict] = {}
    if not tickers:
        return out

    # 1) 1년치 종가 일괄 다운로드 (MA50/MA200, 연속일 조건용)
    try:
        hist = yf.download(
            tickers, period="1y", interval="1d", auto_adjust=True,
            progress=False, threads=True, group_by="ticker",
        )
    except Exception as e:  # noqa: BLE001
        errors.append(f"yf.download failed: {e}")
        hist = None

    for t in tickers:
        rec: dict = {"price": None, "ma50": None, "ma200": None, "closes": [], "metrics": {}}
        try:
            if hist is not None:
                closes = hist[t]["Close"] if len(tickers) > 1 else hist["Close"]
                closes = closes.dropna()
                if len(closes):
                    rec["closes"] = [float(x) for x in closes.tail(15)]
                    rec["price"] = float(closes.iloc[-1])
                    if len(closes) >= 50:
                        rec["ma50"] = float(closes.tail(50).mean())
                    if len(closes) >= 200:
                        rec["ma200"] = float(closes.tail(200).mean())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{t}: history parse failed: {e}")

        # 2) 밸류 지표 (개별주만; 지수·환율·코인은 없음)
        if not _is_index_or_fx(t):
            try:
                info = yf.Ticker(t).info or {}
                rec["metrics"] = {k: info.get(k) for k in METRIC_KEYS if info.get(k) is not None}
                # 장중이면 info의 현재가가 더 최신
                live = info.get("regularMarketPrice") or info.get("currentPrice")
                if live:
                    rec["price"] = float(live)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{t}: info failed: {e}")

        if rec["price"] is None:
            errors.append(f"{t}: no price")
        out[t] = rec
    return out
