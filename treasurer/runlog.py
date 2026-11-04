"""Log how long each event takes in the tool, so "done" can be measured.

One row per push in output/run_log.csv: when, which reader, how many receipts,
how many edits the reviewer made, how many blocking flags were overridden with a
note, and minutes from first draft to push and from first review to push.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

FIELDS = ["pushed_at", "event_id", "reader", "model", "receipts", "posted", "edits", "overrides",
          "minutes_draft_to_push", "minutes_review_to_push"]


def minutes(start: float | None, end: float) -> str:
    return f"{(end - start) / 60:.1f}" if start else ""


def log_run(path: Path, row: dict) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"pushed_at": datetime.now().isoformat(timespec="seconds"), **row})


def read_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))
