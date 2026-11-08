"""Notifier. 환경변수로 채널 선택 — 둘 다 설정하면 둘 다 보냄.

ntfy:     NTFY_TOPIC (필수), NTFY_SERVER (기본 https://ntfy.sh), NTFY_TOKEN (선택, 인증 토픽용)
telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)


def send_ntfy(title: str, text: str, priority: str = "default") -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {
        "Title": title.encode("utf-8").decode("latin-1", "ignore") if title.isascii() else "",
        "Priority": priority,
        "Tags": "chart_with_upwards_trend",
    }
    # ntfy 헤더는 ASCII만 허용 → 한글 제목은 본문 첫 줄로
    if not title.isascii():
        text = f"{title}\n{text}"
        headers.pop("Title")
    tok = os.environ.get("NTFY_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    r = requests.post(f"{server}/{topic}", data=text.encode("utf-8"), headers=headers, timeout=15)
    if r.status_code >= 300:
        log.error("ntfy %s: %s", r.status_code, r.text[:200])
        return False
    return True


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )
    if r.status_code != 200:
        log.error("telegram %s: %s", r.status_code, r.text[:200])
        return False
    return True


def send(title: str, text: str, priority: str = "default") -> bool:
    sent = False
    sent |= send_ntfy(title, text, priority)
    sent |= send_telegram(f"{title}\n{text}")
    if not sent:
        log.warning("no notifier configured (NTFY_TOPIC or TELEGRAM_*); printing:\n%s\n%s", title, text)
    return sent


def format_alerts(alerts, errors) -> tuple[str, str]:
    """(body, priority). 매수/매도 알림이 있으면 high, 관찰·에러만이면 default."""
    lines = []
    for a in alerts:
        lines.append(f"{a.title}\n{a.body}")
    if errors:
        lines.append("⚠️ 수집 실패:\n" + "\n".join(f"- {e}" for e in errors[:8]))
    prio = "high" if any(not a.watch for a in alerts) else "default"
    return "\n\n".join(lines), prio
