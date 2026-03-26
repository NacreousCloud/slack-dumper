import json
import sqlite3
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _fmt_ts(ts: str) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def _fmt_date(ts: str) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y년 %m월 %d일")
    except Exception:
        return ""


def _group_messages(rows) -> list[dict]:
    """
    연속된 같은 유저의 메시지를 5분 이내면 묶어서 반환.
    각 그룹: {"msg": 첫 메시지, "continuations": [이후 메시지들], "replies": [], "files": []}
    """
    groups = []
    for row in rows:
        msg = dict(row)
        msg["fmt_ts"] = _fmt_ts(msg["ts"])
        msg["fmt_date"] = _fmt_date(msg["ts"])
        if (
            groups
            and groups[-1]["msg"]["user_id"] == msg["user_id"]
            and abs(float(msg["ts"]) - float(groups[-1]["msg"]["ts"])) < 300
        ):
            groups[-1]["continuations"].append(msg)
        else:
            groups.append({"msg": msg, "continuations": [], "replies": [], "files": []})
    return groups


def create_app(db_path: str) -> FastAPI:
    app = FastAPI(title="Slack Archive Viewer")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["fmt_ts"] = _fmt_ts
    templates.env.globals["fmt_date"] = _fmt_date
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_channels(conn):
        return conn.execute("SELECT * FROM channels ORDER BY name").fetchall()

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        conn = get_db()
        channels = _get_channels(conn)
        conn.close()
        return templates.TemplateResponse(
            "base.html",
            {"request": request, "channels": channels, "active_channel": None},
        )

    @app.get("/channel/{channel_id}", response_class=HTMLResponse)
    async def channel_view(
        request: Request,
        channel_id: str,
        before: str | None = None,
        q: str | None = None,
    ):
        conn = get_db()
        channels = _get_channels(conn)
        ch = conn.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()

        if q:
            raw_msgs = conn.execute(
                """
                SELECT m.*, u.display_name, u.real_name, u.avatar_url
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                WHERE m.channel_id=? AND m.text LIKE ?
                ORDER BY m.ts DESC LIMIT 100
                """,
                (channel_id, f"%{q}%"),
            ).fetchall()
        else:
            if before:
                raw_msgs = conn.execute(
                    """
                    SELECT m.*, u.display_name, u.real_name, u.avatar_url
                    FROM messages m
                    LEFT JOIN users u ON m.user_id = u.id
                    WHERE m.channel_id=?
                      AND (m.thread_ts IS NULL OR m.thread_ts = m.ts)
                      AND m.ts < ?
                    ORDER BY m.ts DESC LIMIT 60
                    """,
                    (channel_id, before),
                ).fetchall()
            else:
                raw_msgs = conn.execute(
                    """
                    SELECT m.*, u.display_name, u.real_name, u.avatar_url
                    FROM messages m
                    LEFT JOIN users u ON m.user_id = u.id
                    WHERE m.channel_id=?
                      AND (m.thread_ts IS NULL OR m.thread_ts = m.ts)
                    ORDER BY m.ts DESC LIMIT 60
                    """,
                    (channel_id,),
                ).fetchall()

        raw_msgs = list(reversed(raw_msgs))
        groups = _group_messages(raw_msgs)

        for group in groups:
            ts = group["msg"]["ts"]
            msg_id = f"{channel_id}:{ts}"
            group["files"] = conn.execute(
                "SELECT * FROM files WHERE message_id=?", (msg_id,)
            ).fetchall()
            if group["msg"]["reply_count"]:
                group["replies"] = conn.execute(
                    """
                    SELECT m.*, u.display_name, u.avatar_url
                    FROM messages m
                    LEFT JOIN users u ON m.user_id = u.id
                    WHERE m.thread_ts=? AND m.ts != m.thread_ts
                    ORDER BY m.ts
                    """,
                    (ts,),
                ).fetchall()

        oldest_ts = raw_msgs[0]["ts"] if raw_msgs else None
        conn.close()
        return templates.TemplateResponse(
            "channel.html",
            {
                "request": request,
                "channels": channels,
                "active_channel": ch,
                "groups": groups,
                "oldest_ts": oldest_ts,
                "query": q or "",
            },
        )

    @app.get("/api/search")
    async def search(q: str = Query(...), channel_id: str | None = None):
        conn = get_db()
        if channel_id:
            rows = conn.execute(
                """
                SELECT m.ts, m.text, m.channel_id, u.display_name, c.name as channel_name
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                LEFT JOIN channels c ON m.channel_id = c.id
                WHERE m.text LIKE ? AND m.channel_id=?
                ORDER BY m.ts DESC LIMIT 30
                """,
                (f"%{q}%", channel_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT m.ts, m.text, m.channel_id, u.display_name, c.name as channel_name
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                LEFT JOIN channels c ON m.channel_id = c.id
                WHERE m.text LIKE ?
                ORDER BY m.ts DESC LIMIT 30
                """,
                (f"%{q}%",),
            ).fetchall()
        conn.close()
        return JSONResponse([dict(r) for r in rows])

    @app.get("/files/{file_id}")
    async def serve_file(file_id: str):
        conn = get_db()
        row = conn.execute("SELECT local_path, mimetype FROM files WHERE id=?", (file_id,)).fetchone()
        conn.close()
        if row and row["local_path"] and Path(row["local_path"]).exists():
            return FileResponse(row["local_path"], media_type=row["mimetype"] or "application/octet-stream")
        return HTMLResponse("File not found", status_code=404)

    return app
