import logging
from pathlib import Path

from .auth import load_cookie, load_token
from .client import SlackClient
from .db import init_db
from .fetcher.channels import sync_channels
from .fetcher.files import download_files
from .fetcher.messages import sync_messages
from .fetcher.users import sync_users

logger = logging.getLogger(__name__)


def run_sync(
    db_path: Path,
    files_dir: Path,
    skip_files: bool = False,
    channel_filter: list[str] | None = None,
):
    token = load_token()
    cookie = load_cookie()
    client = SlackClient(token, cookie=cookie)
    conn = init_db(db_path)

    logger.info("Syncing users...")
    sync_users(client, conn)

    logger.info("Syncing channels...")
    channels = sync_channels(client, conn)

    for ch in channels:
        if channel_filter and ch["id"] not in channel_filter and ch["name"] not in channel_filter:
            continue
        logger.info("Syncing messages: #%s (%s)", ch["name"], ch["id"])
        row = conn.execute(
            "SELECT last_synced_cursor FROM channels WHERE id=?", (ch["id"],)
        ).fetchone()
        oldest_ts = row["last_synced_cursor"] if row else None
        sync_messages(client, conn, ch["id"], oldest=oldest_ts)

    if not skip_files:
        logger.info("Downloading files...")
        download_files(conn, token, files_dir, cookie=cookie)

    conn.close()
    logger.info("Done.")


def run_download_files(db_path: Path, files_dir: Path):
    """DB에 등록된 미다운로드 파일만 내려받는다."""
    token = load_token()
    cookie = load_cookie()
    conn = init_db(db_path)

    pending = conn.execute(
        "SELECT COUNT(*) FROM files WHERE downloaded=0 AND url_private IS NOT NULL"
    ).fetchone()[0]
    logger.info("Pending files to download: %d", pending)

    download_files(conn, token, files_dir, cookie=cookie)
    conn.close()
    logger.info("Done.")
