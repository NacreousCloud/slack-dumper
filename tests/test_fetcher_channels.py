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
