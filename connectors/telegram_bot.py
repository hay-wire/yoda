import json
import os

import requests

from brain import router

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def send_digest(items):
    """Outbound push - only called when there's something actionable, never on a fixed interval."""
    if not items:
        return
    send_raw_message(_compose_digest_text(items))


def send_raw_message(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    _send_message(token, chat_id, text)


def _compose_digest_text(items):
    """Digest wording is composed from already-extracted structured fields,
    so it's eligible for the Gemini path - raw message content was already
    stripped away by the time items reach here."""
    prompt = (
        "Write a short, plain-text digest message for these work items "
        "(JSON below). One line per item: company, what it is, urgency, "
        "due date if any. No markdown, no preamble.\n\n"
        + json.dumps(items, default=str)
    )
    try:
        return router.compose(prompt, structured_only=True)
    except Exception:
        return _fallback_digest_text(items)


def _fallback_digest_text(items):
    lines = ["New work items:"]
    for item in items:
        due = f" (due {item['due_date']})" if item.get("due_date") else ""
        urgency = f" [{item['urgency']}]" if item.get("urgency") else ""
        lines.append(f"- [{item.get('company')}] {item['item']}{due}{urgency}")
    return "\n".join(lines)


def _send_message(token, chat_id, text):
    url = TELEGRAM_API.format(token=token, method="sendMessage")
    response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    response.raise_for_status()
    return response.json()
