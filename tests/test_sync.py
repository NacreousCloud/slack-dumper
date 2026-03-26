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
