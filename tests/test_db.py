import os
import tempfile

from slack_dumper.db import get_conn, init_db


def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "workspaces" in tables
        assert "channels" in tables
        assert "messages" in tables
        assert "files" in tables
        assert "users" in tables
        conn.close()


def test_init_db_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn1 = init_db(f.name)
        conn1.close()
        conn2 = init_db(f.name)
        assert conn2 is not None
        conn2.close()


def test_get_conn_commits_and_closes():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        with get_conn(path) as conn:
            conn.execute(
                "INSERT INTO workspaces (id, name) VALUES ('W1', 'test')"
            )
        with get_conn(path) as conn:
            row = conn.execute(
                "SELECT name FROM workspaces WHERE id='W1'"
            ).fetchone()
        assert row["name"] == "test"
    finally:
        os.unlink(path)
