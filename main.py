"""Orchestrator - invoked by the scheduler on every wake cycle.

Phase 1 scope only: one email account, Claude classification, digest.
Additional email accounts and WhatsApp ingestion are Phase 2+.
"""

import os

from dotenv import load_dotenv

from brain.claude_agent import classify_messages
from connectors.email_imap import fetch_new_messages
from connectors.telegram_bot import send_digest
from db.database import (
    ensure_company,
    get_connection,
    get_last_uid,
    init_db,
    insert_pipeline_item,
    update_checkpoint,
)

load_dotenv()

DB_PATH = os.environ.get("EA_DB_PATH", "ea.db")


def run_cycle():
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)

    company = os.environ["EMAIL_COMPANY"]
    channel = os.environ.get("EMAIL_CHANNEL", "email")
    account = os.environ["EMAIL_ACCOUNT"]
    host = os.environ["EMAIL_IMAP_HOST"]
    password = os.environ["EMAIL_APP_PASSWORD"]

    ensure_company(conn, company, account)

    last_uid = get_last_uid(conn, channel, account)
    messages = fetch_new_messages(host, account, password, last_uid)

    if not messages:
        print("No new messages.")
        conn.close()
        return

    print(f"Fetched {len(messages)} new message(s) from {account}.")
    items = classify_messages(company, channel, messages)

    for item in items:
        insert_pipeline_item(
            conn,
            {
                "company": item.get("company", company),
                "channel": item.get("channel", channel),
                "item": item["item"],
                "stage": item.get("stage", "new"),
                "next_action": item.get("next_action"),
                "due_date": item.get("due_date"),
                "urgency": item.get("urgency"),
                "source_ref": str(item.get("source_ref", "")),
            },
        )

    update_checkpoint(conn, channel, account, str(max(int(m["id"]) for m in messages)))

    if items:
        send_digest(items)
        print(f"Sent digest with {len(items)} item(s).")
    else:
        print("No actionable items found in new messages.")

    conn.close()


if __name__ == "__main__":
    run_cycle()
