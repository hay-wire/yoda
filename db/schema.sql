-- Pipeline items: the actual "don't lose this" table
CREATE TABLE IF NOT EXISTS pipeline_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    channel TEXT NOT NULL,           -- 'whatsapp' | 'gmail' | 'outlook' | 'zoho' | 'telegram'
    item TEXT NOT NULL,              -- short description
    stage TEXT,                      -- e.g. 'new', 'in progress', 'waiting on them', 'stalled'
    next_action TEXT,
    due_date DATE,
    urgency TEXT,                    -- 'low' | 'medium' | 'high'
    last_touched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_ref TEXT,                 -- message id / email id for traceability
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Checkpoints: what's already been read, per source
CREATE TABLE IF NOT EXISTS checkpoints (
    channel TEXT NOT NULL,
    account TEXT NOT NULL,           -- email address, or 'whatsapp' for the single WA account
    last_checked_at TIMESTAMP,
    last_uid TEXT,                   -- IMAP UID or WhatsApp message id/timestamp
    PRIMARY KEY (channel, account)
);

-- Companies: config, not really queried much, just keeps mapping explicit
CREATE TABLE IF NOT EXISTS companies (
    name TEXT PRIMARY KEY,
    email_account TEXT
);

-- Settings: small key/value store for web-UI-managed preferences that
-- aren't credentials (those stay in .env) - e.g. personalization text.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
