# Personal EA / Chief-of-Staff

Laptop-resident system that reads email (and, optionally, WhatsApp) on a
wake/sleep cycle, has Claude turn new messages into trackable work items,
stores them in SQLite, and reaches you via Telegram. Built per
`personal-ea-build-guide.md`, all four phases.

| Phase | What it adds | Status |
|---|---|---|
| 1 | One email account, Claude classification, SQLite, Telegram digest + inbound commands | Built |
| 2 | Remaining email accounts, WhatsApp (Baileys, read-only), Gemini router for wording | Built |
| 3 | Stale-item alerts, weekly per-company summaries, `/done` and `/snooze` | Built |
| 4 | `/draft` reply suggestions, WhatsApp Business API (opt-in), local-model privacy mode | Built, two are opt-in scaffolding — see below |

Two Phase 4 pieces are code you can turn on, not things that can be proven
working from here: **WhatsApp Business API sending** needs a Meta Business
Account and phone number that only you can set up (details in
`connectors/whatsapp_business.py`), and it is deliberately **not called by
anything** in this codebase — nothing here auto-sends, on any channel, ever.
**Local-model privacy mode** needs Ollama running on your machine; the
classification prompt is reused verbatim from `brain/claude_agent.py` but
untested against a live Ollama instance in this environment.

## Setup

1. **Telegram bot**: message `@BotFather` → `/newbot` → save the token. Send
   the bot a message, then hit `https://api.telegram.org/bot<token>/getUpdates`
   to find your chat id.
2. **Claude Code**: install Claude Code and run `claude login` with your
   Pro/Max account. Confirm `ANTHROPIC_API_KEY` is *not* set
   (`echo $ANTHROPIC_API_KEY` should print nothing) — its presence silently
   switches billing to the paid API instead of your subscription.
3. **Email app passwords**: generate one per account (Gmail, Outlook, Zoho —
   each has its own "App Passwords" setting under account security; requires
   2FA).
4. Copy `.env.example` to `.env` and fill in at least `EMAIL_1_*` and the
   Telegram values.
5. **Create the DB**: `python main.py` calls `init_db` automatically, or run
   `sqlite3 ea.db < db/schema.sql` directly.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill it in
```

**Test end-to-end on one email account + Telegram before enabling anything
else below.**

## Running

- `python main.py` — one wake cycle: fetch new email (and WhatsApp, if
  enabled), classify, write to SQLite, send a digest if anything actionable
  came in. This is what the scheduler calls repeatedly.
- `python bot_server.py` — the always-on inbound side (long-polling). Run as
  a separate, continuously-running process.
- `python stale_check.py` — Phase 3, run daily.
- `python weekly_summary.py` — Phase 3, run weekly.

## Telegram commands

- `add followup: <description>` — track a new item (company is
  auto-matched against known companies, else filed under "general")
- `/status [company]` — list open items, with their `#id`
- `/done <id>` — mark an item done
- `/snooze <id> <YYYY-MM-DD>` — push out its due date
- `/draft <id>` — Claude drafts a reply for the item; it is only ever
  returned to you in Telegram, never sent anywhere

## Phase 2: more email accounts

Fill in `EMAIL_2_*` / `EMAIL_3_*` in `.env`. `main.py` loops over whichever
`EMAIL_N_*` blocks have `EMAIL_N_ACCOUNT` set — the same IMAP connector
function handles all three, it's just called again per account.

## Phase 2: WhatsApp (Baileys)

1. `cd connectors && npm install` (installs `@whiskeysockets/baileys`).
2. `node connectors/whatsapp_baileys.js 0` — scan the printed QR code with
   your phone. The session is saved under `.whatsapp-auth/` (gitignored) —
   **back this folder up**; losing it means re-scanning.
3. Run the same command again to confirm it reconnects without a new QR
   code.
4. Set `WHATSAPP_ENABLED=true` and, if you want messages tagged by company
   rather than landing under "general", fill in `WHATSAPP_COMPANY_MAP`.

This connector is read/track-only by design — it never sends a WhatsApp
message. Each wake cycle reconnects, fetches anything new, and disconnects;
it never holds a persistent connection, which is the main defense against
WhatsApp's automation detection. If a reconnect fails, `main.py` sends you a
Telegram alert instead of failing silently.

## Phase 2: Gemini router

