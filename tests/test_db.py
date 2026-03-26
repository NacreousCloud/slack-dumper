import tempfile

from slack_dumper.db import init_db


def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "channels" in tables
        assert "messages" in tables
        assert "files" in tables
        assert "users" in tables
        conn.close()


def test_init_db_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        init_db(f.name)
        init_db(f.name)  # 두 번 호출해도 에러 없어야 함
