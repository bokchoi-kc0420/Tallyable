"""Event close-out: funder rules and "who is owed what". YOUR VERSION.

Fill in the four functions marked TODO. Run:
    pytest research/starter -q                       # tests your version
    CLOSEOUT_IMPL=solution pytest research/starter -q  # tests the reference
The dataclasses and rule packs are done for you; the logic is yours.
All rules are plain Python over APPROVED receipts. No AI.

Rules are taken from UC Davis CSI pages read on 2026-11-04:
- Club Finance Council (CFC): https://csi.ucdavis.edu/manage-your-org/grants/cfc
- Operation Reimbursement Grant (ORG): https://csi.ucdavis.edu/operation-reimbursement-grant
Re-check them each quarter; funders change rules. They live in data (RulePack)
so a KSEA national pack is the same code with different numbers.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from treasurer.checks import Flag, Severity
from treasurer.models import Receipt, money


@dataclass(frozen=True)
class Event:
    event_id: str
    name: str
    event_date: date
    attendees: int
    days: int = 1


@dataclass(frozen=True)
class RulePack:
    name: str
    max_award: Decimal | None = None             # biggest grant per application
    food_cap_per_person_day: Decimal | None = None
    min_club_share: Decimal | None = None        # 0.10 = club pays at least 10% of cost
    report_due_days_after_event: int | None = None
    purchase_window_days: int | None = None      # purchases must fall within N days before applying
    banned_categories: frozenset[str] = frozenset()
    suspect_keywords: tuple[str, ...] = ()       # item words that MAY be banned; a human decides
    food_categories: frozenset[str] = frozenset({"Food", "Drink"})
    notes: tuple[str, ...] = field(default_factory=tuple)


CFC = RulePack(
    name="UC Davis Club Finance Council",
    max_award=Decimal("2500"),
    food_cap_per_person_day=Decimal("12"),
    min_club_share=Decimal("0.10"),
    report_due_days_after_event=21,
    notes=("Expenditure report needs receipts, event photos and impact statements.",
           "Application due at least 42 days before the event."),
)

ORG = RulePack(
    name="UC Davis Operation Reimbursement Grant",
    max_award=Decimal("250"),
    purchase_window_days=42,
    banned_categories=frozenset({"Food", "Drink"}),
    suspect_keywords=("balloon", "table cover", "streamer", "banner", "decoration"),
    notes=("Decorations, website subscriptions and one-time marketing are also not allowed.",
           "Every purchase needs a receipt."),
)


def check_funder_rules(event: Event, receipts: list[Receipt], pack: RulePack,
                       requested: Decimal | None = None, applied_on: date | None = None) -> list[Flag]:
    """TODO. Return Flags for one event against one funder. `receipts` = approved only.

    Codes the tests expect (use Severity.BLOCK unless noted):
      food_over_cap        Food+Drink item amounts (pre-tax, minus returned) > cap x attendees x days
      over_max_award       requested > pack.max_award
      club_share_too_low   requested > event cost x (1 - min_club_share); cost = sum of posted_amount
      banned_category      an item whose category is in pack.banned_categories
      maybe_banned (WARN)  an item name containing one of pack.suspect_keywords
      outside_window       receipt date more than purchase_window_days before applied_on
      no_receipt_for_funder  receipt with no image_file
    Skip any rule whose RulePack field is None. Put the numbers in the message:
    a treasurer should be able to act on the flag without opening the code.
    """
    raise NotImplementedError


def report_due(event: Event, pack: RulePack) -> date | None:
    """TODO. Event date + report_due_days_after_event, or None if the pack has no deadline."""
    raise NotImplementedError


@dataclass(frozen=True)
class PayerLine:
    payer: str
    fronted: Decimal
    reimbursed: Decimal

    @property
    def owed(self) -> Decimal:
        return money(self.fronted - self.reimbursed)


def payer_summary(receipts: list[Receipt], reimbursed: dict[str, Decimal] | None = None) -> list[PayerLine]:
    """TODO. One PayerLine per payer: fronted = sum of posted_amount, reimbursed from the dict.
    Group receipts with no payer under "(no payer)". Sort by owed, biggest first.
    Hint: collections.defaultdict, and use money() so cents never drift.
    """
    raise NotImplementedError
