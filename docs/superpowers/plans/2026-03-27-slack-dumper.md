# Slack Dumper 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 개인 슬랙 사용자 권한으로 접근 가능한 모든 채널·메시지·파일을 로컬에 저장하고, 오프라인에서 열람할 수 있는 CLI + 로컬 뷰어 서비스 구축

**Architecture:** Slack Web API를 user token(OAuth 2.0)으로 호출해 채널 목록·메시지·스레드·파일을 페이지네이션 방식으로 수집한다. 수집 데이터는 SQLite에 저장하고 첨부 파일은 로컬 디렉토리에 다운로드한다. FastAPI 기반 로컬 웹 서버로 오프라인 뷰어를 제공하며 Jinja2 템플릿으로 Slack UI와 유사한 화면을 렌더링한다.

**Tech Stack:** Python 3.11+, slack-sdk, SQLite (sqlite3), FastAPI, Jinja2, httpx, click (CLI), pytest

---

## 배경 지식

### Slack API 권한 모델

- **Workspace Export(관리자 전용)**: 워크스페이스 전체 내보내기 — 관리자/소유자만 가능
- **User Token 방식(이 프로젝트)**: 개인이 로그인한 상태에서 자신이 가입된 채널의 데이터만 수집. 관리자 권한 불필요.

### 필요한 OAuth Scopes (user token)

| Scope | 용도 |
|---|---|
| `channels:read` | 공개 채널 목록 |
| `groups:read` | 비공개 채널(Private) 목록 |
| `im:read` | DM 목록 |
| `mpim:read` | 그룹 DM 목록 |
| `channels:history` | 공개 채널 메시지 |
| `groups:history` | 비공개 채널 메시지 |
| `im:history` | DM 메시지 |
| `mpim:history` | 그룹 DM 메시지 |
| `files:read` | 파일 메타데이터 및 다운로드 |
| `users:read` | 사용자 정보(display name 등) |
| `reactions:read` | 이모지 반응 |
| `search:read` | (선택) 검색 기능 |

---

## 파일 구조

```
slack-dumper/
├── slack_dumper/
│   ├── __init__.py
│   ├── auth.py          # OAuth token 관리 및 검증
│   ├── client.py        # Slack API 클라이언트 래퍼 (rate limit 처리 포함)
│   ├── models.py        # SQLite DB 스키마 정의 (dataclass + DDL)
│   ├── db.py            # DB 연결, CRUD 헬퍼
│   ├── fetcher/
│   │   ├── __init__.py
│   │   ├── channels.py  # 채널 목록 수집
│   │   ├── messages.py  # 메시지 + 스레드 수집
│   │   ├── files.py     # 파일 다운로드
│   │   └── users.py     # 사용자 프로필 수집
│   ├── sync.py          # 전체 동기화 오케스트레이터
│   └── viewer/
│       ├── app.py       # FastAPI 앱
│       ├── templates/   # Jinja2 HTML 템플릿
│       │   ├── base.html
│       │   ├── channel.html
│       │   └── message.html
│       └── static/      # CSS, JS
├── tests/
│   ├── test_client.py
│   ├── test_db.py
│   ├── test_fetcher_channels.py
│   ├── test_fetcher_messages.py
│   └── test_sync.py
├── cli.py               # click CLI 진입점
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Task 1: 프로젝트 초기 세팅 및 DB 스키마

**Files:**
- Create: `pyproject.toml`
- Create: `slack_dumper/__init__.py`
- Create: `slack_dumper/models.py`
- Create: `slack_dumper/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: pyproject.toml 작성**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "slack-dumper"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "slack-sdk>=3.27",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
    "httpx>=0.27",
    "click>=8.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21"]

[project.scripts]
slack-dumper = "cli:main"
```

- [ ] **Step 2: DB 스키마 모델 정의 (`slack_dumper/models.py`)**

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT,
    display_name TEXT,
    real_name TEXT,
    avatar_url TEXT,
    is_bot INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,   -- 'public', 'private', 'im', 'mpim'
    topic TEXT,
    purpose TEXT,
    member_count INTEGER,
    last_synced_cursor TEXT,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,   -- channel_id + ':' + ts
    channel_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    user_id TEXT,
    text TEXT,
    thread_ts TEXT,
    reply_count INTEGER DEFAULT 0,
    has_files INTEGER DEFAULT 0,
    raw_json TEXT,
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    name TEXT,
    mimetype TEXT,
    size INTEGER,
    url_private TEXT,
    local_path TEXT,
    downloaded INTEGER DEFAULT 0,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, ts);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_ts);
"""
```

