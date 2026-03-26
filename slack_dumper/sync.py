import logging
from pathlib import Path

from .auth import load_token
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
    client = SlackClient(token)
    conn = init_db(db_path)

    logger.info("Syncing users...")
    sync_users(client, conn)

    logger.info("Syncing channels...")
    channels = sync_channels(client, conn)

    for ch in channels:
        if channel_filter and ch["id"] not in channel_filter and ch["name"] not in channel_filter:
            continue
        logger.info("Syncing messages: #%s (%s)", ch["name"], ch["id"])
        oldest = conn.execute(
            "SELECT last_synced_cursor FROM channels WHERE id=?", (ch["id"],)
        ).fetchone()
        oldest_ts = oldest["last_synced_cursor"] if oldest else None
        sync_messages(client, conn, ch["id"], oldest=oldest_ts)

    if not skip_files:
        logger.info("Downloading files...")
        download_files(conn, token, files_dir)

    conn.close()
    logger.info("Done.")
