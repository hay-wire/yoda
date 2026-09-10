import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    conn.close()


def get_last_uid(conn, channel, account):
    row = conn.execute(
        "SELECT last_uid FROM checkpoints WHERE channel = ? AND account = ?",
        (channel, account),
    ).fetchone()
    return row["last_uid"] if row else None


def update_checkpoint(conn, channel, account, last_uid):
    conn.execute(
        """INSERT INTO checkpoints (channel, account, last_checked_at, last_uid)
           VALUES (?, ?, CURRENT_TIMESTAMP, ?)
           ON CONFLICT(channel, account) DO UPDATE SET
               last_checked_at = CURRENT_TIMESTAMP,
               last_uid = excluded.last_uid""",
        (channel, account, last_uid),
    )
    conn.commit()


def ensure_company(conn, name, email_account=None):
    conn.execute(
        "INSERT OR IGNORE INTO companies (name, email_account) VALUES (?, ?)",
        (name, email_account),
    )
    conn.commit()


def list_companies(conn):
    rows = conn.execute("SELECT * FROM companies").fetchall()
    return [dict(row) for row in rows]


def insert_pipeline_item(conn, item):
    conn.execute(
        """INSERT INTO pipeline_items
               (company, channel, item, stage, next_action, due_date, urgency, source_ref)
           VALUES (:company, :channel, :item, :stage, :next_action, :due_date, :urgency, :source_ref)""",
        item,
    )
    conn.commit()


def get_open_items(conn, company=None):
    if company:
        rows = conn.execute(
            """SELECT * FROM pipeline_items WHERE company = ?
               ORDER BY due_date IS NULL, due_date, last_touched DESC""",
            (company,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM pipeline_items
               ORDER BY due_date IS NULL, due_date, last_touched DESC"""
        ).fetchall()
    return [dict(row) for row in rows]