- [ ] **Step 3: DB 헬퍼 작성 (`slack_dumper/db.py`)**

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .models import SCHEMA


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def get_conn(path: str | Path):
    conn = init_db(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: DB 테스트 작성 (`tests/test_db.py`)**

```python
import tempfile
from pathlib import Path
from slack_dumper.db import init_db

def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "channels" in tables
        assert "messages" in tables
        assert "files" in tables
        assert "users" in tables
        conn.close()

def test_init_db_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        init_db(f.name)
        init_db(f.name)  # 두 번 호출해도 에러 없어야 함
```

- [ ] **Step 5: 테스트 실행**

```bash
pip install -e ".[dev]"
pytest tests/test_db.py -v
```

Expected: PASS 2 tests

- [ ] **Step 6: 커밋**

```bash
git init && git add .
git commit -m "feat: init project with DB schema"
```

---

## Task 2: Slack API 클라이언트 래퍼

**Files:**
- Create: `slack_dumper/auth.py`
- Create: `slack_dumper/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: auth.py — 토큰 로드 및 검증**

```python
import os
from dotenv import load_dotenv

load_dotenv()


def load_token() -> str:
    token = os.environ.get("SLACK_USER_TOKEN", "")
    if not token.startswith("xoxp-"):
        raise ValueError(
            "SLACK_USER_TOKEN이 설정되지 않았거나 user token이 아닙니다. "
            "'xoxp-'로 시작해야 합니다."
        )
    return token
```

- [ ] **Step 2: client.py — rate limit 자동 재시도 래퍼**

```python
import time
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, token: str):
        self._client = WebClient(token=token)

    def call(self, method: str, **kwargs):
        """rate limit(429) 시 자동 대기 후 재시도"""
        while True:
            try:
                fn = getattr(self._client, method)
                return fn(**kwargs)
            except SlackApiError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning("Rate limited. Waiting %ds...", retry_after)
                    time.sleep(retry_after)
                else:
                    raise

    def paginate(self, method: str, result_key: str, **kwargs):
        """cursor 기반 페이지네이션 제너레이터"""
        cursor = None
        while True:
            resp = self.call(method, cursor=cursor, limit=200, **kwargs)
            yield from resp[result_key]
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
```

- [ ] **Step 3: 클라이언트 테스트 (`tests/test_client.py`)**

```python
import pytest
from unittest.mock import MagicMock, patch
from slack_sdk.errors import SlackApiError
from slack_dumper.client import SlackClient


def _make_client(token="xoxp-test"):
    return SlackClient(token)


def test_paginate_single_page():
    client = _make_client()
    mock_resp = {
        "channels": [{"id": "C1"}, {"id": "C2"}],
        "response_metadata": {"next_cursor": ""},
    }
    with patch.object(client._client, "conversations_list", return_value=mock_resp):
        results = list(client.paginate("conversations_list", "channels"))
    assert len(results) == 2


def test_call_retries_on_rate_limit():
    client = _make_client()
    error_resp = MagicMock(status_code=429, headers={"Retry-After": "0"})
    ok_resp = {"ok": True, "channels": []}
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise SlackApiError("rate limited", error_resp)
        return ok_resp

    with patch.object(client._client, "conversations_list", side_effect=side_effect):
        result = client.call("conversations_list")
    assert call_count == 2
    assert result["ok"] is True
```

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/test_client.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add slack_dumper/auth.py slack_dumper/client.py tests/test_client.py
git commit -m "feat: add Slack API client with rate limit retry"
```

---

## Task 3: 채널 수집기 (Fetcher)

**Files:**
- Create: `slack_dumper/fetcher/__init__.py`
- Create: `slack_dumper/fetcher/channels.py`
- Create: `slack_dumper/fetcher/users.py`
- Test: `tests/test_fetcher_channels.py`

- [ ] **Step 1: channels.py 작성**

```python
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
            INSERT OR REPLACE INTO channels
                (id, name, type, topic, purpose, member_count, synced_at)
            VALUES (:id, :name, :type, :topic, :purpose, :member_count, :synced_at)
            """,
            ch,
        )
        channels.append(ch)
    conn.commit()
    return channels
```

- [ ] **Step 2: users.py 작성**

```python
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
```

- [ ] **Step 3: 채널 수집 테스트**

