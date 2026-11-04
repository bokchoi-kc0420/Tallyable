"""Edge cases for the rule checks: refunds, split payments, $0 tip, tax-exempt."""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from treasurer.checks import can_approve, run_checks
from treasurer.closeout import payer_summary
from treasurer.models import LineItem, Receipt, Status


def item(name="Thing", price="5.00", unit=1, returned=False, category="Other"):
    return LineItem(category=category, item=name, unit=unit, price=Decimal(price), returned=returned)


def receipt(rid="T1", items=None, tax="0", tip="0", total=None, **kw):
    items = items or [item()]
    r = Receipt(receipt_id=rid, event_id="E", place=kw.pop("place", "Shop"), date=kw.pop("date", date(2026, 11, 1)),
                payer=kw.pop("payer", "Member A"), items=items, tax=Decimal(tax), tip=Decimal(tip),
                total=Decimal("0"), image_file=kw.pop("image_file", "x.jpg"), **kw)
    return r.model_copy(update={"total": Decimal(total) if total is not None else r.computed_total})


def codes(r, others=()):
    return sorted(f.code for f in run_checks([*others, r])[r.receipt_id])


# ---- refunds and returned items ----

def test_everything_returned_posts_zero():
    r = receipt(items=[item("Cups", "4.00", returned=True), item("Plates", "6.00", returned=True)], tax="0.80")
    assert r.posted_amount == Decimal("0.00")
    assert codes(r) == ["returned_item"]


def test_returned_item_takes_its_share_of_tax():
    # $10 + $30 items, $4 tax. Returning the $10 item removes $10 + $1 tax.
    r = receipt(items=[item("A", "10.00", returned=True), item("B", "30.00")], tax="4.00")
    assert r.returned_amount == Decimal("11.00")
    assert r.posted_amount == Decimal("33.00")


def test_returned_share_rounds_to_cents():
    r = receipt(items=[item("A", "3.33", returned=True), item("B", "6.67")], tax="0.77")
    assert r.returned_amount == Decimal("3.59")  # 3.33 + 0.77 * 0.333 = 3.5864 -> 3.59
    assert r.posted_amount + r.returned_amount == r.total


def test_refund_on_a_separate_slip_cannot_be_negative():
    # A store refund slip shows a negative total. The model refuses it, so a refund
    # must be recorded as `returned` on the original receipt instead.
    with pytest.raises(ValidationError):
        receipt(items=[item("Refund", "-5.00")])


# ---- split payments ----

def test_two_card_slips_for_one_bill_are_not_duplicates():
    a = receipt("T1", place="Pizza Corner", total="40.00", items=[item(price="40.00")], payer="Member A")
    b = receipt("T2", place="Pizza Corner", total="25.00", items=[item(price="25.00")], payer="Member B")
    assert "possible_duplicate" not in codes(b, [a])


def test_equal_split_looks_like_a_duplicate_and_needs_a_note():
    # Two people each pay exactly half: same place, date and total. The check
    # can't tell this from a re-uploaded receipt, so it blocks until someone writes why.
    a = receipt("T1", place="Pizza Corner", items=[item(price="30.00")], payer="Member A")
    b = receipt("T2", place="Pizza Corner", items=[item(price="30.00")], payer="Member B")
    flags = run_checks([a, b])["T2"]
    assert [f.code for f in flags] == ["possible_duplicate"]
    assert not can_approve(flags) and can_approve(flags, "Split bill, two cards")


def test_split_payers_are_owed_separately():
    a = receipt("T1", items=[item(price="40.00")], payer="Member A").model_copy(update={"status": Status.APPROVED})
    b = receipt("T2", items=[item(price="25.00")], payer="Member B").model_copy(update={"status": Status.APPROVED})
    owed = {x.payer: x.owed for x in payer_summary([a, b])}
    assert owed == {"Member A": Decimal("40.00"), "Member B": Decimal("25.00")}


# ---- tips ----

def test_zero_tip_is_fine():
    assert codes(receipt(tip="0")) == []


def test_tip_left_off_the_reading_trips_math():
    r = receipt(items=[item(price="50.00")], tip="10.00")
    misread = r.model_copy(update={"tip": Decimal("0")})
    assert codes(misread) == ["math_error"]


def test_negative_tip_is_rejected():
    with pytest.raises(ValidationError):
        receipt(tip="-1.00")


# ---- tax ----

def test_tax_exempt_receipt_raises_nothing():
    assert codes(receipt(tax="0")) == []


def test_free_items_do_not_divide_by_zero():
    r = receipt(items=[item("Free sample", "0.00")], tax="0")
    assert codes(r) == []
    assert r.posted_amount == Decimal("0.00")


def test_tax_exactly_twelve_percent_is_not_flagged():
    assert codes(receipt(items=[item(price="100.00")], tax="12.00")) == []
    assert codes(receipt(items=[item(price="100.00")], tax="12.01")) == ["unusual_tax"]


def test_tax_on_mostly_returned_receipt_uses_full_subtotal():
    # The tax rate is judged on what was printed, before returns.
    r = receipt(items=[item("A", "90.00", returned=True), item("B", "10.00")], tax="8.00")
    assert "unusual_tax" not in codes(r)
