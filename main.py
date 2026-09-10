"""Orchestrator - invoked by the scheduler on every wake cycle.

Ingests every configured email account (Phase 1: one, Phase 2: up to three)
and, if enabled, WhatsApp, classifies new messages via the brain router
(Claude by default, or a local model under PRIVACY_MODE=local), stores the
results, and sends one digest per cycle if anything actionable came in.
"""

from dotenv import load_dotenv

from brain import router
from config import DB_PATH, WHATSAPP_ENABLED, get_email_accounts, match_whatsapp_company
from connectors import whatsapp
from connectors.email_imap import fetch_new_messages
from connectors.telegram_bot import send_digest, send_raw_message
from db.database import (
    ensure_company,
    get_connection,
    get_last_uid,
    get_setting,
    init_db,
    insert_pipeline_item,
    update_checkpoint,
)

load_dotenv()


def _store_items(conn, items, fallback_company, fallback_channel):
    for item in items:
        insert_pipeline_item(
            conn,
            {
                "company": item.get("company", fallback_company),
                "channel": item.get("channel", fallback_channel),
                "item": item["item"],
                "stage": item.get("stage", "new"),
                "next_action": item.get("next_action"),
                "due_date": item.get("due_date"),
                "urgency": item.get("urgency"),
                "source_ref": str(item.get("source_ref", "")),
            },
        )
    return items


def ingest_email_account(conn, account, persona):
    company, channel = account["company"], account["channel"]
    ensure_company(conn, company, account["account"])

    last_uid = get_last_uid(conn, channel, account["account"])
    messages = fetch_new_messages(account["host"], account["account"], account["password"], last_uid)
    if not messages:
        return []

    print(f"Fetched {len(messages)} new message(s) from {account['account']}.")
    items = router.classify(company, channel, messages, persona=persona)
    update_checkpoint(conn, channel, account["account"], str(max(int(m["id"]) for m in messages)))
    return _store_items(conn, items, company, channel)


def ingest_whatsapp(conn, persona):
    """Read-only, reconnect -> fetch -> disconnect per cycle (handled inside
    connectors/whatsapp.py). A reconnect failure is surfaced via Telegram
    rather than failing silently."""
    try:
        last_uid = get_last_uid(conn, "whatsapp", "whatsapp") or "0"
        messages = whatsapp.fetch_new_messages(int(last_uid))
    except Exception as exc:
        send_raw_message(f"WhatsApp reconnect failed: {exc}")
        return []

    if not messages:
        return []

    print(f"Fetched {len(messages)} new WhatsApp message(s).")
    by_company = {}
    for msg in messages:
        by_company.setdefault(match_whatsapp_company(msg["chat"]), []).append(msg)

    all_items = []
    for company, msgs in by_company.items():
        ensure_company(conn, company)
        items = router.classify(company, "whatsapp", msgs, persona=persona)
        all_items.extend(_store_items(conn, items, company, "whatsapp"))

    update_checkpoint(conn, "whatsapp", "whatsapp", str(max(m["timestamp_ms"] for m in messages)))
    return all_items


def run_cycle():
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    persona = get_setting(conn, "persona_instructions", "") or ""

    accounts = get_email_accounts()
    if not accounts:
        raise RuntimeError("No email accounts configured - set EMAIL_1_* in .env.")

    all_items = []
    for account in accounts:
        all_items.extend(ingest_email_account(conn, account, persona))

    if WHATSAPP_ENABLED:
        all_items.extend(ingest_whatsapp(conn, persona))

    if all_items:
        send_digest(all_items)
        print(f"Sent digest with {len(all_items)} item(s).")
    else:
        print("No actionable items found this cycle.")

    conn.close()


if __name__ == "__main__":
    run_cycle()
