import os

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def send_digest(items):
    """Outbound push - only called when there's something actionable, never on a fixed interval."""
    if not items:
        return

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    lines = ["New work items:"]
    for item in items:
        due = f" (due {item['due_date']})" if item.get("due_date") else ""
        urgency = f" [{item['urgency']}]" if item.get("urgency") else ""
        lines.append(f"- [{item.get('company')}] {item['item']}{due}{urgency}")

    _send_message(token, chat_id, "\n".join(lines))


def _send_message(token, chat_id, text):
    url = TELEGRAM_API.format(token=token, method="sendMessage")
    response = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    response.raise_for_status()
    return response.json()
