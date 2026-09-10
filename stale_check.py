"""Phase 3: flag items that haven't moved in STALE_DAYS+ days. Run once a
day by its own scheduler entry, separate from the email/WhatsApp wake cycle.
"""

import json

from dotenv import load_dotenv

from brain import router
from config import DB_PATH, STALE_DAYS
from connectors.telegram_bot import send_raw_message
from db.database import get_connection, get_stale_items, init_db

load_dotenv()


def run():
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    stale = get_stale_items(conn, STALE_DAYS)
    conn.close()

    if not stale:
        print("No stale items.")
        return

    prompt = (
        f"These work items have not moved in {STALE_DAYS}+ days (JSON below). "
        "Write a short, plain-text alert grouped by company, one line per "
        "item. No markdown, no preamble.\n\n" + json.dumps(stale, default=str)
    )
    try:
        text = router.compose(prompt, structured_only=True)
    except Exception:
        text = _fallback_text(stale)

    send_raw_message(text)
    print(f"Sent stale alert for {len(stale)} item(s).")


def _fallback_text(items):
    lines = ["Stale items (no movement in a while):"]
    for item in items:
        lines.append(f"- [{item['company']}] {item['item']} (since {item['last_touched']})")
    return "\n".join(lines)


if __name__ == "__main__":
    run()
