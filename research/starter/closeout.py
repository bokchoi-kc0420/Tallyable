"""Event close-out: funder rules and "who is owed what".

All rules are plain Python over APPROVED receipts. No AI: a funder flag has to be
exact and reproducible, because a treasurer may have to defend it to the funder.
Run the tests with:  pytest research/starter -q

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


def _food_spend(receipts: list[Receipt], pack: RulePack) -> Decimal:
    """Food and drink cost before tax, minus returned items. Tax is left out on
    purpose: the cap is per person, and counting tax would make it stricter
    than the funder wrote. Change this if the funder says otherwise."""
    total = Decimal("0")
    for r in receipts:
        total += sum((i.amount for i in r.items if i.category in pack.food_categories and not i.returned),
                     Decimal("0"))
    return money(total)


def check_funder_rules(event: Event, receipts: list[Receipt], pack: RulePack,
                       requested: Decimal | None = None, applied_on: date | None = None) -> list[Flag]:
    """Flags for one event against one funder. `receipts` = approved receipts only.

    Each rule is skipped when its RulePack field is None, so a funder without
    that rule needs no special code. Every message carries the numbers, so a
    treasurer can act on it without opening this file.
    """
    flags: list[Flag] = []
    # Event cost = what actually reaches the balance sheet (returned items excluded).
    cost = money(sum((r.posted_amount for r in receipts), Decimal("0")))

    # Rule 1, food cap (CFC): food and drink may cost at most $12 per person per day.
    # Cap = rate x attendees x days. Blocks, because the funder will not pay the excess.
    if pack.food_cap_per_person_day is not None:
        cap = money(pack.food_cap_per_person_day * event.attendees * event.days)
        food = _food_spend(receipts, pack)
        if food > cap:
            flags.append(Flag("food_over_cap", Severity.BLOCK,
                              f"Food and drink ${food} is over the cap of ${cap} "
                              f"(${pack.food_cap_per_person_day} x {event.attendees} people x {event.days} day)"))

    # Rules 2 and 3 only apply once we know how much the club is asking for.
    if requested is not None:
        # Rule 2, max award: one application can't ask for more than the funder's ceiling.
        if pack.max_award is not None and requested > pack.max_award:
            flags.append(Flag("over_max_award", Severity.BLOCK,
                              f"Request ${requested} is over the ${pack.max_award} maximum"))
        # Rule 3, club share (CFC): the club must pay at least 10% of the cost itself,
        # so the most it can request is cost x 90%, rounded half up to the cent.
        if pack.min_club_share is not None and cost > 0:
            max_grant = money(cost * (1 - pack.min_club_share))
            if requested > max_grant:
                flags.append(Flag("club_share_too_low", Severity.BLOCK,
                                  f"Request ${requested} leaves the club paying under "
                                  f"{int(pack.min_club_share * 100)}% of ${cost}; ask for at most ${max_grant}"))

    # Rules 4 to 7 look at each receipt on its own.
    for r in receipts:
        # Rule 4, banned category (ORG): no food or drink. Returned items don't count,
        # since the club didn't end up paying for them.
        banned = [i.item for i in r.items if i.category in pack.banned_categories and not i.returned]
        if banned:
            flags.append(Flag("banned_category", Severity.BLOCK,
                              f"{r.receipt_id}: {', '.join(banned)} not allowed by {pack.name}"))
        # Rule 5, maybe banned (ORG): decorations are banned, but "decoration" isn't a
        # category we track. Keyword matches only WARN, so a human makes the call.
        maybe = [i.item for i in r.items
                 if not i.returned and any(k in i.item.lower() for k in pack.suspect_keywords)]
        if maybe:
            flags.append(Flag("maybe_banned", Severity.WARN,
                              f"{r.receipt_id}: check whether {', '.join(maybe)} counts as a decoration"))
        # Rule 6, purchase window (ORG): only purchases from the 42 days before the
        # application date can be reimbursed.
        if pack.purchase_window_days is not None and applied_on is not None:
            if (applied_on - r.date).days > pack.purchase_window_days:
                flags.append(Flag("outside_window", Severity.BLOCK,
                                  f"{r.receipt_id}: bought {r.date}, more than "
                                  f"{pack.purchase_window_days} days before applying on {applied_on}"))
        # Rule 7, receipt required: funders need a receipt for every purchase. In the app,
        # a missing photo only WARNS, but for a funder it BLOCKS.
        if not r.image_file:
            flags.append(Flag("no_receipt_for_funder", Severity.BLOCK,
                              f"{r.receipt_id}: funder needs a receipt for every purchase"))
    return flags


def report_due(event: Event, pack: RulePack) -> date | None:
    """CFC wants the expenditure report 21 days after the event. Other funders may have no deadline."""
    if pack.report_due_days_after_event is None:
        return None
    return event.event_date + timedelta(days=pack.report_due_days_after_event)


@dataclass(frozen=True)
class PayerLine:
    payer: str
    fronted: Decimal
    reimbursed: Decimal

    @property
    def owed(self) -> Decimal:
        return money(self.fronted - self.reimbursed)


def payer_summary(receipts: list[Receipt], reimbursed: dict[str, Decimal] | None = None) -> list[PayerLine]:
    """Who fronted how much, and who is still owed. `reimbursed` maps payer -> amount
    already paid back (from the ledger). Receipts with no payer are grouped under
    "(no payer)" so the money never disappears from the summary."""
    reimbursed = reimbursed or {}
    fronted: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for r in receipts:
        fronted[(r.payer or "").strip() or "(no payer)"] += r.posted_amount
    return sorted((PayerLine(p, money(v), money(reimbursed.get(p, Decimal("0"))))
                   for p, v in fronted.items()), key=lambda line: -line.owed)
