import tempfile
from unittest.mock import MagicMock

from slack_dumper.db import init_db
from slack_dumper.fetcher.channels import sync_channels


def _make_mock_client(channels):
    client = MagicMock()
    client.paginate.return_value = iter(channels)
    return client


def test_sync_channels_saves_member_channels():
    raw = [
        {
            "id": "C1",
            "name": "general",
            "is_member": True,
            "is_private": False,
            "is_im": False,
            "is_mpim": False,
            "topic": {"value": ""},
            "purpose": {"value": ""},
            "num_members": 5,
        },
        {
            "id": "C2",
            "name": "secret",
            "is_member": False,
            "is_private": True,
            "is_im": False,
            "is_mpim": False,
            "topic": {"value": ""},
            "purpose": {"value": ""},
            "num_members": 2,
        },
    ]
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        result = sync_channels(_make_mock_client(raw), conn)
        rows = conn.execute("SELECT id FROM channels").fetchall()
    assert len(result) == 1
    assert result[0]["id"] == "C1"
    assert len(rows) == 1


def test_sync_channels_preserves_cursor_on_resync():
    """채널 재동기화 시 last_synced_cursor가 초기화되지 않아야 함"""
    raw = [
        {
            "id": "C1",
            "name": "general",
            "is_member": True,
            "is_private": False,
            "is_im": False,
            "is_mpim": False,
            "topic": {"value": ""},
            "purpose": {"value": ""},
            "num_members": 5,
        },
    ]
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        sync_channels(_make_mock_client(raw), conn)
        conn.execute(
            "UPDATE channels SET last_synced_cursor='1234.5678' WHERE id='C1'"
        )
        conn.commit()
        sync_channels(_make_mock_client(raw), conn)
        row = conn.execute(
            "SELECT last_synced_cursor FROM channels WHERE id='C1'"
        ).fetchone()
    assert row["last_synced_cursor"] == "1234.5678"
