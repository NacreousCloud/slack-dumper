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
