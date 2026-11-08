"""python -m pytest tests/ — 네트워크 없이 엔진만 검증."""
from datetime import date, timedelta
import yaml, pathlib
from src.engine import run

RULES = yaml.safe_load((pathlib.Path(__file__).parents[1] / "rules.yaml").read_text(encoding="utf-8"))

def snap(prices: dict, foreign=None, metrics=None, stock_foreign=None):
    q = {t: {"price": p, "ma50": p*0.95, "ma200": p*0.8, "closes": [p]*5, "metrics": (metrics or {}).get(t, {})}
         for t, p in prices.items()}
    return {"quotes": q, "krx": {"foreign_net": foreign or [], "stock_foreign_net": stock_foreign or {}}, "errors": []}

def test_hynix_foreign_two_days():
    s = snap({}, stock_foreign={"000660": [-1e6, 2e5, 3e5]})
    s["krx"]["stock_dates"] = {"000660": ["20261104", "20261105", "20261106"]}
    a, _ = run(RULES, s, {}, date(2026,11,10)); assert "hynix_foreign_2d" in ids(a)
    s = snap({}, stock_foreign={"000660": [2e5, -1e5, 3e5]})
    s["krx"]["stock_dates"] = {"000660": ["20261104", "20261105", "20261106"]}
    a, _ = run(RULES, s, {}, date(2026,11,10)); assert "hynix_foreign_2d" not in ids(a)

def ids(alerts): return {a.rule_id for a in alerts}

def test_hynix_buy_fires_once_then_rearms():
    st = {}
    a1, st = run(RULES, snap({"000660.KS": 940_000}), st, date(2026,11,10))
    assert "hynix_buy" in ids(a1)
    a2, st = run(RULES, snap({"000660.KS": 930_000}), st, date(2026,11,11))
    assert "hynix_buy" not in ids(a2)            # 중복 알림 없음
    a3, st = run(RULES, snap({"000660.KS": 1_000_000}), st, date(2026,11,12))  # +5.3% 벗어남
    a4, st = run(RULES, snap({"000660.KS": 940_000}), st, date(2026,11,13))
    assert "hynix_buy" in ids(a4)                # 재진입 → 재알림

def test_samsung_sell_levels():
    a, _ = run(RULES, snap({"005930.KS": 225_000}), {}, date(2026,12,1))
    assert "samsung_sell_22" in ids(a) and "samsung_sell_24" not in ids(a)

def test_requires_manual_flag():
    a, _ = run(RULES, snap({"006400.KS": 400_000}), {}, date(2026,12,1))
    assert "sdi_buy" not in ids(a)
    r2 = dict(RULES, manual={**RULES["manual"], "ess_order_confirmed": True})
    a, _ = run(r2, snap({"006400.KS": 400_000}), {}, date(2026,12,1))
    assert "sdi_buy" in ids(a)

def test_fslr_expiry():
    a, _ = run(RULES, snap({"FSLR": 183}), {}, date(2026,11,17)); assert "fslr_buy" in ids(a)
    a, _ = run(RULES, snap({"FSLR": 183}), {}, date(2026,11,19)); assert "fslr_buy" not in ids(a)

def test_foreign_two_days():
    st = {}
    a, st = run(RULES, snap({}, foreign=[-1e11]), st, date(2026,11,10)); assert "kospi_foreign_2d" not in ids(a)
    a, st = run(RULES, snap({}, foreign=[2e11]),  st, date(2026,11,11)); assert "kospi_foreign_2d" not in ids(a)
    a, st = run(RULES, snap({}, foreign=[3e11]),  st, date(2026,11,12)); assert "kospi_foreign_2d" in ids(a)
    # 같은 날 두 번 돌아도 덮어쓰기만 됨 (중복 집계 없음)
    assert len(st["history"]["krx:KOSPI"]) == 3

def test_hynix_sell_needs_3_days_above_ma50():
    st = {}
    d = date(2026,12,1)
    for i in range(3):
        a, st = run(RULES, snap({"000660.KS": 1_520_000}), st, d + timedelta(days=i))
    assert "hynix_sell" in ids(a)  # 3일째에 발동

def test_mu_pbr_and_overheat():
    a, _ = run(RULES, snap({"MU": 300}, metrics={"MU": {"priceToBook": 1.4}}), {}, date(2027,1,5))
    assert "mu_pbr" in ids(a)
    s = snap({"GOOGL": 400}); s["quotes"]["GOOGL"]["ma200"] = 300
    a, _ = run(RULES, s, {}, date(2027,1,5)); assert "overheat" in ids(a)
