"""Hosted only: Heroku wipes its disk on every restart, so each account's folder is copied into
Postgres (DATABASE_URL, set by the Heroku Postgres add-on). The app keeps reading and writing plain
files: `restore` puts the folder back on a fresh disk, `push` sends what changed since the last push.
Locally there is no DATABASE_URL and none of this runs."""
from __future__ import annotations

import functools
import os
from pathlib import Path

import psycopg

Seen = dict[str, tuple[int, int]]  # path -> (mtime, size) as last pushed


def on() -> bool:
    return bool(os.getenv("DATABASE_URL"))


@functools.cache
def _db() -> psycopg.Connection:
    db = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    db.execute("CREATE TABLE IF NOT EXISTS files (path text PRIMARY KEY, data bytea NOT NULL)")
    return db


def _scan(folder: Path, root: Path) -> Seen:
    return {p.relative_to(root).as_posix(): (s.st_mtime_ns, s.st_size)
            for p in folder.rglob("*") if p.is_file() and p.suffix != ".tmp" and (s := p.stat())}


def restore(folder: Path, root: Path) -> Seen:
    """Write the saved copy back to disk if this folder isn't here (a restart wiped it)."""
    if not folder.exists():
        prefix = folder.relative_to(root).as_posix() + "/"
        for path, data in _db().execute("SELECT path, data FROM files WHERE starts_with(path, %s)", (prefix,)):
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(data)
    return _scan(folder, root) if folder.exists() else {}


def push(folder: Path, root: Path, seen: Seen) -> Seen:
    """Save new or changed files, drop deleted ones. Returns what's saved now, for the next push."""
    now = _scan(folder, root) if folder.exists() else {}
    changed = [p for p, stamp in now.items() if seen.get(p) != stamp]
    gone = [p for p in seen if p not in now]
    if not changed and not gone:
        return seen
    try:
        with _db().transaction():
            for p in changed:
                _db().execute("INSERT INTO files VALUES (%s, %s) ON CONFLICT (path) DO UPDATE SET data = EXCLUDED.data",
                              (p, (root / p).read_bytes()))
            if gone:
                _db().execute("DELETE FROM files WHERE path = ANY(%s)", (gone,))
    except (psycopg.Error, OSError):  # dropped connection or a file mid-write: try again next run
        _db.cache_clear()
        return seen
    return now
