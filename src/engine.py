"""Rule engine: pure functions over (rules, snapshot, state) -> (alerts, new_state).

state = {
  "rules": {rule_id: {"active": bool, "last_fired": "YYYY-MM-DD"}},
  "history": {ticker: {"YYYY-MM-DD": {"price":..., "ma50":...}}},
}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Alert:
    rule_id: str
    title: str
    body: str
    watch: bool = False


# ───────────────────────── condition evaluators ─────────────────────────

def _price(snap, ticker):
    q = snap["quotes"].get(ticker) or {}
    return q.get("price")


def _bizdate(d: str) -> str:
    """'20261106' → '2026-11-06' (이미 ISO면 그대로)"""
    d = str(d)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d


def _hist_seq(state, key, n):
    h = state.get("history", {}).get(key, {})
    return [h[d] for d in sorted(h.keys())[-n:]]


def _consecutive_above_ma50(snap, state, ticker, n, today):
    """최근 n 영업일 종가 > MA50 — history에 저장된 일별 기록으로 판정."""
    hist = state.get("history", {}).get(ticker, {})
    days = sorted(hist.keys())[-n:]
    if len(days) < n:
        return False
    return all(
        hist[d].get("price") is not None and hist[d].get("ma50") is not None
        and hist[d]["price"] > hist[d]["ma50"]
        for d in days
    )


def evaluate(rule, snap, state, today: date) -> tuple[bool, str]:
    """Return (condition_true, detail_string)."""
    t = rule.get("type")
    if t == "price_below":
        p = _price(snap, rule["ticker"])
        if p is None:
            return False, "no data"
        return p <= rule["level"], f"{p:,.2f} ≤ {rule['level']:,}"
    if t == "price_above":
        p = _price(snap, rule["ticker"])
        if p is None:
            return False, "no data"
        ok = p >= rule["level"]
        extra = rule.get("and") or {}
        if ok and "above_ma50_days" in extra:
            ok = _consecutive_above_ma50(snap, state, rule["ticker"], extra["above_ma50_days"], today)
            return ok, f"{p:,.2f} ≥ {rule['level']:,} & MA50 위 {extra['above_ma50_days']}일"
        return ok, f"{p:,.2f} ≥ {rule['level']:,}"
    if t == "price_between":
        p = _price(snap, rule["ticker"])
        if p is None:
            return False, "no data"
        return rule["low"] <= p <= rule["high"], f"{p:,.2f} ∈ [{rule['low']}, {rule['high']}]"
    if t == "metric_below":
        q = snap["quotes"].get(rule["ticker"]) or {}
        v = (q.get("metrics") or {}).get(rule["metric"])
        if v is None:
            return False, "no metric"
        return v <= rule["level"], f"{rule['metric']}={v:.2f} ≤ {rule['level']}"
    if t == "krx_foreign_net_buy_days":
        n = rule["days"]
        seq = _hist_seq(state, "krx:KOSPI", n)
        if len(seq) < n:
            return False, "no krx data"
        tail = seq[-n:]
        ok = all(x > 0 for x in tail)
        return ok, "외국인 " + " / ".join(f"{x/1e8:+,.0f}억" for x in tail)
    if t == "stock_foreign_net_buy_days":
        n = rule["days"]
        seq = _hist_seq(state, f"krx:{rule['krx']}", n)
        if len(seq) < n:
            return False, "no naver data"
        tail = seq[-n:]
        ok = all(x > 0 for x in tail)
        return ok, "외국인 " + " / ".join(f"{x/1e4:+,.0f}만주" for x in tail)
    if t == "ma200_above_pct":
        hits = []
        for tk in rule["tickers"]:
            q = snap["quotes"].get(tk) or {}
            p, ma = q.get("price"), q.get("ma200")
            if p and ma and (p / ma - 1) * 100 >= rule["pct"]:
                hits.append(f"{tk} +{(p/ma-1)*100:.0f}%")
        return bool(hits), ", ".join(hits)
    return False, f"unknown type {t}"


def _rearmed(rule, snap, pct) -> bool:
    """조건이 꺼진 뒤 level에서 pct% 이상 벗어났는지."""
    t = rule.get("type")
    if t not in ("price_below", "price_above", "price_between"):
        return True  # 비가격 규칙은 꺼지면 바로 재장전
    p = _price(snap, rule["ticker"])
    if p is None:
        return False
    if t == "price_below":
        return p >= rule["level"] * (1 + pct / 100)
    if t == "price_above":
        return p <= rule["level"] * (1 - pct / 100)
    lo, hi = rule["low"], rule["high"]
    return p >= hi * (1 + pct / 100) or p <= lo * (1 - pct / 100)


# ───────────────────────── main entry ─────────────────────────

def run(rules_doc: dict, snap: dict, state: dict, today: date) -> tuple[list[Alert], dict]:
    settings = rules_doc.get("settings", {})
    manual = rules_doc.get("manual", {})
    rearm_pct = settings.get("rearm_pct", 5)
    hist_days = settings.get("history_days", 10)

    state.setdefault("rules", {})
    state.setdefault("history", {})
    ds = today.isoformat()

    # 1) 일별 이력 기록 (연속일 조건용)
    for tk, q in snap["quotes"].items():
        h = state["history"].setdefault(tk, {})
        if q.get("price") is not None:
            h[ds] = {"price": q["price"], "ma50": q.get("ma50"), "ma200": q.get("ma200")}
        for old in sorted(h.keys())[:-hist_days]:
            del h[old]

    # 1b) 수급 이력 누적 (네이버 지수 API는 하루치만 주므로 여기서 쌓는다)
    krx = snap.get("krx", {})
    dates = krx.get("dates") or [ds]
    if krx.get("foreign_net"):
        h = state["history"].setdefault("krx:KOSPI", {})
        for d, v in zip(dates[-len(krx["foreign_net"]):], krx["foreign_net"]):
            h[_bizdate(d)] = v
        for old in sorted(h.keys())[:-hist_days]:
            del h[old]
    for code, seq in (krx.get("stock_foreign_net") or {}).items():
        h = state["history"].setdefault(f"krx:{code}", {})
        sd = krx.get("stock_dates", {}).get(code) or [ds] * len(seq)
        for d, v in zip(sd[-len(seq):], seq):
            h[_bizdate(d)] = v
        for old in sorted(h.keys())[:-hist_days]:
            del h[old]

    alerts: list[Alert] = []
    for rule in rules_doc.get("rules", []):
        rid = rule["id"]
        rs = state["rules"].setdefault(rid, {"active": False, "last_fired": None})

        # 만료 / 수동 플래그
        if rule.get("expires") and today > date.fromisoformat(str(rule["expires"])):
            continue
        if rule.get("requires") and not manual.get(rule["requires"], False):
            continue

        cond, detail = evaluate(rule, snap, state, today)

        if cond and not rs["active"]:
            rs["active"], rs["last_fired"] = True, ds
            tag = "WATCH" if rule.get("watch") else ("SELL" if "sell" in rid else "BUY" if any(
                k in rule.get("type", "") for k in ("below", "between", "metric")) else "ALERT")
            title = f"[{tag}] {rule.get('name', rule.get('ticker', rid))}"
            body = detail + (f"\n→ {rule['note']}" if rule.get("note") else "")
            alerts.append(Alert(rid, title, body, watch=bool(rule.get("watch"))))
        elif not cond and rs["active"] and _rearmed(rule, snap, rearm_pct):
            rs["active"] = False

    return alerts, state
