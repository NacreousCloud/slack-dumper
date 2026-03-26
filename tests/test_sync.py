import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from slack_dumper.sync import run_sync


def test_run_sync_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        files_dir = Path(tmpdir) / "files"

        mock_client = MagicMock()
        mock_client.paginate.side_effect = lambda *args, **kwargs: iter([])

        with (
            patch("slack_dumper.sync.load_token", return_value="xoxp-test"),
            patch("slack_dumper.sync.SlackClient", return_value=mock_client),
        ):
            run_sync(db_path=db_path, files_dir=files_dir, skip_files=True)

        assert db_path.exists()


def test_run_sync_channel_filter():
    """channel_filter가 있으면 해당 채널만 메시지 수집"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        files_dir = Path(tmpdir) / "files"

        channels = [
            {"id": "C1", "name": "general", "type": "public"},
            {"id": "C2", "name": "random", "type": "public"},
        ]
        message_calls = []

        mock_client = MagicMock()
        mock_client.paginate.side_effect = lambda *a, **kw: iter([])

        with (
            patch("slack_dumper.sync.load_token", return_value="xoxp-test"),
            patch("slack_dumper.sync.SlackClient", return_value=mock_client),
            patch("slack_dumper.sync.sync_channels", return_value=channels),
            patch("slack_dumper.sync.sync_users"),
            patch(
                "slack_dumper.sync.sync_messages",
                side_effect=lambda *a, **kw: message_calls.append(a[2]),
            ),
        ):
            run_sync(
                db_path=db_path,
                files_dir=files_dir,
                skip_files=True,
                channel_filter=["general"],
            )

        assert message_calls == ["C1"]
