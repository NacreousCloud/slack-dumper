import json
import sqlite3
import logging
from datetime import datetime, timezone

from ..client import SlackClient

logger = logging.getLogger(__name__)


def _msg_id(channel_id: str, ts: str) -> str:
    return f"{channel_id}:{ts}"


def sync_messages(
    client: SlackClient,
    conn: sqlite3.Connection,
    channel_id: str,
    oldest: str | None = None,
):
    """채널 메시지를 수집. oldest를 주면 증분 동기화."""
    kwargs = {"channel": channel_id}
    if oldest:
        kwargs["oldest"] = oldest

    thread_tss: list[str] = []

    for raw in client.paginate("conversations_history", "messages", **kwargs):
        msg_id = _msg_id(channel_id, raw["ts"])
        conn.execute(
            """
            INSERT OR REPLACE INTO messages
                (id, channel_id, ts, user_id, text, thread_ts, reply_count, has_files, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                channel_id,
                raw["ts"],
                raw.get("user"),
                raw.get("text", ""),
                raw.get("thread_ts"),
                raw.get("reply_count", 0),
                int(bool(raw.get("files"))),
                json.dumps(raw),
            ),
        )
        # 파일 메타데이터 저장
        for f in raw.get("files", []):
            conn.execute(
                """
                INSERT OR IGNORE INTO files (id, message_id, name, mimetype, size, url_private)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f["id"],
                    msg_id,
                    f.get("name"),
                    f.get("mimetype"),
                    f.get("size"),
                    f.get("url_private_download") or f.get("url_private"),
                ),
            )
        if raw.get("reply_count", 0) > 0:
            thread_tss.append(raw["ts"])

    conn.commit()

    # 스레드 댓글 수집
    for thread_ts in thread_tss:
        _sync_thread(client, conn, channel_id, thread_ts)

    # 마지막 ts를 cursor로 저장 (증분 동기화용)
    last = conn.execute(
        "SELECT ts FROM messages WHERE channel_id=? ORDER BY ts DESC LIMIT 1",
        (channel_id,),
    ).fetchone()
    if last:
        conn.execute(
            "UPDATE channels SET last_synced_cursor=?, synced_at=? WHERE id=?",
            (last["ts"], datetime.now(timezone.utc).isoformat(), channel_id),
        )
        conn.commit()


def _sync_thread(
    client: SlackClient,
    conn: sqlite3.Connection,
    channel_id: str,
    thread_ts: str,
):
    for raw in client.paginate(
        "conversations_replies",
        "messages",
        channel=channel_id,
        ts=thread_ts,
    ):
        if raw["ts"] == thread_ts:
            continue  # 루트 메시지는 이미 저장됨
        msg_id = _msg_id(channel_id, raw["ts"])
        conn.execute(
            """
            INSERT OR REPLACE INTO messages
                (id, channel_id, ts, user_id, text, thread_ts, reply_count, has_files, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                channel_id,
                raw["ts"],
                raw.get("user"),
                raw.get("text", ""),
                thread_ts,
                0,
                int(bool(raw.get("files"))),
                json.dumps(raw),
            ),
        )
    conn.commit()
