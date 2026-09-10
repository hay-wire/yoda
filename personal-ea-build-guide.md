# Personal EA / Chief-of-Staff System — Build Guide

**Goal:** A laptop-resident system that reads WhatsApp + 3 email accounts (Gmail, Outlook, Zoho) on a wake/sleep cycle, tracks work items per company, flags things going stale, and talks to you via Telegram — without 23 agents, without paying for a separate LLM API on top of what you already have.

---

## 1. Architecture Overview

```
                    ┌─────────────────────┐
                    │   Scheduler (cron/   │
                    │   systemd timer)     │
                    │   wakes every N min  │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                                  ▼
     ┌─────────────────┐              ┌─────────────────────┐
     │  WhatsApp reader │              │  Email reader (IMAP) │
     │  (Baileys)       │              │  Gmail / Outlook /   │
     │  reconnect →     │              │  Zoho — 3 accounts   │
     │  fetch new →     │              │  fetch since last    │
     │  disconnect      │              │  UID/timestamp       │
     └────────┬─────────┘              └──────────┬───────────┘
              │                                    │
              └────────────────┬───────────────────┘
                                ▼
                    ┌────────────────────────┐
                    │   Router: sensitive?    │
                    └──────┬───────────┬──────┘
                    yes (default)      no
                           ▼             ▼
              ┌─────────────────┐  ┌──────────────────┐
              │ Claude (Agent   │  │ Gemini free API    │
              │ SDK / claude -p,│  │ (digest wording,   │
              │ Pro/Max plan)   │  │ generic summaries) │
              │ raw msg/email   │  │ structured/        │
              │ content         │  │ aggregate data only│
              └────────┬────────┘  └─────────┬─────────┘
                        └──────────┬──────────┘
                                   ▼
                    ┌────────────────────────┐
                    │   SQLite pipeline DB    │
                    │   (items, checkpoints)  │
                    └────────────┬─────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │   Telegram Bot          │
                    │   - pushes digest       │
                    │     (only if actionable)│
                    │   - always-on for your  │
                    │     inbound commands    │
                    └────────────────────────┘
```

**Key design decisions locked in from our discussion:**
- No multi-agent sprawl — one orchestrator script, a handful of functions, not 23 personas.
- Wake/sleep cycle, not always-on listeners — safer for WhatsApp, lighter on resources.
- Telegram bot's *inbound* side stays always-on (long-polling is cheap); only WhatsApp/email ingestion sleeps.
- IMAP for all 3 email accounts instead of 3 separate API integrations (Gmail API / Graph API / Zoho API).
- WhatsApp via unofficial client (Baileys) since official Business API can't read your existing personal chats.
- LLM: **hybrid** — Claude, via the Agent SDK / `claude -p` running on your existing Pro/Max subscription, is the **default** brain for anything touching raw email/WhatsApp content. Gemini's free API only handles tasks that don't need that raw content.

---

## 2. Component Details

### 2.1 Telegram Bot (interface)
- Library: `python-telegram-bot` (or `node-telegram-bot-api` if you go Node end-to-end).
- Two jobs:
  1. **Outbound digest** — sent only when there's something actionable (new item, stale followup, deadline approaching). Not a fixed-interval ping.
  2. **Inbound commands** — you can text it things like `add followup: call Essar Friday` or `status Kalastra`. This side runs continuously via long-polling; it's cheap enough to leave on.

### 2.2 Email Ingestion (IMAP × 3)
- Library: Python `imaplib` + `email` (stdlib), or `imap-tools` for a cleaner API.
- One connector function, called 3 times with different credentials — not 3 separate codepaths.
- Each account is tagged with a `company` value at ingest time (config-driven — you map account → company once).
- Auth: use **app passwords**, not your main password:
  - Gmail → Google Account → Security → App Passwords (requires 2FA enabled)
  - Outlook → Microsoft Account → Security → App passwords
  - Zoho Mail → Zoho Account → Security → App Passwords
- Fetch strategy: track last-seen UID per account in the checkpoints table; on each wake, fetch only UIDs greater than that.

### 2.3 WhatsApp Ingestion (Baileys)
- Library: `Baileys` (Node.js — this is the one component best done in Node even if the rest is Python; you can shell out to a small Node script from Python, or just run the whole system in Node).
- Flow per wake cycle: reconnect using saved session credentials (auth folder from first QR scan) → fetch messages since last checkpoint timestamp → disconnect cleanly.
- **Keep this read/track-only.** Don't auto-send replies through it — that's the highest-risk action for triggering WhatsApp's automation detection. Drafting replies for you to send manually is a safer v1 behavior than auto-sending.
- Session lives in a local auth folder on your laptop — back it up, since a lost session means re-scanning the QR code.

