SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT,
    display_name TEXT,
    real_name TEXT,
    avatar_url TEXT,
    is_bot INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,   -- 'public', 'private', 'im', 'mpim'
    topic TEXT,
    purpose TEXT,
    member_count INTEGER,
    last_synced_cursor TEXT,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,   -- channel_id + ':' + ts
    channel_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    user_id TEXT,
    text TEXT,
    thread_ts TEXT,
    reply_count INTEGER DEFAULT 0,
    has_files INTEGER DEFAULT 0,
    raw_json TEXT,
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    name TEXT,
    mimetype TEXT,
    size INTEGER,
    url_private TEXT,
    local_path TEXT,
    downloaded INTEGER DEFAULT 0,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, ts);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_ts);
"""
