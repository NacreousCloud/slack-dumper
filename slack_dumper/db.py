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
