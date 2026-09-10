"""Telegram bot inbound side. Runs continuously (long-polling) as its own
process/service, separate from main.py which only runs per wake cycle."""

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from db.database import get_connection, get_open_items, init_db, insert_pipeline_item, list_companies

load_dotenv()
logging.basicConfig(level=logging.INFO)

DB_PATH = os.environ.get("EA_DB_PATH", "ea.db")

HELP_TEXT = (
    "Personal EA bot.\n\n"
    "add followup: <description> - track a new item\n"
    "/status [company] - list open items, optionally filtered by company"
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
        lines.append(f"- [{item['company']}] {item['item']} - {item.get('stage') or 'new'}{due}")
    await update.message.reply_text("\n".join(lines))


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


def main():
    init_db(DB_PATH)
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()
