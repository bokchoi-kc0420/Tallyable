"""Turn approved receipts into rows for the sheets.

`LocalCsvSink` is the fallback when Google Sheets is not set up (see sheets.py).
The sink is idempotent: a receipt id that was already posted is skipped,
so clicking Push twice never double-counts.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from .models import Receipt, Status
from .reimburse import REIMB_FIELDS

TX_FIELDS = ["event_id", "receipt_id", "date", "place", "payer", "category", "item", "unit", "price",
             "amount", "returned", "receipt_tax", "receipt_tip", "receipt_total", "receipt_posted", "image_file"]


def transaction_rows(r: Receipt) -> list[dict]:
    """Long format: one row per line item. Every sheet layout is built from these."""
    return [dict(event_id=r.event_id, receipt_id=r.receipt_id, date=r.date.isoformat(), place=r.place,
                 payer=r.payer or "", category=i.category, item=i.item, unit=i.unit, price=str(i.price),
                 amount=str(i.amount), returned="TRUE" if i.returned else "FALSE", receipt_tax=str(r.tax),
                 receipt_tip=str(r.tip), receipt_total=str(r.total), receipt_posted=str(r.posted_amount),
                 image_file=r.image_file or "") for i in r.items]


def event_totals(receipts: list[Receipt], income: dict[str, Decimal]) -> dict[str, Decimal]:
    approved = [r for r in receipts if r.counts]
    expenses = sum((r.posted_amount for r in approved), Decimal("0"))
    inc = sum(income.values(), Decimal("0"))
    margin = (inc - expenses) / inc * 100 if inc else Decimal("0")
    return {"income": inc, "expenses": expenses, "net": inc - expenses, "margin_pct": margin.quantize(Decimal("0.01"))}


class LocalCsvSink:
    def __init__(self, path: Path):
        self.path = path

    def posted_ids(self) -> set[tuple[str, str]]:
        """(event_id, receipt_id) pairs already written. Keyed by event too, because every
        event starts its receipt ids over at R01."""
        if not self.path.exists():
            return set()
        with open(self.path, newline="") as fh:
            return {(row["event_id"], row["receipt_id"]) for row in csv.DictReader(fh)}

    label = "local CSV"

    def post(self, receipts: list[Receipt], event=None, income=None) -> list[str]:
        """Write approved, not-yet-posted receipts. Returns the ids written."""
        done = self.posted_ids()
        todo = [r for r in receipts if r.status is Status.APPROVED and (r.event_id, r.receipt_id) not in done]
        new_file = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=TX_FIELDS)
            if new_file:
                w.writeheader()
            for r in todo:
                w.writerows(transaction_rows(r))
        return [r.receipt_id for r in todo]

    # Reimbursements sit next to the transactions file.
    @property
    def _reimb_path(self) -> Path:
        return self.path.with_name("reimbursements.csv")

    def reimbursements(self) -> list[dict]:
        if not self._reimb_path.exists():
            return []
        with open(self._reimb_path, newline="") as fh:
            return list(csv.DictReader(fh))

    def record_reimbursement(self, r) -> None:
        new_file = not self._reimb_path.exists()
        self._reimb_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._reimb_path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=REIMB_FIELDS)
            if new_file:
                w.writeheader()
            w.writerow(r.row())
