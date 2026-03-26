import sqlite3

from ..client import SlackClient


def sync_users(client: SlackClient, conn: sqlite3.Connection):
    for raw in client.paginate("users_list", "members"):
        conn.execute(
            """
            INSERT OR REPLACE INTO users
                (id, name, display_name, real_name, avatar_url, is_bot)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                raw["id"],
                raw.get("name", ""),
                raw.get("profile", {}).get("display_name", ""),
                raw.get("profile", {}).get("real_name", ""),
                raw.get("profile", {}).get("image_72", ""),
                int(raw.get("is_bot", False)),
            ),
        )
    conn.commit()
