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


def test_download_files_verifies_file_content():
    """파일이 실제로 디스크에 저장되고 내용이 맞는지 검증"""
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

        files_dir = Path(tmpdir) / "files"
        with patch("httpx.stream", return_value=mock_response):
            download_files(conn, "xoxp-test", files_dir)

        dest = files_dir / "F1" / "img.png"
        assert dest.exists()
        assert dest.read_bytes() == b"fake-image-data"


def test_download_files_failure_skips():
    """다운로드 실패 시 downloaded=0이 유지되고 함수가 계속 실행됨"""
    import httpx as _httpx
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = init_db(":memory:")
        conn.execute(
            "INSERT INTO files (id, url_private, name, downloaded) VALUES ('F1', 'https://files.slack.com/x', 'img.png', 0)"
        )
        conn.commit()

        with patch("httpx.stream", side_effect=_httpx.RequestError("timeout")):
            download_files(conn, "xoxp-test", Path(tmpdir) / "files")

        row = conn.execute("SELECT downloaded FROM files WHERE id='F1'").fetchone()
        assert row["downloaded"] == 0
