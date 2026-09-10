from itertools import islice

from imap_tools import AND, MailBox

DEFAULT_INITIAL_LIMIT = 20
MAX_BODY_CHARS = 3000


def fetch_new_messages(host, username, password, last_uid=None, initial_limit=DEFAULT_INITIAL_LIMIT):
    """One connector, reused per account/company (Gmail, Outlook, Zoho all speak IMAP).

    On the first run for an account (no checkpoint yet) only the most recent
    `initial_limit` messages are pulled, to avoid backfilling an entire mailbox.
    """
    messages = []
    with MailBox(host).login(username, password, initial_folder="INBOX") as mailbox:
        if last_uid:
            fetched = mailbox.fetch(AND(uid=f"{int(last_uid) + 1}:*"), mark_seen=False)
        else:
            fetched = islice(
                mailbox.fetch(AND(all=True), mark_seen=False, reverse=True),
                initial_limit,
            )

        for msg in fetched:
            body = (msg.text or msg.html or "").strip()
            messages.append(
                {
                    "id": msg.uid,
                    "from": msg.from_,
                    "subject": msg.subject,
                    "date": msg.date.isoformat() if msg.date else "",
                    "body": body[:MAX_BODY_CHARS],
                }
            )
    return messages
