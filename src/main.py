"""Entry point. `python -m src.main [--market KR|US|ALL] [--dry-run]`"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .collector import fetch_krx, fetch_quotes
from .engine import run
from .notifier import format_alerts, send

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules.yaml"
STATE = ROOT / "state.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")


def _is_kr(t: str) -> bool:
    return t.endswith(".KS") or t.endswith(".KQ")


def _tickers_for(rules_doc, market: str) -> tuple[set[str], set[str]]:
    tickers, krx_codes = set(), set()
    for r in rules_doc["rules"]:
        ts = r.get("tickers") or ([r["ticker"]] if r.get("ticker") else [])
        for t in ts:
            if market == "ALL" or (market == "KR" and _is_kr(t)) or (market == "US" and not _is_kr(t)):
                tickers.add(t)
        if r.get("krx") and market in ("ALL", "KR"):
            krx_codes.add(r["krx"])
    # 거시 지표는 항상 포함
    tickers |= {"^TNX", "^VIX", "KRW=X", "BTC-USD"}
    return tickers, krx_codes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="ALL", choices=["KR", "US", "ALL"])
    ap.add_argument("--dry-run", action="store_true", help="알림 안 보내고 출력만")
    ap.add_argument("--ping", action="store_true", help="연결 테스트 알림 1개만 보내고 종료")
    args = ap.parse_args(argv)

    if args.ping:
        ok = send("알리미 테스트", "ntfy 연결 OK. 이 알림이 보이면 설정 끝.", "high")
        print("sent" if ok else "FAILED — NTFY_TOPIC 환경변수 확인")
        return 0 if ok else 1

    rules_doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()

    errors: list[str] = []
    tickers, krx_codes = _tickers_for(rules_doc, args.market)
    snap = {"quotes": fetch_quotes(tickers, errors), "krx": {}, "errors": errors}
    if args.market in ("KR", "ALL"):
        snap["krx"] = fetch_krx(krx_codes, rules_doc["settings"].get("history_days", 10), errors)

    alerts, state = run(rules_doc, snap, state, today)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    log.info("%d alerts, %d errors", len(alerts), len(errors))
    if alerts or errors:
        body, prio = format_alerts(alerts, errors)
        title = f"알리미 {args.market} {today}"
        if args.dry_run:
            print(title, body, sep="\n")
        else:
            send(title, body, prio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
