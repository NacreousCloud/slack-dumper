from unittest.mock import MagicMock

import tempfile

from slack_dumper.db import init_db
from slack_dumper.fetcher.messages import sync_messages


def _make_client(messages, thread_replies=None):
    client = MagicMock()

    def paginate(method, key, **kwargs):
        if method == "conversations_history":
            return iter(messages)
        if method == "conversations_replies":
            return iter(thread_replies or [])
        return iter([])

    client.paginate.side_effect = paginate
    return client


def test_sync_messages_saves_messages():
    msgs = [
        {
            "ts": "1000.0",
            "user": "U1",
            "text": "hello",
            "files": [],
            "reply_count": 0,
        }
    ]
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        conn.execute(
            "INSERT INTO channels (id, name, type) VALUES ('C1', 'g', 'public')"
        )
        conn.commit()
        sync_messages(_make_client(msgs), conn, "C1")
        rows = conn.execute("SELECT * FROM messages").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "hello"


def test_sync_messages_fetches_thread_replies():
    root = {
        "ts": "1000.0",
        "user": "U1",
        "text": "root",
        "files": [],
        "reply_count": 1,
        "thread_ts": "1000.0",
    }
    reply = {
        "ts": "1001.0",
        "user": "U2",
        "text": "reply",
        "files": [],
        "reply_count": 0,
        "thread_ts": "1000.0",
    }
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        conn.execute(
            "INSERT INTO channels (id, name, type) VALUES ('C1', 'g', 'public')"
        )
        conn.commit()
        sync_messages(_make_client([root], [root, reply]), conn, "C1")
        rows = conn.execute("SELECT ts FROM messages ORDER BY ts").fetchall()
    assert [r["ts"] for r in rows] == ["1000.0", "1001.0"]