```python
import tempfile
from unittest.mock import MagicMock
from slack_dumper.db import init_db
from slack_dumper.fetcher.channels import sync_channels


def _make_mock_client(channels):
    client = MagicMock()
    client.paginate.return_value = iter(channels)
    return client


def test_sync_channels_saves_member_channels():
    raw = [
        {"id": "C1", "name": "general", "is_member": True,
         "is_private": False, "is_im": False, "is_mpim": False,
         "topic": {"value": ""}, "purpose": {"value": ""}, "num_members": 5},
        {"id": "C2", "name": "secret", "is_member": False,  # 가입 안 된 채널 — 제외
         "is_private": True, "is_im": False, "is_mpim": False,
         "topic": {"value": ""}, "purpose": {"value": ""}, "num_members": 2},
    ]
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        result = sync_channels(_make_mock_client(raw), conn)
        rows = conn.execute("SELECT id FROM channels").fetchall()
    assert len(result) == 1
    assert result[0]["id"] == "C1"
    assert len(rows) == 1
```

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/test_fetcher_channels.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add slack_dumper/fetcher/ tests/test_fetcher_channels.py
git commit -m "feat: add channel and user fetchers"
```

---

## Task 4: 메시지 + 스레드 수집기

**Files:**
- Create: `slack_dumper/fetcher/messages.py`
- Test: `tests/test_fetcher_messages.py`

- [ ] **Step 1: messages.py 작성**

```python
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
                (f["id"], msg_id, f.get("name"), f.get("mimetype"),
                 f.get("size"), f.get("url_private_download") or f.get("url_private")),
            )
        if raw.get("reply_count", 0) > 0:
            thread_tss.append(raw["ts"])

    conn.commit()

    # 스레드 댓글 수집
    for thread_ts in thread_tss:
        _sync_thread(client, conn, channel_id, thread_ts)

    # 마지막 ts를 cursor로 저장
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
        "conversations_replies", "messages",
        channel=channel_id, ts=thread_ts
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
                msg_id, channel_id, raw["ts"], raw.get("user"),
                raw.get("text", ""), thread_ts, 0,
                int(bool(raw.get("files"))), json.dumps(raw),
            ),
        )
    conn.commit()
```

- [ ] **Step 2: 메시지 수집 테스트**

```python
import json
import tempfile
from unittest.mock import MagicMock
from slack_dumper.db import init_db
from slack_dumper.fetcher.messages import sync_messages


def _make_client(messages, thread_replies=None):
    client = MagicMock()
    def paginate(method, key, **kwargs):
        if method == "conversations_history":
            return iter(messages)
        if method == "conversations_replies":
            return iter(thread_replies or [])
        return iter([])
    client.paginate.side_effect = paginate
    return client


def test_sync_messages_saves_messages():
    msgs = [{"ts": "1000.0", "user": "U1", "text": "hello", "files": [], "reply_count": 0}]
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        conn.execute("INSERT INTO channels (id, name, type) VALUES ('C1', 'g', 'public')")
        conn.commit()
        sync_messages(_make_client(msgs), conn, "C1")
        rows = conn.execute("SELECT * FROM messages").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "hello"


def test_sync_messages_fetches_thread_replies():
    root = {"ts": "1000.0", "user": "U1", "text": "root", "files": [], "reply_count": 1, "thread_ts": "1000.0"}
    reply = {"ts": "1001.0", "user": "U2", "text": "reply", "files": [], "reply_count": 0, "thread_ts": "1000.0"}
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = init_db(f.name)
        conn.execute("INSERT INTO channels (id, name, type) VALUES ('C1', 'g', 'public')")
        conn.commit()
        sync_messages(_make_client([root], [root, reply]), conn, "C1")
        rows = conn.execute("SELECT ts FROM messages ORDER BY ts").fetchall()
    assert [r["ts"] for r in rows] == ["1000.0", "1001.0"]
```

- [ ] **Step 3: 테스트 실행**

```bash
pytest tests/test_fetcher_messages.py -v
```

- [ ] **Step 4: 커밋**

```bash
git add slack_dumper/fetcher/messages.py tests/test_fetcher_messages.py
git commit -m "feat: add message and thread fetcher with incremental sync"
```

---

## Task 5: 파일 다운로더

**Files:**
- Create: `slack_dumper/fetcher/files.py`
- Test: `tests/test_fetcher_files.py`

- [ ] **Step 1: files.py 작성**

```python
import sqlite3
import logging
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


def download_files(conn: sqlite3.Connection, token: str, base_dir: Path):
    """DB에 등록된 미다운로드 파일들을 로컬에 저장"""
    base_dir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        "SELECT id, url_private, name FROM files WHERE downloaded=0 AND url_private IS NOT NULL"
    ).fetchall()

    headers = {"Authorization": f"Bearer {token}"}
    for row in rows:
        dest = base_dir / row["id"] / (row["name"] or "file")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.stream("GET", row["url_private"], headers=headers, timeout=60) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=8192):
                        f.write(chunk)
            conn.execute(
                "UPDATE files SET downloaded=1, local_path=? WHERE id=?",
                (str(dest), row["id"]),
            )
            conn.commit()
            logger.info("Downloaded %s -> %s", row["name"], dest)
        except Exception as e:
            logger.warning("Failed to download %s: %s", row["id"], e)
```

- [ ] **Step 2: 파일 다운로드 테스트**

```python
import tempfile
import sqlite3
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
```

- [ ] **Step 3: 테스트 실행**

```bash
pytest tests/test_fetcher_files.py -v
```

- [ ] **Step 4: 커밋**

```bash
git add slack_dumper/fetcher/files.py tests/test_fetcher_files.py
git commit -m "feat: add file downloader with streaming"
```

---

## Task 6: 전체 동기화 오케스트레이터 + CLI

**Files:**
- Create: `slack_dumper/sync.py`
- Create: `cli.py`
- Test: `tests/test_sync.py`
- Create: `.env.example`

- [ ] **Step 1: sync.py 작성**

```python
import logging
from pathlib import Path
from .auth import load_token
from .client import SlackClient
from .db import init_db
from .fetcher.channels import sync_channels
from .fetcher.users import sync_users
from .fetcher.messages import sync_messages
from .fetcher.files import download_files

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
```

- [ ] **Step 2: cli.py 작성**

```python
import logging
from pathlib import Path
import click
from slack_dumper.sync import run_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@click.group()
def main():
    """Slack 개인 데이터 덤퍼"""


