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


def get_item(conn, item_id):
    row = conn.execute("SELECT * FROM pipeline_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def get_open_items(conn, company=None, include_done=False):
    clauses = [] if include_done else ["(stage IS NULL OR stage != 'done')"]
    params = []
    if company:
        clauses.append("company = ?")
        params.append(company)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT * FROM pipeline_items {where}
            ORDER BY due_date IS NULL, due_date, last_touched DESC""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_stale_items(conn, days, company=None):
    """Phase 3: items that haven't moved in `days`+ days and aren't done."""
    params = [days]
    company_clause = ""
    if company:
        company_clause = "AND company = ?"
        params.append(company)

    rows = conn.execute(
        f"""SELECT * FROM pipeline_items
            WHERE (stage IS NULL OR stage != 'done')
              AND julianday('now') - julianday(last_touched) >= ?
              {company_clause}
            ORDER BY last_touched ASC""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def mark_done(conn, item_id):
    cursor = conn.execute(
        "UPDATE pipeline_items SET stage = 'done', last_touched = CURRENT_TIMESTAMP WHERE id = ?",
        (item_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def snooze_item(conn, item_id, new_due_date):
    cursor = conn.execute(
        "UPDATE pipeline_items SET due_date = ?, last_touched = CURRENT_TIMESTAMP WHERE id = ?",
        (new_due_date, item_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_weekly_stats(conn, days=7, stale_days=5):
    """Phase 3: aggregate counts only, per company - the input a weekly
    summary needs, and structured enough to hand to the Gemini path."""
    companies = [row["company"] for row in conn.execute("SELECT DISTINCT company FROM pipeline_items")]

    stats = {}
    for company in companies:
        new_count = conn.execute(
            "SELECT COUNT(*) AS c FROM pipeline_items WHERE company = ? AND created_at >= datetime('now', ?)",
            (company, f"-{days} days"),
        ).fetchone()["c"]
        done_count = conn.execute(
            """SELECT COUNT(*) AS c FROM pipeline_items
               WHERE company = ? AND stage = 'done' AND last_touched >= datetime('now', ?)""",
            (company, f"-{days} days"),
        ).fetchone()["c"]
        open_count = conn.execute(
            "SELECT COUNT(*) AS c FROM pipeline_items WHERE company = ? AND (stage IS NULL OR stage != 'done')",
            (company,),
        ).fetchone()["c"]
        stale_count = len(get_stale_items(conn, stale_days, company=company))

        stats[company] = {
            "new": new_count,
            "done": done_count,
            "open": open_count,
            "stale": stale_count,
        }
    return stats
