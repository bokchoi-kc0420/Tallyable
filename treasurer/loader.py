"""Load the fake answer key CSV into Receipt objects."""
from __future__ import annotations

import csv
import hashlib
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

from .models import LineItem, Receipt


def image_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_answer_key(csv_path: Path, event_id: str = "EVT-FAKE-01") -> list[Receipt]:
    base = csv_path.parent
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            groups.setdefault(row["receipt_id"], []).append(row)

    receipts = []
    for rid, rows in groups.items():
        first = rows[0]
        img = first["image_file"] or None
        receipts.append(Receipt(
            receipt_id=rid,
            event_id=event_id,
            place=first["place"],
            date=first["date"],
            payer=first["payer"] or None,
            items=[LineItem(category=r["category"], item=r["item"], unit=int(r["unit"]),
                            price=Decimal(r["price"]), returned=r["returned"] == "TRUE") for r in rows],
            tax=Decimal(first["tax"]),
            tip=Decimal(first["tip"]),
            total=Decimal(first["total"]),
            image_file=img,
            image_hash=image_hash(base / img) if img else None,
        ))
    return receipts


def planted_errors(csv_path: Path) -> dict[str, str]:
    """receipt_id -> planted error code, for receipts that have one."""
    with open(csv_path, newline="") as fh:
        return {r["receipt_id"]: r["planted_error"] for r in csv.DictReader(fh) if r["planted_error"]}