### 2.4 Brain (LLM layer) — hybrid: Claude by default, Gemini for the rest

**The split is by data sensitivity, not by task type:**

| Route to | When |
|---|---|
| **Claude (default)** | Anything that touches raw email/WhatsApp content — extracting action items, classifying by company, judging urgency/stage from actual message text. This is most of what the brain does, since real client/business content flows through it. |
| **Gemini free API** | Anything that only touches *already-extracted, structured* data — composing the Telegram digest wording from the pipeline table's fields, generating a weekly summary from aggregate counts, any generic non-business drafting. No raw message content ever gets sent to Gemini. |

A simple `router.py` decides this per call — in practice it's almost binary: raw content in → Claude; structured fields already sitting in SQLite → Gemini is fine.

**Claude — via Agent SDK / `claude -p`, on your existing Pro/Max subscription:**
- This is officially supported: the Agent SDK (Python or TypeScript) and `claude -p` (Claude Code's non-interactive mode) authenticate with your Pro/Max login and draw from your subscription's usage limits — not pay-per-token billing.
- Setup: install Claude Code, log in with your Pro/Max credentials, and make sure no `ANTHROPIC_API_KEY` environment variable is set anywhere on the machine — its presence silently switches calls to paid API billing.
- Your `main.py` orchestrator either imports the Agent SDK directly, or shells out to `claude -p "<prompt with new messages>"` and parses the response.
- **Caveat:** this usage is pooled with your regular Claude.ai chat and interactive Claude Code usage, not a separate bucket. A wake cycle every 15–30 min with batched calls (one call per source per cycle, not per message) should be light, but keep an eye on `/status` if you're also a heavy Claude.ai user for your other company work. Anthropic positions this tier for individual automation, not scaled production — which is exactly this use case.

**Gemini — free tier (Google AI Studio), for the non-sensitive slice only:**
- Currently Flash-only on the free tier, roughly 10–15 requests/minute and a daily cap that's changed multiple times in 2026 — check current numbers at ai.google.dev rather than architecting around a fixed figure.
- Since it only ever sees structured/aggregate data under this split, the "free-tier data may train Google's models" caveat is much less of a concern than it would be if raw messages went through it.

**What the brain actually produces per cycle:** structured JSON — `{item, company, channel, stage, next_action, due_date, urgency}` — written to the pipeline table. Claude produces this from raw content; Gemini only ever consumes it downstream for wording/summaries.

### 2.5 Data Store — SQLite
Single file, no server to manage, trivial to back up (just copy the `.db` file).

```sql
-- Pipeline items: the actual "don't lose this" table
CREATE TABLE pipeline_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    channel TEXT NOT NULL,           -- 'whatsapp' | 'gmail' | 'outlook' | 'zoho'
    item TEXT NOT NULL,              -- short description
    stage TEXT,                      -- e.g. 'new', 'in progress', 'waiting on them', 'stalled'
    next_action TEXT,
    due_date DATE,
    last_touched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_ref TEXT,                 -- message id / email id for traceability
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Checkpoints: what's already been read, per source
CREATE TABLE checkpoints (
    channel TEXT NOT NULL,
    account TEXT NOT NULL,           -- email address, or 'whatsapp' for the single WA account
    last_checked_at TIMESTAMP,
    last_uid TEXT,                   -- IMAP UID or WhatsApp message id/timestamp
    PRIMARY KEY (channel, account)
);

-- Companies: config, not really queried much, just keeps mapping explicit
CREATE TABLE companies (
    name TEXT PRIMARY KEY,
    email_account TEXT
);
```

### 2.6 Scheduler
- **Linux/Mac laptop:** `systemd` timer (Linux) or `launchd` (Mac) is more reliable than cron for "always-on laptop" since it handles sleep/wake better and can catch up on missed runs.
- **Windows:** Task Scheduler.
- Interval: start at every 15–30 minutes. Tune based on how urgent your followups actually are — WhatsApp business conversations probably want tighter intervals than email.

---

## 3. Tech Stack Summary

| Layer | Choice | Why |
|---|---|---|
| Language | Python (+ small Node script for Baileys) | IMAP, SQLite, Telegram all have solid Python libs; Baileys is Node-only |
| WhatsApp | Baileys | Only realistic way to read your existing personal chats for free |
| Email | IMAP (imaplib / imap-tools) | One connector for Gmail + Outlook + Zoho instead of 3 APIs |
| LLM (default) | Claude via Agent SDK / `claude -p`, on Pro/Max subscription | Handles all raw email/WhatsApp content; officially draws from subscription usage, not paid API |
| LLM (secondary) | Gemini free tier (Flash) | Only for tasks on already-structured/aggregate data — digest wording, summaries |
| Storage | SQLite | Zero-ops, single file, easy backup |
| Interface | Telegram Bot API | Two-way, free, reliable |
| Scheduler | systemd timer / launchd / Task Scheduler | Handles sleep/wake better than plain cron |

---

## 4. Build Phases

**Phase 1 — MVP (build this first, nothing else):**
Telegram bot (inbound + outbound) + SQLite schema + **one** email account ingestion + Claude (Agent SDK/`claude -p`) classification + daily digest. Skip the Gemini routing entirely at this stage — a single-source MVP has nothing "non-sensitive" to route yet. Prove the loop works before adding sources or the router.

**Phase 2 — Add sources:**
Remaining 2 email accounts, then WhatsApp (Baileys) last, since it's the most fragile piece.

**Phase 3 — Add intelligence:**
Stale-item detection ("hasn't moved in 5 days"), per-company weekly summaries, Telegram commands for you to update items manually (`done X`, `snooze Y`).

**Phase 4 — Only if Phase 1–3 feel solid:**
Draft-reply suggestions (never auto-send), WhatsApp Business API migration if you want to eventually automate sending, local model swap for privacy.

---

## 5. Setup Steps (in order)

1. **Telegram bot:** message `@BotFather` on Telegram → `/newbot` → save the token.
2. **Claude Code / Agent SDK:** install Claude Code, run `claude login`, authenticate with your Pro/Max credentials. Confirm `ANTHROPIC_API_KEY` is **not** set in your environment (`echo $ANTHROPIC_API_KEY` should return nothing) so calls draw from your subscription, not paid API credits.
3. **Gemini API key:** Google AI Studio (aistudio.google.com) → Get API key → no billing needed for free tier. Only needed once you build the router in Phase 2+.
4. **Email app passwords:** generate for Gmail, Outlook, Zoho as described in 2.2. Store in a `.env` file, never in code.
5. **Baileys session:** run the Baileys quick-start once locally, scan the QR code with your phone, confirm the auth folder persists a session (reconnect without re-scanning).
6. **SQLite DB:** run the schema above once to create `ea.db`.
7. **Scheduler:** wire up the systemd timer / launchd job / Task Scheduler entry to run your main script every 15–30 min.
8. **Test end-to-end on one email account + Telegram first**, before touching WhatsApp or adding the Gemini router.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| WhatsApp session flagged as automated | Read-only, wake/sleep cycle (not always-on), never auto-send, keep it on your own laptop session |
| Gemini free-tier rate limits hit | Batch messages per cycle rather than per-item calls; this path only handles the lighter, non-sensitive load anyway |
| Router misclassifies something sensitive as safe to send to Gemini | Default to Claude when in doubt — the router should require an explicit "structured-only" flag on a call to route to Gemini, not infer it |
| Claude subscription usage pooled with regular Claude.ai/Claude Code use | Batch calls per cycle (not per-message); monitor `/status`; this tier is meant for exactly this kind of individual automation |
| `ANTHROPIC_API_KEY` accidentally set, silently switching to paid billing | Check env vars at setup and periodically; keep credentials in `.env`, never export globally |
| Baileys session drops | Back up the auth folder; script should alert you via Telegram if reconnect fails, not fail silently |
| Laptop sleeps/reboots and misses cycles | systemd/launchd catch-up on wake is more forgiving than plain cron here |
| Losing track of which email account = which company | `companies` table makes the mapping explicit and centralized, not hardcoded per script |

---

## 7. Suggested Folder Structure

```
personal-ea/
├── .env                     # credentials — never commit
├── ea.db                    # SQLite database
├── main.py                  # orchestrator — called by scheduler each wake
├── connectors/
│   ├── email_imap.py
│   ├── whatsapp_baileys.js  # shelled out to, or run as a sidecar
│   └── telegram_bot.py
├── brain/
│   ├── router.py             # decides Claude vs Gemini per call
│   ├── claude_agent.py       # Agent SDK / claude -p calls — default, raw content
│   └── gemini_client.py      # Gemini free API — structured/aggregate data only
├── db/
│   └── schema.sql
└── scheduler/
    └── personal-ea.timer    # or launchd .plist / Task Scheduler XML
```

---

## Next Step
Start with Phase 1 only: Telegram bot + SQLite + one email account + Claude (Agent SDK/`claude -p`) classification + daily digest. The Gemini router is a Phase 2+ addition once you've actually got structured, non-sensitive data worth offloading. Everything else in this doc is where to go once that loop is running reliably for about a week.
