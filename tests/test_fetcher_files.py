import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from slack_dumper.db import init_db
from slack_dumper.fetcher.files import download_files


def test_download_files_saves_to_disk():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = init_db(":memory:")
        conn.execute(
            "INSERT INTO files (id, url_private, name, downloaded) VALUES ('F1', 'https://files.slack.com/x', 'img.png', 0)"
        )
        conn.commit()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = iter([b"fake-image-data"])
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response):
            download_files(conn, "xoxp-test", Path(tmpdir) / "files")

        row = conn.execute("SELECT downloaded, local_path FROM files WHERE id='F1'").fetchone()
        assert row["downloaded"] == 1
        assert row["local_path"] is not None
