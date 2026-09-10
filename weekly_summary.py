"""Phase 3: weekly per-company summary, composed from aggregate counts only
- the kind of already-structured, non-sensitive data the Gemini path is
for. Run once a week by its own scheduler entry.
"""

import json

from dotenv import load_dotenv

from brain import router
from config import DB_PATH, STALE_DAYS
from connectors.telegram_bot import send_raw_message
from db.database import get_connection, get_weekly_stats, init_db

load_dotenv()


def run():
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    stats = get_weekly_stats(conn, stale_days=STALE_DAYS)
    conn.close()

    if not stats:
        print("No activity to summarize.")
        return

    prompt = (
        "Write a short weekly summary for a personal work tracker, one "
        "paragraph per company, from this aggregate data (JSON below): "
        "new/done/open/stale item counts. Plain text, no markdown, no "
        "preamble.\n\n" + json.dumps(stats, default=str)
    )
    try:
        text = router.compose(prompt, structured_only=True)
    except Exception:
        text = _fallback_text(stats)

    send_raw_message(text)
    print("Sent weekly summary.")


def _fallback_text(stats):
    lines = ["Weekly summary:"]
    for company, s in stats.items():
        lines.append(f"- {company}: {s['new']} new, {s['done']} done, {s['open']} open, {s['stale']} stale")
    return "\n".join(lines)


if __name__ == "__main__":
    run()
