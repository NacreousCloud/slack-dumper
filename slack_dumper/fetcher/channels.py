import sqlite3
from datetime import datetime, timezone

from ..client import SlackClient

CHANNEL_TYPES = "public_channel,private_channel,im,mpim"


def _channel_type(raw: dict) -> str:
    if raw.get("is_im"):
        return "im"
    if raw.get("is_mpim"):
        return "mpim"
    if raw.get("is_private"):
        return "private"
    return "public"


def sync_channels(client: SlackClient, conn: sqlite3.Connection) -> list[dict]:
    channels = []
    for raw in client.paginate("conversations_list", "channels", types=CHANNEL_TYPES):
        if not raw.get("is_member"):
            continue
        ch = {
            "id": raw["id"],
            "name": raw.get("name") or raw.get("user") or raw["id"],
            "type": _channel_type(raw),
            "topic": raw.get("topic", {}).get("value", ""),
            "purpose": raw.get("purpose", {}).get("value", ""),
            "member_count": raw.get("num_members", 0),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        conn.execute(
            """
            INSERT INTO channels (id, name, type, topic, purpose, member_count, synced_at)
            VALUES (:id, :name, :type, :topic, :purpose, :member_count, :synced_at)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                type=excluded.type,
                topic=excluded.topic,
                purpose=excluded.purpose,
                member_count=excluded.member_count,
                synced_at=excluded.synced_at
            """,
            ch,
        )
        channels.append(ch)
    conn.commit()
    return channels
