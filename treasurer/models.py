"""Data model: a Receipt holds many LineItems.

Tax, tip and total live on the receipt, not the item, because that is how
paper receipts (and the club's expense report, with its merged cells) work.
The same models will validate the AI's JSON output in week 2.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

CENT = Decimal("0.01")
# Bottle deposits and fees: printed right under an item, so a saving under them is really that item's.
FEE = re.compile(r"\b(CRV|DEPOSIT|DEP|BAG|FEE)\b", re.IGNORECASE)


def money(x: Decimal) -> Decimal:
    """Round to cents the way a cashier does (half up), never with floats."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


Category = Literal["Food", "Drink", "Other"]


class Status(str, Enum):
    DRAFTED = "drafted"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"


class LineItem(BaseModel):
    category: Category
    item: str = Field(min_length=1)
    unit: int = Field(gt=0, description="Quantity bought")
    # Negative for a discount, coupon or promo line (common on online-order screenshots),
    # so the lines still add up to the printed total and the math check stays honest.
    price: Decimal = Field(description="Price per unit, before tax. Negative for a discount line.")
    returned: bool = False
    # As the receipt marks it (T vs S/N/F). None when the receipt doesn't say: tax is then split by amount.
    taxed: bool | None = None
    # A discount printed under one item (Member Savings): it is part of that item, so it leaves with it.
    for_item_above: bool = False

    @property
    def amount(self) -> Decimal:
        return money(self.price * self.unit)


class Receipt(BaseModel):
    receipt_id: str
    event_id: str
    place: str
    date: date
    payer: str | None = None
    items: list[LineItem] = Field(min_length=1)
    tax: Decimal = Field(default=Decimal("0"), ge=0)
    tip: Decimal = Field(default=Decimal("0"), ge=0)
    total: Decimal = Field(ge=0, description="Total as printed on the receipt")
    image_file: str | None = None
    image_hash: str | None = None
    status: Status = Status.DRAFTED
    review_note: str | None = None
    # What the photo shows. Anything but a receipt is not proof that money was spent (see checks.check_proof).
    proof: Literal["receipt", "cart", "estimate", "pending_charge"] = "receipt"
    # Why the left-out lines (LineItem.returned) are out: the payer's own stuff, or taken back to the store.
    left_out_why: Literal["personal", "returned"] = "personal"

    @model_validator(mode="after")
    def _not_a_refund(self):
        # Discount lines may be negative, but a whole receipt can't be: a refund is
        # recorded as `returned` on the original receipt instead.
        if sum((i.amount for i in self.items), Decimal("0")) < 0:
            raise ValueError("Items add up to less than $0. Record a refund as a returned item.")
        return self

    @property
    def counts(self) -> bool:
        """Approved or already posted: the receipt counts toward the event's totals."""
        return self.status in (Status.APPROVED, Status.POSTED)

    @property
    def subtotal(self) -> Decimal:
        return money(sum((i.amount for i in self.items), Decimal("0")))

    @property
    def computed_total(self) -> Decimal:
        return money(self.subtotal + self.tax + self.tip)

    @property
    def owners(self) -> list[LineItem]:
        """The line each line belongs to: itself, or for a discount printed under an item, that item.
        A deposit or fee line in between (Safeway prints CRV under the soda) is skipped."""
        owners, last, item = [], None, None  # item: the last line that isn't a deposit or fee
        for i in self.items:
            if i.for_item_above and i.price < 0 and last:
                owners.append(item or last)
                continue
            owners.append(i)
            last = i
            item = item if FEE.search(i.item) else i
        return owners

    @property
    def returned_amount(self) -> Decimal:
        """Cost of left-out items plus their share of the tax.

        A discount printed under an item belongs to that item. Tax follows the lines the receipt
        marks as taxed; when it marks none, tax is split in proportion to each line's amount.
        """
        owners = self.owners
        out = sum((i.amount for i, o in zip(self.items, owners, strict=True) if o.returned), Decimal("0"))
        if out == 0:
            return Decimal("0.00")
        marked = any(i.taxed is not None for i in self.items)
        base = [(i, o) for i, o in zip(self.items, owners, strict=True) if o.taxed or not marked]
        base_amt = sum((i.amount for i, _ in base), Decimal("0"))
        out_base = sum((i.amount for i, o in base if o.returned), Decimal("0"))
        return money(out + (self.tax * out_base / base_amt if base_amt else Decimal("0")))

    @property
    def posted_amount(self) -> Decimal:
        """What reaches the balance sheet: the total minus returned items."""
        return money(self.total - self.returned_amount)


def cell_decimal(x) -> Decimal:
    """Sheet cell -> Decimal. Cells come back as int, float or str, and once the sheet is
    formatted as currency, as text like "$1,200.00", "-$5.00" or "($5.00)"."""
    t = str(x).strip().replace("$", "").replace(",", "").replace(" ", "")
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    if t in ("", "-"):
        return Decimal("0")
    try:
        return Decimal(t)
    except InvalidOperation:
        raise ValueError(f"'{x}' in the sheet isn't a number. Fix that cell, then push again.") from None
