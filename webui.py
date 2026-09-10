"""Lightweight local web UI for managing the pipeline and all configuration.

Run with `python webui.py`. Binds to 127.0.0.1 by default. This page can
display and edit email app passwords, API keys, and the Telegram bot token,
so it is gated behind a single shared-secret password (WEBUI_SECRET) and
should never be bound to a non-localhost address without adding real
authentication beyond that.
"""

import os

from dotenv import dotenv_values, load_dotenv, set_key
from flask import Flask, redirect, render_template, request, session, url_for
from functools import wraps

from config import DB_PATH
from db.database import (
    delete_item,
    ensure_company,
    get_connection,
    get_item,
    get_open_items,
    get_setting,
    get_stale_items,
    init_db,
    insert_pipeline_item,
    list_companies,
    mark_done,
    remove_company,
    set_setting,
    snooze_item,
    update_item,
)

load_dotenv()

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
STALE_DAYS_DEFAULT = int(os.environ.get("STALE_DAYS", "5"))

STAGES = ["new", "in progress", "waiting on them", "stalled", "done"]
URGENCIES = ["low", "medium", "high"]

# Credential fields: blank in the settings form means "keep the current
# value" rather than "clear it" - these are never pre-filled either.
_SECRET_FIELDS = {
    "TELEGRAM_BOT_TOKEN",
    "EMAIL_1_APP_PASSWORD",
    "EMAIL_2_APP_PASSWORD",
    "EMAIL_3_APP_PASSWORD",
    "GEMINI_API_KEY",
    "WHATSAPP_BUSINESS_TOKEN",
}

_ENV_FIELDS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "EMAIL_1_COMPANY", "EMAIL_1_CHANNEL", "EMAIL_1_ACCOUNT", "EMAIL_1_APP_PASSWORD", "EMAIL_1_IMAP_HOST",
    "EMAIL_2_COMPANY", "EMAIL_2_CHANNEL", "EMAIL_2_ACCOUNT", "EMAIL_2_APP_PASSWORD", "EMAIL_2_IMAP_HOST",
    "EMAIL_3_COMPANY", "EMAIL_3_CHANNEL", "EMAIL_3_ACCOUNT", "EMAIL_3_APP_PASSWORD", "EMAIL_3_IMAP_HOST",
    "WHATSAPP_COMPANY_MAP",
    "WHATSAPP_BUSINESS_TOKEN", "WHATSAPP_BUSINESS_PHONE_ID",
    "GEMINI_API_KEY", "GEMINI_MODEL",
    "PRIVACY_MODE", "OLLAMA_HOST", "OLLAMA_MODEL",
    "STALE_DAYS",
]

app = Flask(__name__)
app.secret_key = os.environ.get("WEBUI_SECRET")

if not app.secret_key:
    raise RuntimeError("Set WEBUI_SECRET in .env before running the web UI - it gates access to it.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == app.secret_key:
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    conn = get_connection(DB_PATH)
    company_filter = request.args.get("company") or None
    items = get_open_items(conn, company=company_filter)
    stale_ids = {i["id"] for i in get_stale_items(conn, STALE_DAYS_DEFAULT)}
    companies = list_companies(conn)
    conn.close()
    return render_template(
        "dashboard.html", items=items, stale_ids=stale_ids, companies=companies, company_filter=company_filter
    )


@app.route("/items/new", methods=["GET", "POST"])
@login_required
def new_item():
    conn = get_connection(DB_PATH)
    if request.method == "POST":
        company = request.form["company"].strip() or "general"
        ensure_company(conn, company)
        insert_pipeline_item(conn, _item_fields_from_form(request.form, source_ref="webui"))
        conn.close()
        return redirect(url_for("dashboard"))
    companies = list_companies(conn)
    conn.close()
    return render_template("item_form.html", companies=companies, item=None, stages=STAGES, urgencies=URGENCIES)


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    conn = get_connection(DB_PATH)
    if request.method == "POST":
        update_item(conn, item_id, _item_fields_from_form(request.form))
        conn.close()
        return redirect(url_for("dashboard"))
    item = get_item(conn, item_id)
    companies = list_companies(conn)
    conn.close()
    if not item:
        return redirect(url_for("dashboard"))
    return render_template("item_form.html", companies=companies, item=item, stages=STAGES, urgencies=URGENCIES)


def _item_fields_from_form(form, source_ref=None):
    fields = {
        "company": form["company"].strip(),
        "channel": form.get("channel") or "manual",
        "item": form["item"].strip(),
        "stage": form.get("stage") or "new",
        "next_action": form.get("next_action") or None,
        "due_date": form.get("due_date") or None,
        "urgency": form.get("urgency") or None,
    }
    if source_ref is not None:
        fields["source_ref"] = source_ref
    return fields


@app.route("/items/<int:item_id>/done", methods=["POST"])
@login_required
def item_done(item_id):
    conn = get_connection(DB_PATH)
    mark_done(conn, item_id)
    conn.close()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/items/<int:item_id>/snooze", methods=["POST"])
@login_required
def item_snooze(item_id):
    conn = get_connection(DB_PATH)
    snooze_item(conn, item_id, request.form["due_date"])
    conn.close()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
def item_delete(item_id):
    conn = get_connection(DB_PATH)
    delete_item(conn, item_id)
    conn.close()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/companies", methods=["GET", "POST"])
@login_required
def companies():
    conn = get_connection(DB_PATH)
    if request.method == "POST":
        name = request.form["name"].strip()
        if name:
            ensure_company(conn, name, request.form.get("email_account") or None)
    rows = list_companies(conn)
    conn.close()
    return render_template("companies.html", companies=rows)


@app.route("/companies/<name>/delete", methods=["POST"])
@login_required
def company_delete(name):
    conn = get_connection(DB_PATH)
    remove_company(conn, name)
    conn.close()
    return redirect(url_for("companies"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        _save_settings(request.form)
        return redirect(url_for("settings", saved=1))

    env = dotenv_values(ENV_PATH)
    email_blocks = [
        {
            "n": n,
            "company": env.get(f"EMAIL_{n}_COMPANY", ""),
            "channel": env.get(f"EMAIL_{n}_CHANNEL", ""),
            "account": env.get(f"EMAIL_{n}_ACCOUNT", ""),
            "password_set": bool(env.get(f"EMAIL_{n}_APP_PASSWORD")),
            "imap_host": env.get(f"EMAIL_{n}_IMAP_HOST", ""),
        }
        for n in (1, 2, 3)
    ]
    conn = get_connection(DB_PATH)
    persona = get_setting(conn, "persona_instructions", "") or ""
    conn.close()
    return render_template(
        "settings.html",
        env=env,
        email_blocks=email_blocks,
        persona=persona,
        saved=request.args.get("saved"),
    )


def _save_settings(form):
    for key in _ENV_FIELDS:
        value = form.get(key, "")
        if key in _SECRET_FIELDS and not value:
            continue  # blank means "keep existing" for credential fields
        set_key(ENV_PATH, key, value)
    set_key(ENV_PATH, "WHATSAPP_ENABLED", "true" if form.get("WHATSAPP_ENABLED") == "on" else "false")

    conn = get_connection(DB_PATH)
    set_setting(conn, "persona_instructions", form.get("persona_instructions", "").strip())
    conn.close()


if __name__ == "__main__":
    init_db(DB_PATH)
    host = os.environ.get("WEBUI_HOST", "127.0.0.1")
    port = int(os.environ.get("WEBUI_PORT", "5000"))
    app.run(host=host, port=port)