@main.command()
@click.option("--db", default="slack.db", show_default=True, help="SQLite DB 경로")
@click.option("--files-dir", default="slack_files", show_default=True, help="파일 저장 디렉토리")
@click.option("--skip-files", is_flag=True, help="파일 다운로드 건너뜀")
@click.option("--channel", "channels", multiple=True, help="수집할 채널 ID 또는 이름 (반복 가능)")
def sync(db, files_dir, skip_files, channels):
    """슬랙 데이터 동기화"""
    run_sync(
        db_path=Path(db),
        files_dir=Path(files_dir),
        skip_files=skip_files,
        channel_filter=list(channels) or None,
    )


@main.command()
@click.option("--db", default="slack.db", show_default=True)
@click.option("--port", default=8000, show_default=True)
def serve(db, port):
    """로컬 뷰어 서버 시작"""
    import uvicorn
    from slack_dumper.viewer.app import create_app
    app = create_app(db_path=db)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: .env.example 작성**

```
# Slack User Token (xoxp-로 시작해야 함)
# 발급 방법: https://api.slack.com/apps → Create New App → OAuth & Permissions
SLACK_USER_TOKEN=xoxp-your-token-here
```

- [ ] **Step 4: sync 통합 테스트**

```python
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from slack_dumper.sync import run_sync


def test_run_sync_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        files_dir = Path(tmpdir) / "files"

        mock_client = MagicMock()
        mock_client.paginate.return_value = iter([])  # 빈 데이터로 실행

        with patch("slack_dumper.sync.load_token", return_value="xoxp-test"), \
             patch("slack_dumper.sync.SlackClient", return_value=mock_client):
            run_sync(db_path=db_path, files_dir=files_dir, skip_files=True)

        assert db_path.exists()
```

- [ ] **Step 5: 테스트 실행**

```bash
pytest tests/test_sync.py -v
```

- [ ] **Step 6: 커밋**

```bash
git add slack_dumper/sync.py cli.py .env.example tests/test_sync.py
git commit -m "feat: add sync orchestrator and CLI"
```

---

## Task 7: Slack 아카이브 뷰어 (FastAPI + Jinja2)

Slack의 실제 UI와 최대한 유사한 아카이브 뷰어를 구축한다.

**구현할 UI 요소:**
- 왼쪽 사이드바: 워크스페이스명, 채널 섹션(Public/Private/DM) 그룹핑
- 메인 영역: 날짜 구분선, 연속 메시지 묶음(같은 유저 5분 이내)
- 스레드 패널: 오른쪽 슬라이드인으로 스레드 댓글 표시
- 이미지 인라인 미리보기, 파일 첨부 카드
- 상단 검색창 (채널 내 전문 검색)
- 날짜 점프 (특정 날짜로 이동)

**Files:**
- Create: `slack_dumper/viewer/app.py`
- Create: `slack_dumper/viewer/templates/base.html`
- Create: `slack_dumper/viewer/templates/channel.html`
- Create: `slack_dumper/viewer/static/style.css`
- Create: `slack_dumper/viewer/static/app.js`

- [ ] **Step 1: viewer/app.py 작성**

```python
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
            cond = "AND m.ts < ?" if before else ""
            params = (channel_id, before, 60) if before else (channel_id, 60)
            raw_msgs = conn.execute(
                f"""
                SELECT m.*, u.display_name, u.real_name, u.avatar_url
                FROM messages m
                LEFT JOIN users u ON m.user_id = u.id
                WHERE m.channel_id=?
                  AND (m.thread_ts IS NULL OR m.thread_ts = m.ts)
                  {cond}
                ORDER BY m.ts DESC LIMIT ?
                """,
                params,
            ).fetchall()

        # 오래된 순으로 표시
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
        cond = "AND m.channel_id=?" if channel_id else ""
        params = (f"%{q}%", channel_id) if channel_id else (f"%{q}%",)
        rows = conn.execute(
            f"""
            SELECT m.ts, m.text, m.channel_id, u.display_name, c.name as channel_name
            FROM messages m
            LEFT JOIN users u ON m.user_id = u.id
            LEFT JOIN channels c ON m.channel_id = c.id
            WHERE m.text LIKE ? {cond}
            ORDER BY m.ts DESC LIMIT 30
            """,
            params,
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
```

