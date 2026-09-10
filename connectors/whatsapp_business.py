"""WhatsApp Business API - Phase 4 migration path, opt-in and NOT wired into
main.py or bot_server.py by anything in this codebase.

This is the one part of the system capable of acting on your behalf toward
another person rather than just reading and drafting, which is why it stays
separate and inert until you deliberately call it. Phases 1-3 never send;
this module exists only for if/when you decide to automate sending later.

Using it requires your own setup on Meta's side, which nothing here can do
for you:
  1. A Meta Business Account and a WhatsApp Business Account (WABA).
  2. A phone number registered and verified with that WABA (this can NOT be
     the same personal number the Baileys connector in whatsapp.py reads -
     Meta requires a distinct, dedicated number for the Business API).
  3. A permanent access token for the WABA (System User token via Meta
     Business Settings; the default temporary token expires in 24h).
  4. The phone_number_id shown in Meta's API setup page for that number.

Once you have those, set WHATSAPP_BUSINESS_TOKEN and
WHATSAPP_BUSINESS_PHONE_ID in .env and call send_message() explicitly from
wherever you decide sending should happen - e.g. a new Telegram command that
takes a drafted reply (see brain.claude_agent.draft_reply) and confirms
before sending it.
"""

import os

import requests

GRAPH_API = "https://graph.facebook.com/v21.0"


def send_message(to, text):
    token = os.environ["WHATSAPP_BUSINESS_TOKEN"]
    phone_number_id = os.environ["WHATSAPP_BUSINESS_PHONE_ID"]

    response = requests.post(
        f"{GRAPH_API}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
