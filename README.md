# Personal EA / Chief-of-Staff — Phase 1

Laptop-resident system that reads one email account, has Claude classify new
messages into trackable work items, stores them in SQLite, and reaches you
via Telegram. Built per `personal-ea-build-guide.md`, Phase 1 only:

- One email account over IMAP
- Claude classification via `claude -p` (your Pro/Max subscription, no API key)
- SQLite pipeline (`pipeline_items`, `checkpoints`, `companies`)
- Telegram bot: outbound digest (only when there's something new) + inbound
  commands (`/status`, `add followup: ...`)

WhatsApp, the second/third email accounts, and the Gemini router are Phase 2+
and intentionally not built yet.

## Setup

1. **Telegram bot**: message `@BotFather` → `/newbot` → save the token. Send
   the bot a message, then hit `https://api.telegram.org/bot<token>/getUpdates`
   to find your chat id.
2. **Claude Code**: install Claude Code and run `claude login` with your
   Pro/Max account. Confirm `ANTHROPIC_API_KEY` is *not* set
   (`echo $ANTHROPIC_API_KEY` should print nothing) — its presence silently
   switches billing to the paid API instead of your subscription.
3. **Email app password**: generate one for your chosen account (Gmail,
   Outlook, or Zoho — each has its own "App Passwords" setting under account
   security; requires 2FA).
4. Copy `.env.example` to `.env` and fill it in.
5. **Create the DB**: run `python main.py` once (it calls `init_db`
   automatically) or run `sqlite3 ea.db < db/schema.sql` directly.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill it in
```

## Running

- `python main.py` — one wake cycle: fetch new email, classify with Claude,
  write items to SQLite, send a Telegram digest if anything actionable came
  in. This is what the scheduler calls repeatedly.
- `python bot_server.py` — the always-on inbound side (long-polling). Run
  this as a separate, continuously-running process.

## Scheduling (Linux / systemd)

Edit the paths in `scheduler/*.service`, then:

```bash
cp scheduler/personal-ea.service scheduler/personal-ea.timer /etc/systemd/system/
cp scheduler/personal-ea-bot.service /etc/systemd/system/
systemctl enable --now personal-ea.timer      # periodic email cycle
systemctl enable --now personal-ea-bot.service  # always-on Telegram inbound
```

On macOS use a `launchd` agent with the same split (a periodic job calling
`main.py`, and a `KeepAlive` agent running `bot_server.py`). On Windows, use
Task Scheduler for `main.py` on a repeating trigger, and a startup task (or a
service via NSSM) for `bot_server.py`.

Start the interval at 15–30 minutes and tune from there.

## Test before adding more

Get this loop running reliably on one email account for about a week before
adding the other accounts, WhatsApp, or the Gemini router — see the build
guide for Phases 2–4.