- [ ] **Step 2: base.html — Slack 스타일 레이아웃**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Slack Archive</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div class="layout">

  <!-- 사이드바 -->
  <nav class="sidebar">
    <div class="workspace-header">
      <span class="workspace-icon">S</span>
      <span class="workspace-name">Slack Archive</span>
    </div>

    <!-- 검색창 -->
    <div class="sidebar-search">
      <input id="global-search" type="text" placeholder="검색..." autocomplete="off">
      <div id="search-results" class="search-dropdown hidden"></div>
    </div>

    <!-- 채널 섹션 -->
    {% set public_channels = channels | selectattr("type", "eq", "public") | list %}
    {% set private_channels = channels | selectattr("type", "eq", "private") | list %}
    {% set dms = channels | selectattr("type", "in", ["im", "mpim"]) | list %}

    {% if public_channels %}
    <div class="sidebar-section">
      <div class="section-label">채널</div>
      {% for ch in public_channels %}
      <a class="channel-link {% if active_channel and active_channel.id == ch.id %}active{% endif %}"
         href="/channel/{{ ch.id }}">
        <span class="ch-icon">#</span>{{ ch.name }}
      </a>
      {% endfor %}
    </div>
    {% endif %}

    {% if private_channels %}
    <div class="sidebar-section">
      <div class="section-label">비공개 채널</div>
      {% for ch in private_channels %}
      <a class="channel-link {% if active_channel and active_channel.id == ch.id %}active{% endif %}"
         href="/channel/{{ ch.id }}">
        <span class="ch-icon">🔒</span>{{ ch.name }}
      </a>
      {% endfor %}
    </div>
    {% endif %}

    {% if dms %}
    <div class="sidebar-section">
      <div class="section-label">다이렉트 메시지</div>
      {% for ch in dms %}
      <a class="channel-link {% if active_channel and active_channel.id == ch.id %}active{% endif %}"
         href="/channel/{{ ch.id }}">
        <span class="ch-icon dm-icon">●</span>{{ ch.name }}
      </a>
      {% endfor %}
    </div>
    {% endif %}
  </nav>

  <!-- 메인 영역 -->
  <main class="main-area">
    {% block content %}
    <div class="empty-state">
      <div class="empty-icon">📁</div>
      <p>채널을 선택하면 메시지를 볼 수 있습니다</p>
    </div>
    {% endblock %}
  </main>

  <!-- 스레드 패널 (JS로 토글) -->
  <aside class="thread-panel hidden" id="thread-panel">
    <div class="thread-panel-header">
      <span>스레드</span>
      <button class="close-thread" onclick="closeThread()">✕</button>
    </div>
    <div class="thread-panel-body" id="thread-panel-body"></div>
  </aside>

</div>
<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: channel.html — 메시지 뷰**

```html
{% extends "base.html" %}
{% block content %}

<!-- 채널 헤더 -->
<div class="channel-header">
  <div class="channel-header-left">
    <span class="ch-title-icon">{% if active_channel.type == 'private' %}🔒{% else %}#{% endif %}</span>
    <h1 class="ch-title">{{ active_channel.name }}</h1>
    {% if active_channel.topic %}
    <span class="ch-divider">|</span>
    <span class="ch-topic">{{ active_channel.topic }}</span>
    {% endif %}
  </div>
  <div class="channel-header-right">
    <form class="inline-search-form" method="get">
      <input class="inline-search" name="q" value="{{ query }}" placeholder="이 채널에서 검색">
    </form>
  </div>
</div>

<!-- 메시지 목록 -->
<div class="messages-area" id="messages-area">

  {% if oldest_ts %}
  <div class="load-more-wrap">
    <a class="load-more" href="?before={{ oldest_ts }}{% if query %}&q={{ query }}{% endif %}">
      ↑ 이전 메시지 더 보기
    </a>
  </div>
  {% endif %}

  {% set current_date = "" %}
  {% for group in groups %}

    {# 날짜 구분선 #}
    {% if group.msg.fmt_date != current_date %}
      {% set current_date = group.msg.fmt_date %}
      <div class="date-divider">
        <span class="date-divider-label">{{ group.msg.fmt_date }}</span>
      </div>
    {% endif %}

    <!-- 메시지 그룹 (같은 유저 연속) -->
    <div class="msg-group" data-ts="{{ group.msg.ts }}">
      <div class="msg-row">
        <div class="avatar-col">
          {% if group.msg.avatar_url %}
          <img class="avatar" src="{{ group.msg.avatar_url }}" alt="">
          {% else %}
          <div class="avatar avatar-fallback">{{ (group.msg.display_name or group.msg.user_id or "?")[0] | upper }}</div>
          {% endif %}
        </div>
        <div class="msg-content">
          <div class="msg-meta">
            <span class="msg-username">{{ group.msg.display_name or group.msg.real_name or group.msg.user_id }}</span>
            <span class="msg-time">{{ group.msg.fmt_ts }}</span>
          </div>
          <div class="msg-text">{{ group.msg.text | replace("\n", "<br>") | safe }}</div>

          {# 파일 첨부 #}
          {% for f in group.files %}
          <div class="attachment">
            {% if f.mimetype and f.mimetype.startswith("image/") and f.downloaded %}
            <img class="img-preview" src="/files/{{ f.id }}" alt="{{ f.name }}" loading="lazy">
            {% else %}
            <div class="file-card">
              <span class="file-icon">📄</span>
              <div class="file-info">
                <a class="file-name" href="/files/{{ f.id }}" target="_blank">{{ f.name }}</a>
                <span class="file-size">{{ (f.size / 1024) | round(1) }} KB</span>
              </div>
            </div>
            {% endif %}
          </div>
          {% endfor %}

          {# 연속 메시지 (아바타·이름 없이) #}
          {% for cont in group.continuations %}
          <div class="msg-continuation" data-ts="{{ cont.ts }}">
            <span class="cont-time">{{ cont.fmt_ts }}</span>
            <div class="msg-text">{{ cont.text | replace("\n", "<br>") | safe }}</div>
          </div>
          {% endfor %}

          {# 스레드 버튼 #}
          {% if group.replies %}
          <button class="thread-btn"
            onclick='openThread({{ group | tojson }})'>
            💬 댓글 {{ group.replies | length }}개
          </button>
          {% endif %}
        </div>
      </div>
    </div>

  {% else %}
  <div class="empty-state">메시지가 없습니다.</div>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 4: style.css — Slack 다크 테마**

```css
/* Reset & Base */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --sidebar-bg: #19171d;
  --sidebar-width: 260px;
  --thread-width: 380px;
  --header-height: 49px;
  --text-primary: #d1d2d3;
  --text-secondary: #9b9b9b;
  --text-username: #ffffff;
  --accent: #4a9fff;
  --hover-bg: rgba(255,255,255,0.07);
  --active-bg: rgba(255,255,255,0.13);
  --border: rgba(255,255,255,0.1);
  --main-bg: #1a1d21;
  --msg-hover: rgba(255,255,255,0.04);
}
body { font-family: 'Slack-Lato', 'Lato', system-ui, sans-serif; background: var(--main-bg); color: var(--text-primary); height: 100vh; overflow: hidden; }

