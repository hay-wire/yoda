"""Central config. Phase 1 is EMAIL_1_* alone; Phase 2 fills in EMAIL_2_*/
EMAIL_3_* and WHATSAPP_ENABLED; Phase 4 adds PRIVACY_MODE."""

import json
import os

DB_PATH = os.environ.get("EA_DB_PATH", "ea.db")
STALE_DAYS = int(os.environ.get("STALE_DAYS", "5"))
WHATSAPP_ENABLED = os.environ.get("WHATSAPP_ENABLED", "false").lower() == "true"
PRIVACY_MODE = os.environ.get("PRIVACY_MODE", "claude")  # "claude" | "local"

_MAX_EMAIL_ACCOUNTS = 3


def get_email_accounts():
    """One connector function (connectors/email_imap.py) is reused for every
    account - Gmail, Outlook, and Zoho all speak IMAP."""
    accounts = []
    for i in range(1, _MAX_EMAIL_ACCOUNTS + 1):
        account = os.environ.get(f"EMAIL_{i}_ACCOUNT")
        if not account:
            continue
        accounts.append(
            {
                "company": os.environ[f"EMAIL_{i}_COMPANY"],
                "channel": os.environ.get(f"EMAIL_{i}_CHANNEL", "email"),
                "account": account,
                "host": os.environ[f"EMAIL_{i}_IMAP_HOST"],
                "password": os.environ[f"EMAIL_{i}_APP_PASSWORD"],
            }
        )
    return accounts


def match_whatsapp_company(chat_id):
    mapping = json.loads(os.environ.get("WHATSAPP_COMPANY_MAP", "{}"))
    for key, company in mapping.items():
        if key in chat_id:
            return company
    return "general"
