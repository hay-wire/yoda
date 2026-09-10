"""Telegram bot inbound side. Runs continuously (long-polling) as its own
process/service, separate from main.py which only runs per wake cycle."""

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from brain.claude_agent import draft_reply
from config import DB_PATH
from db.database import (
    get_connection,
    get_item,
    get_open_items,
    get_setting,
    init_db,
    insert_pipeline_item,
    list_companies,
    mark_done,
    snooze_item,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

HELP_TEXT = (
    "Personal EA bot.\n\n"
    "add followup: <description> - track a new item\n"
    "/status [company] - list open items, optionally filtered by company\n"
    "/done <item id> - mark an item done\n"
    "/snooze <item id> <YYYY-MM-DD> - push out an item's due date\n"
    "/draft <item id> - suggest a reply (never sent automatically)"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_connection(DB_PATH)
    company = " ".join(context.args) if context.args else None
    items = get_open_items(conn, company=company)
    conn.close()

    if not items:
        await update.message.reply_text(f"Nothing open for {company}." if company else "Nothing open.")
        return

    lines = []
    for item in items:
        due = f" (due {item['due_date']})" if item.get("due_date") else ""
        lines.append(f"#{item['id']} [{item['company']}] {item['item']} - {item.get('stage') or 'new'}{due}")
    await update.message.reply_text("\n".join(lines))


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = _parse_item_id(context.args)
    if item_id is None:
        await update.message.reply_text("Usage: /done <item id>")
        return

    conn = get_connection(DB_PATH)
    ok = mark_done(conn, item_id)
    conn.close()
    await update.message.reply_text(f"Marked #{item_id} done." if ok else f"No item #{item_id}.")


async def snooze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /snooze <item id> <YYYY-MM-DD>")
        return

    item_id = _parse_item_id(context.args[:1])
    if item_id is None:
        await update.message.reply_text("Item id must be a number.")
        return

    new_due_date = context.args[1]
    conn = get_connection(DB_PATH)
    ok = snooze_item(conn, item_id, new_due_date)
    conn.close()
    await update.message.reply_text(f"Snoozed #{item_id} to {new_due_date}." if ok else f"No item #{item_id}.")


async def draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = _parse_item_id(context.args)
    if item_id is None:
        await update.message.reply_text("Usage: /draft <item id>")
        return

    conn = get_connection(DB_PATH)
    item = get_item(conn, item_id)
    persona = get_setting(conn, "persona_instructions", "") or ""
    conn.close()
    if not item:
        await update.message.reply_text(f"No item #{item_id}.")
        return

    try:
        text = draft_reply(item, persona=persona)
    except Exception as exc:
        await update.message.reply_text(f"Draft failed: {exc}")
        return

    await update.message.reply_text(f"Draft for #{item_id} (review before sending - not sent automatically):\n\n{text}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    lowered = text.lower()

    prefix = next((p for p in ("add followup:", "add:") if lowered.startswith(p)), None)
    if not prefix:
        await update.message.reply_text(HELP_TEXT)
        return

    description = text[len(prefix):].strip()
    if not description:
        await update.message.reply_text("Add what? e.g. 'add followup: call Essar Friday'")
        return

    conn = get_connection(DB_PATH)
    company = _match_company(conn, description) or "general"
    insert_pipeline_item(
        conn,
        {
            "company": company,
            "channel": "telegram",
            "item": description,
            "stage": "new",
            "next_action": None,
            "due_date": None,
            "urgency": None,
            "source_ref": f"telegram:{update.message.message_id}",
        },
    )
    conn.close()
    await update.message.reply_text(f"Added under {company}: {description}")


def _match_company(conn, text):
    lowered = text.lower()
    for company in list_companies(conn):
        if company["name"].lower() in lowered:
            return company["name"]
    return None


def _parse_item_id(args):
    if not args:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


def main():
    init_db(DB_PATH)
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("snooze", snooze))
    app.add_handler(CommandHandler("draft", draft))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()