/* Layout */
.layout { display: flex; height: 100vh; }

/* Sidebar */
.sidebar {
  width: var(--sidebar-width); background: var(--sidebar-bg);
  display: flex; flex-direction: column; overflow-y: auto; flex-shrink: 0;
  border-right: 1px solid var(--border);
}
.workspace-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  cursor: default;
}
.workspace-icon {
  width: 28px; height: 28px; border-radius: 6px;
  background: #4a154b; color: #fff; display: flex;
  align-items: center; justify-content: center; font-weight: 800; font-size: 14px;
  flex-shrink: 0;
}
.workspace-name { font-weight: 700; font-size: 15px; color: #fff; }

/* Sidebar Search */
.sidebar-search { padding: 8px 12px; position: relative; }
.sidebar-search input {
  width: 100%; background: rgba(255,255,255,0.08);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-primary); padding: 6px 10px; font-size: 13px; outline: none;
}
.sidebar-search input:focus { border-color: var(--accent); background: rgba(255,255,255,0.12); }
.search-dropdown {
  position: absolute; left: 12px; right: 12px; top: 100%;
  background: #2c2d30; border: 1px solid var(--border);
  border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  z-index: 100; max-height: 320px; overflow-y: auto;
}
.search-dropdown.hidden { display: none; }
.search-result-item { padding: 10px 14px; cursor: pointer; border-bottom: 1px solid var(--border); }
.search-result-item:hover { background: var(--hover-bg); }
.search-result-channel { font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; }
.search-result-text { font-size: 13px; color: var(--text-primary); }