Get a free-tier key at aistudio.google.com and set `GEMINI_API_KEY`. Once
set, `brain/router.py` starts using it for digest wording and (Phase 3)
summary/alert wording — all of which are composed from already-extracted
structured fields, never raw message content. Classification of raw
email/WhatsApp text always goes to Claude (or the local model, see Phase 4),
never Gemini; the router only reaches Gemini when a caller explicitly passes
`structured_only=True` — it never infers that from a prompt's content. If
Gemini errors or rate-limits, calls fall back to Claude automatically.

## Phase 3: stale items and weekly summaries

Set `STALE_DAYS` (default 5) and wire up `stale_check.py` (daily) and
`weekly_summary.py` (weekly) via the scheduler — see below. Both are
separate from the main ingestion cycle so they run on their own cadence.

## Phase 4: draft replies

Already active — see `/draft <id>` above. Drafts are generated by Claude
from the stored item fields (company, description, next action); this
system never stores full raw message bodies, so drafts work from the
extracted summary rather than the original text.

## Phase 4: WhatsApp Business API (opt-in, not wired in)

`connectors/whatsapp_business.py` has a `send_message(to, text)` function
and nothing else calls it. To use it you need, on Meta's side (not
something this codebase can do for you):

1. A Meta Business Account and WhatsApp Business Account (WABA).
2. A phone number verified with that WABA — **must be different** from the
   personal number the Baileys connector reads.
3. A permanent access token (System User token via Meta Business Settings —
   the default temporary token expires in 24h).
4. The `phone_number_id` from Meta's API setup page.

Set `WHATSAPP_BUSINESS_TOKEN` / `WHATSAPP_BUSINESS_PHONE_ID`, then call
`send_message()` from wherever you decide automated sending should actually
happen — e.g. a new command that takes a `/draft` result and asks for
confirmation before sending. Nothing here does that automatically; per the
guide, this stays a deliberate, separate step.

## Phase 4: local-model privacy mode

Set `PRIVACY_MODE=local`. `brain/router.py` then sends raw content to
`brain/local_client.py` (Ollama) instead of Claude for classification —
nothing leaves the machine, at the cost of classification quality. Requires
[Ollama](https://ollama.com) running locally with a model pulled, e.g.
`ollama pull llama3.1`. `OLLAMA_HOST` / `OLLAMA_MODEL` are configurable.

## Scheduling (Linux / systemd)

Edit the paths in `scheduler/*.service`, then:

```bash
cp scheduler/personal-ea.service scheduler/personal-ea.timer /etc/systemd/system/
cp scheduler/personal-ea-stale.service scheduler/personal-ea-stale.timer /etc/systemd/system/
cp scheduler/personal-ea-weekly.service scheduler/personal-ea-weekly.timer /etc/systemd/system/
cp scheduler/personal-ea-bot.service /etc/systemd/system/

systemctl enable --now personal-ea.timer          # periodic email/WhatsApp cycle
systemctl enable --now personal-ea-stale.timer    # daily stale check
systemctl enable --now personal-ea-weekly.timer   # weekly summary
systemctl enable --now personal-ea-bot.service    # always-on Telegram inbound
```

On macOS use `launchd` agents with the same split (periodic jobs for
`main.py`/`stale_check.py`/`weekly_summary.py`, and a `KeepAlive` agent for
`bot_server.py`). On Windows, use Task Scheduler for the periodic scripts on
repeating triggers, and a startup task (or a service via NSSM) for
`bot_server.py`.

Start the main cycle interval at 15–30 minutes and tune from there.

## Risk notes (from the build guide, and how this build addresses them)

- **WhatsApp flagged as automated** — read-only, reconnect/fetch/disconnect
  per cycle, never a persistent connection, never sends.
- **Gemini rate limits** — every wording call batches all items for the
  cycle/day/week into one prompt, not one call per item.
- **Router misclassifies something sensitive as safe** — `router.compose`
  only reaches Gemini when a caller passes `structured_only=True` outright;
  raw content never goes through `compose` at all, only `classify`, which
  never touches Gemini.
- **Claude subscription usage pooled with regular use** — batched per
  company per cycle, not per message; keep an eye on `/status` in Claude
  Code if you're a heavy user elsewhere.
- **`ANTHROPIC_API_KEY` silently switching to paid billing** — check it's
  unset at setup and periodically.
- **Baileys session drops** — back up `.whatsapp-auth/`; a reconnect
  failure pushes a Telegram alert instead of failing silently.
- **Laptop sleeps/reboots miss cycles** — systemd timers above are
  `Persistent=true`, so a missed run fires on the next wake.
- **Losing track of which account = which company** — the `companies`
  table centralizes the mapping; every ingestion path calls `ensure_company`
  rather than hardcoding it per script.
