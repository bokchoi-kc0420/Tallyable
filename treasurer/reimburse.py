"""Reimbursements: when the club pays a member back for a receipt they fronted.

A reimbursement does NOT change the event's expenses. The expense was already
counted when the receipt was posted; paying the member back only settles what
the club owes them. So it is recorded in its own tidy table, lowers "owed" in
the close-out, and shows in the ledger as a row with no asset or liability
amount (so the running balance is unchanged).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .models import cell_decimal, money

REIMB_FIELDS = ["event_id", "payer", "date", "amount", "method", "note"]
METHODS = ["Zelle", "Venmo", "Cash", "Check", "PayPal", "Cash App", "Apple Pay", "Bank transfer", "Other"]


@dataclass(frozen=True)
class Reimbursement:
    event_id: str
    payer: str
    date: date
    amount: Decimal
    method: str
    note: str = ""

    def row(self) -> dict:
        return {"event_id": self.event_id, "payer": self.payer, "date": self.date.isoformat(),
                "amount": str(self.amount), "method": self.method, "note": self.note}


def totals_by_payer(rows: list[dict], event_id: str) -> dict[str, Decimal]:
    """Sum of reimbursements per payer for one event, from tidy rows."""
    out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in rows:
        if str(r["event_id"]) == event_id:
            out[str(r["payer"])] += cell_decimal(r["amount"])
    return {k: money(v) for k, v in out.items()}


def validate(payer: str, amount_text: str, owed: Decimal) -> tuple[Decimal | None, str | None]:
    """(amount, None) if OK, else (None, reason). Blocks paying back more than is owed,
    because an overpayment is almost always a typo or a double click."""
    if payer == "(no payer)":
        return None, "Tag a payer on these receipts first; the club can't pay back nobody."
    try:
        amount = money(Decimal(amount_text.replace("$", "").strip()))
    except InvalidOperation:
        return None, f"{amount_text!r} is not an amount."
    if amount <= 0:
        return None, "Amount must be more than $0."
    if amount > owed:
        return None, f"{payer} is owed ${owed}; ${amount} would overpay."
    return amount, None