/* Sidebar Sections */
.sidebar-section { padding: 8px 0; }
.section-label {
  padding: 4px 16px 4px; font-size: 12px; font-weight: 700;
  color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em;
}
.channel-link {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 16px; color: var(--text-secondary);
  text-decoration: none; font-size: 14px; border-radius: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.channel-link:hover { background: var(--hover-bg); color: var(--text-primary); }
.channel-link.active { background: var(--active-bg); color: #fff; font-weight: 600; }
.ch-icon { font-size: 15px; opacity: 0.7; flex-shrink: 0; }
.dm-icon { color: #2bac76; font-size: 10px; }

/* Main Area */
.main-area {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; min-width: 0;
}

/* Channel Header */
.channel-header {
  height: var(--header-height); display: flex; align-items: center;
  justify-content: space-between; padding: 0 20px;
  border-bottom: 1px solid var(--border); flex-shrink: 0; gap: 16px;
}
.channel-header-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ch-title-icon { font-size: 18px; opacity: 0.6; }
.ch-title { font-size: 16px; font-weight: 700; color: #fff; white-space: nowrap; }
.ch-divider { color: var(--border); margin: 0 4px; }
.ch-topic { font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inline-search { background: rgba(255,255,255,0.08); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); padding: 5px 10px; font-size: 13px; outline: none; width: 200px; }
.inline-search:focus { border-color: var(--accent); }

/* Messages Area */
.messages-area {
  flex: 1; overflow-y: auto; padding: 0 0 24px;
  display: flex; flex-direction: column;
}

/* Date Divider */
.date-divider {
  display: flex; align-items: center; margin: 16px 20px 8px;
}
.date-divider::before, .date-divider::after {
  content: ""; flex: 1; height: 1px; background: var(--border);
}
.date-divider-label {
  padding: 2px 12px; font-size: 12px; font-weight: 700;
  color: var(--text-secondary); white-space: nowrap;
}

/* Load More */
.load-more-wrap { text-align: center; padding: 16px; }
.load-more { color: var(--accent); text-decoration: none; font-size: 13px; }
.load-more:hover { text-decoration: underline; }

/* Message Group */
.msg-group { padding: 2px 20px; }
.msg-group:hover { background: var(--msg-hover); }
.msg-row { display: flex; gap: 10px; padding: 4px 0; }
.avatar-col { width: 36px; flex-shrink: 0; padding-top: 2px; }
.avatar {
  width: 36px; height: 36px; border-radius: 6px; object-fit: cover;
}
.avatar-fallback {
  width: 36px; height: 36px; border-radius: 6px;
  background: #4a154b; color: #fff; display: flex;
  align-items: center; justify-content: center; font-weight: 700; font-size: 15px;
}
.msg-content { flex: 1; min-width: 0; }
.msg-meta { display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; }
.msg-username { font-weight: 700; font-size: 15px; color: var(--text-username); }
.msg-time { font-size: 11px; color: var(--text-secondary); }
.msg-text { font-size: 15px; line-height: 1.5; color: var(--text-primary); word-break: break-word; }

/* Continuation (same user) */
.msg-continuation { padding: 1px 0; display: flex; gap: 8px; align-items: flex-start; }
.cont-time { font-size: 10px; color: transparent; width: 36px; flex-shrink: 0; text-align: right; line-height: 1.6; }
.msg-continuation:hover .cont-time { color: var(--text-secondary); }

/* Attachments */
.attachment { margin-top: 6px; }
.img-preview { max-width: 400px; max-height: 300px; border-radius: 8px; cursor: pointer; display: block; }
.file-card {
  display: flex; align-items: center; gap: 10px;
  background: rgba(255,255,255,0.05); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px; max-width: 360px; margin-top: 4px;
}
.file-icon { font-size: 24px; }
.file-info { display: flex; flex-direction: column; }
.file-name { color: var(--accent); text-decoration: none; font-size: 14px; font-weight: 600; }
.file-name:hover { text-decoration: underline; }
.file-size { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }

/* Thread Button */
.thread-btn {
  margin-top: 6px; background: none; border: 1px solid var(--border);
  border-radius: 6px; color: var(--accent); cursor: pointer;
  font-size: 13px; padding: 3px 10px; display: inline-flex; align-items: center; gap: 4px;
}
.thread-btn:hover { background: var(--hover-bg); border-color: var(--accent); }

/* Thread Panel */
.thread-panel {
  width: var(--thread-width); background: var(--main-bg);
  border-left: 1px solid var(--border); display: flex; flex-direction: column;
  flex-shrink: 0;
}
.thread-panel.hidden { display: none; }
.thread-panel-header {
  height: var(--header-height); display: flex; align-items: center;
  justify-content: space-between; padding: 0 16px;
  border-bottom: 1px solid var(--border); font-weight: 700; font-size: 15px;
}
.close-thread { background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 18px; padding: 4px; }
.close-thread:hover { color: #fff; }
.thread-panel-body { flex: 1; overflow-y: auto; padding: 16px; }

/* Thread Messages */
.thread-msg { display: flex; gap: 10px; margin-bottom: 12px; }
.thread-msg-content .msg-meta { margin-bottom: 2px; }

/* Empty State */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary); gap: 12px; }
.empty-icon { font-size: 48px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 3px; }
```

- [ ] **Step 5: app.js — 스레드 패널 + 검색**

```javascript
// 스레드 패널 열기
function openThread(group) {
  const panel = document.getElementById('thread-panel');
  const body = document.getElementById('thread-panel-body');
  panel.classList.remove('hidden');

  const replies = group.replies || [];
  const rootMsg = group.msg;

  const renderMsg = (msg) => `
    <div class="thread-msg">
      <div class="avatar-col">
        ${msg.avatar_url
          ? `<img class="avatar" src="${msg.avatar_url}" alt="">`
          : `<div class="avatar avatar-fallback">${(msg.display_name || msg.user_id || '?')[0].toUpperCase()}</div>`
        }
      </div>
      <div class="thread-msg-content msg-content">
        <div class="msg-meta">
          <span class="msg-username">${msg.display_name || msg.user_id || '알 수 없음'}</span>
          <span class="msg-time">${msg.fmt_ts || ''}</span>
        </div>
        <div class="msg-text">${(msg.text || '').replace(/\n/g, '<br>')}</div>
      </div>
    </div>
  `;

  body.innerHTML = `
    <div style="border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:16px; margin-bottom:16px;">
      ${renderMsg(rootMsg)}
    </div>
    ${replies.map(renderMsg).join('')}
    <div style="color:#9b9b9b; font-size:12px; margin-top:8px;">${replies.length}개의 댓글</div>
  `;
}

function closeThread() {
  document.getElementById('thread-panel').classList.add('hidden');
}

// 전역 검색
const searchInput = document.getElementById('global-search');
const searchResults = document.getElementById('search-results');

if (searchInput) {
  let timer;
  searchInput.addEventListener('input', () => {
    clearTimeout(timer);
    const q = searchInput.value.trim();
    if (q.length < 2) { searchResults.classList.add('hidden'); return; }
    timer = setTimeout(async () => {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      const items = await res.json();
      if (!items.length) { searchResults.classList.add('hidden'); return; }
      searchResults.innerHTML = items.map(item => `
        <div class="search-result-item" onclick="location.href='/channel/${item.channel_id}'">
          <div class="search-result-channel">#${item.channel_name || item.channel_id}</div>
          <div class="search-result-text">${item.text?.slice(0, 80) || ''}</div>
        </div>
      `).join('');
      searchResults.classList.remove('hidden');
    }, 300);
  });

  document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
      searchResults.classList.add('hidden');
    }
  });
}

