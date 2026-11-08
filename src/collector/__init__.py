"""Collector adapters. Each returns a Snapshot dict:

snapshot = {
  "quotes": {ticker: {"price": float, "ma50": float|None, "ma200": float|None,
                      "closes": [float,...]  # 최근 N일 종가, 오래된 것부터
                      "metrics": {"trailingPE":..,"forwardPE":..,"priceToBook":..}}},
  "krx":    {"foreign_net": [float,...]  # 최근 N일 코스피 외국인 순매수(원), 오래된 것부터
             "fundamental": {krx_code: {"PER":..,"PBR":..}}},
  "errors": [str,...],
}
"""
from .yf import fetch_quotes
from .krx import fetch_krx

__all__ = ["fetch_quotes", "fetch_krx"]
