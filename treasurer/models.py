"""Data model: a Receipt holds many LineItems.

Tax, tip and total live on the receipt, not the item, because that is how
paper receipts (and the club's expense report, with its merged cells) work.
The same models will validate the AI's JSON output in week 2.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

CENT = Decimal("0.01")


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
    price: Decimal = Field(ge=0, description="Price per unit, before tax")
    returned: bool = False

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

    @property
    def subtotal(self) -> Decimal:
        return money(sum((i.amount for i in self.items), Decimal("0")))

    @property
    def computed_total(self) -> Decimal:
        return money(self.subtotal + self.tax + self.tip)

    @property
    def returned_amount(self) -> Decimal:
        """Cost of returned items plus their share of the tax.

        The receipt does not say which items were taxed, so tax is split in
        proportion to each item's amount. Exact when every item is taxable.
        """
        returned = sum((i.amount for i in self.items if i.returned), Decimal("0"))
        if returned == 0 or self.subtotal == 0:
            return Decimal("0.00")
        return money(returned + self.tax * returned / self.subtotal)

    @property
    def posted_amount(self) -> Decimal:
        """What reaches the balance sheet: the total minus returned items."""
        return money(self.total - self.returned_amount)
