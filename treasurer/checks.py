"""Rule checks. Plain Python, no AI: every flag is exact and reproducible."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .models import Receipt, money

TOLERANCE = Decimal("0.01")
MAX_TAX_RATE = Decimal("0.12")


class Severity(str, Enum):
    BLOCK = "block"  # approval disabled until fixed or overridden with a note
    WARN = "warn"    # shown on the row, does not block
    INFO = "info"


@dataclass(frozen=True)
class Flag:
    code: str
    severity: Severity
    message: str


def check_math(r: Receipt) -> list[Flag]:
    diff = r.computed_total - r.total
    if abs(diff) <= TOLERANCE:
        return []
    return [Flag("math_error", Severity.BLOCK,
                 f"Items + tax + tip = ${r.computed_total}, receipt says ${r.total} "
                 f"(off by ${money(abs(diff))})")]


def check_missing_payer(r: Receipt) -> list[Flag]:
    if r.payer and r.payer.strip():
        return []
    return [Flag("missing_payer", Severity.BLOCK, "No payer tagged")]


def check_missing_receipt(r: Receipt) -> list[Flag]:
    if r.image_file:
        return []
    return [Flag("missing_receipt", Severity.WARN, "No receipt photo attached")]


def check_tax_rate(r: Receipt) -> list[Flag]:
    if r.subtotal == 0 or r.tax / r.subtotal <= MAX_TAX_RATE:
        return []
    pct = money(r.tax / r.subtotal * 100)
    return [Flag("unusual_tax", Severity.WARN, f"Tax is {pct}% of the subtotal (over 12%)")]


# A cart or an estimate can change before anyone pays, so it blocks like a math error: the treasurer waits
# for the real receipt, or writes a note to count it as is. A bank charge is real money, so it only asks.
NOT_FINAL = {"cart": (Severity.BLOCK, "A cart before checkout. Ask for the order confirmation, or book it as is below."),
             "estimate": (Severity.BLOCK, "A price estimate. Ask for the receipt from after the ride or service, "
                                          "or book it as is below."),
             "pending_charge": (Severity.WARN, "A bank charge, not the seller's receipt. Ask for the receipt if there is one.")}


def check_proof(r: Receipt) -> list[Flag]:
    if r.proof not in NOT_FINAL:
        return []
    return [Flag("not_final", *NOT_FINAL[r.proof])]


def check_returned(r: Receipt) -> list[Flag]:
    names = [i.item for i in r.items if i.returned]
    if not names:
        return []
    return [Flag("returned_item", Severity.INFO,
                 f"Returned, listed but excluded: {', '.join(names)} (-${r.returned_amount})")]


def same_purchase(r: Receipt, s: Receipt) -> str | None:
    """Why two receipts look like one purchase (same image, or same place, date and total), else None."""
    if r.image_hash is not None and r.image_hash == s.image_hash:
        return "same image"
    if r.place.strip().lower() == s.place.strip().lower() and r.date == s.date and abs(r.total - s.total) <= TOLERANCE:
        return "same place, date and total"
    return None


def check_duplicates(receipts: list[Receipt]) -> dict[str, list[Flag]]:
    """Flag the LATER receipt of each pair, naming the earlier one.

    A pair is a duplicate if the image bytes match, or if place, date and
    total match within one event (catches a re-photographed receipt). The same payer with
    the same total within a day gets a softer "Check" flag.
    """
    out: dict[str, list[Flag]] = {}
    seen: list[Receipt] = []
    for r in receipts:
        for s in seen:
            if s.event_id != r.event_id:
                continue
            why = same_purchase(r, s)
            if why:
                out.setdefault(r.receipt_id, []).append(
                    Flag("possible_duplicate", Severity.BLOCK, f"Possible duplicate of {s.receipt_id} ({why})"))
                break
            # One purchase sent as two proofs (a paper receipt and a bank screenshot) reads with two place
            # names and dates a day apart. Different payers with the same total are different purchases.
            if r.payer and r.payer == s.payer and abs(r.total - s.total) <= TOLERANCE and abs((r.date - s.date).days) <= 1:
                out.setdefault(r.receipt_id, []).append(Flag(
                    "possible_duplicate", Severity.WARN,
                    f"{r.payer} has the same total on {s.receipt_id}, a day apart or less. Same purchase sent twice?"))
                break
        seen.append(r)
    return out


PER_RECEIPT = [check_math, check_missing_payer, check_missing_receipt, check_tax_rate, check_proof, check_returned]


def check_earlier_events(receipts: list[Receipt], earlier: list[tuple[str, Receipt]]) -> dict[str, list[Flag]]:
    """A receipt the club already counted in another event (event name, receipt): paying it back twice
    is the costly mistake, and nothing inside one event can catch it."""
    out: dict[str, list[Flag]] = {}
    for r in receipts:
        hit = next(((name, s, why) for name, s in earlier if (why := same_purchase(r, s))), None)
        if hit:
            name, s, why = hit
            out[r.receipt_id] = [Flag("possible_duplicate", Severity.BLOCK,
                                      f"Possible duplicate of {s.receipt_id} in {name}, already in the books ({why})")]
    return out


def run_checks(receipts: list[Receipt], earlier: list[tuple[str, Receipt]] = ()) -> dict[str, list[Flag]]:
    """Every flag per receipt id. `earlier`: what the club counted in its other events, as (event name, receipt)."""
    flags = {r.receipt_id: [f for check in PER_RECEIPT for f in check(r)] for r in receipts}
    for found in (check_duplicates(receipts), check_earlier_events(receipts, list(earlier))):
        for rid, dup in found.items():
            flags[rid].extend(dup)
    return flags


def can_approve(flags: list[Flag], override_note: str | None = None) -> bool:
    """Blocking flags need a written override note; others never block."""
    if not any(f.severity is Severity.BLOCK for f in flags):
        return True
    return bool(override_note and override_note.strip())