// 페이지 로드 시 최신 메시지로 스크롤
window.addEventListener('load', () => {
  const area = document.getElementById('messages-area');
  if (area) area.scrollTop = area.scrollHeight;
});
```

- [ ] **Step 6: 커밋**

```bash
git add slack_dumper/viewer/
git commit -m "feat: add Slack-style archive viewer with threads and search"
```

---

## Task 8: Slack 앱 생성 및 토큰 발급 가이드 (README)

**Files:**
- Create: `README.md`

- [ ] **Step 1: README.md 작성**

```markdown
# Slack Dumper

개인 Slack 데이터(채널, 비공개채널, 메시지, 스레드, 파일)를 로컬에 저장하고 오프라인에서 열람하는 도구.

## 1. Slack App 생성 및 User Token 발급

1. https://api.slack.com/apps → **Create New App** → **From scratch**
2. App Name 입력 후 워크스페이스 선택
3. **OAuth & Permissions** → **Scopes** → **User Token Scopes** 추가:
   - `channels:read`, `channels:history`
   - `groups:read`, `groups:history`
   - `im:read`, `im:history`
   - `mpim:read`, `mpim:history`
   - `users:read`
   - `files:read`
4. **Install to Workspace** 클릭 → 권한 승인
5. **OAuth Tokens** 섹션의 **User OAuth Token** (`xoxp-...`) 복사

## 2. 설정

```bash
cp .env.example .env
# .env에 SLACK_USER_TOKEN=xoxp-... 입력
```

## 3. 설치

```bash
pip install -e .
```

## 4. 동기화

```bash
# 전체 동기화 (메시지 + 파일)
slack-dumper sync

# 특정 채널만
slack-dumper sync --channel general --channel C1234ABCD

# 파일 제외
slack-dumper sync --skip-files
```

## 5. 오프라인 뷰어

```bash
slack-dumper serve
# 브라우저에서 http://localhost:8000 열기
```
```

- [ ] **Step 2: 커밋**

```bash
git add README.md
git commit -m "docs: add setup and usage README"
```

---

## Task 9: 전체 테스트 실행 및 최종 검증

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest tests/ -v --tb=short
```

Expected: 모든 테스트 PASS

- [ ] **Step 2: 실제 환경 스모크 테스트 (토큰 있을 경우)**

```bash
cp .env.example .env
# .env 편집 후

slack-dumper sync --skip-files --channel general
slack-dumper serve
# http://localhost:8000 에서 채널 목록 및 메시지 확인
```

- [ ] **Step 3: 최종 커밋**

```bash
git add .
git commit -m "chore: finalize slack-dumper v0.1.0"
```

---

## 구현 후 확장 고려사항 (v0.2+)

| 기능 | 설명 |
|---|---|
| 증분 동기화 | `last_synced_cursor` 활용 (이미 구조 준비됨) |
| 검색 | SQLite FTS5 또는 `search:read` 스코프 활용 |
| 이모지 반응 | `reactions:read`로 수집, 메시지에 표시 |
| DM 뷰 | `im` 타입 채널 대화 상대 이름 표시 |
| 정적 HTML 내보내기 | 서버 없이 폴더째 열람 가능한 HTML 생성 |
| 스케줄 동기화 | cron / launchd 설정으로 주기적 업데이트 |
