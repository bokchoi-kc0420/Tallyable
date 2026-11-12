import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from treasurer.checks import Severity, can_approve, check_duplicates, check_math, check_tax_rate, run_checks
from treasurer.loader import load_answer_key, planted_errors
from treasurer.models import LineItem, Receipt

KEY = Path(__file__).parent.parent / "fake_event" / "answer_key.csv"
SUMMARY = Path(__file__).parent.parent / "fake_event" / "expected_summary.json"

# planted error in the answer key -> flag code the checks must raise
EXPECTED_FLAG = {
    "math_total_mismatch": "math_error",
    "math_hidden_item": "math_error",
    "missing_payer": "missing_payer",
    "duplicate": "possible_duplicate",
    "missing_receipt": "missing_receipt",
    "returned_item": "returned_item",
}


@pytest.fixture(scope="module")
def receipts():
    return load_answer_key(KEY)


@pytest.fixture(scope="module")
def flags(receipts):
    return run_checks(receipts)


def make(total="10.83", tax="0.83", tip="0", **kw):
    base = dict(receipt_id="T1", event_id="E", place="Shop", date=date(2026, 11, 1), payer="Member A",
                items=[LineItem(category="Other", item="Thing", unit=2, price=Decimal("5.00"))],
                tax=Decimal(tax), tip=Decimal(tip), total=Decimal(total), image_file="x.jpg")
    base.update(kw)
    return Receipt(**base)


# ---------- graded against the fake event ----------

def test_loads_all_receipts(receipts):
    assert len(receipts) == 15
    assert sum(len(r.items) for r in receipts) == 33


@pytest.mark.parametrize("rid,planted", sorted(planted_errors(KEY).items()))
def test_every_planted_error_is_caught(flags, rid, planted):
    codes = {f.code for f in flags[rid]}
    assert EXPECTED_FLAG[planted] in codes, f"{rid}: expected {EXPECTED_FLAG[planted]}, got {codes}"


def test_no_false_flags_on_clean_receipts(flags):
    planted = planted_errors(KEY)
    noisy = {rid: [f.code for f in fl] for rid, fl in flags.items() if rid not in planted and fl}
    assert noisy == {}


def test_duplicate_names_the_original(flags):
    msg = next(f.message for f in flags["R11"] if f.code == "possible_duplicate")
    assert "R03" in msg
    assert not any(f.code == "possible_duplicate" for f in flags["R03"])


def test_math_message_shows_the_gap(flags):
    msg = next(f.message for f in flags["R06"] if f.code == "math_error")
    assert "$110.26" in msg and "$115.26" in msg and "$5.00" in msg


def test_returned_item_excluded_from_posted_amount(receipts):
    r09 = next(r for r in receipts if r.receipt_id == "R09")
    assert r09.returned_amount == Decimal("43.29")  # 39.99 + 3.30 tax
    assert r09.posted_amount == Decimal("26.50")


def test_reviewed_event_matches_expected_total(receipts):
    """Simulate a correct review: fix R06's total, reject the duplicate R11."""
    expected = json.loads(SUMMARY.read_text())
    approved = []
    for r in receipts:
        if r.receipt_id == "R11":
            continue
        if r.receipt_id == "R06":
            r = r.model_copy(update={"total": r.computed_total})
        approved.append(r)
    total = sum((r.posted_amount for r in approved), Decimal("0"))
    assert total == Decimal(expected["expected_total_expenses"])


# ---------- unit tests on the rules ----------

def test_math_tolerance_boundary():
    assert check_math(make(total="10.83")) == []           # exact
    assert check_math(make(total="10.84")) == []           # off by 1 cent: allowed
    assert check_math(make(total="10.85"))[0].code == "math_error"  # off by 2 cents


def test_decimal_not_float():
    # 0.1 + 0.2 style rounding must not create false math errors
    r = make(items=[LineItem(category="Food", item="a", unit=3, price=Decimal("0.10")),
                    LineItem(category="Food", item="b", unit=1, price=Decimal("0.20"))],
             tax="0", total="0.50")
    assert check_math(r) == []


def test_tax_warning_over_twelve_percent():
    assert check_tax_rate(make(tax="1.20", total="11.20")) == []
    flag = check_tax_rate(make(tax="1.30", total="11.30"))[0]
    assert flag.code == "unusual_tax" and flag.severity is Severity.WARN


def test_duplicate_by_identical_image_even_if_fields_differ():
    a = make(receipt_id="A", image_hash="abc")
    b = make(receipt_id="B", image_hash="abc", place="Other shop")
    assert "B" in check_duplicates([a, b])


def test_same_payer_same_total_a_day_apart_is_a_soft_flag_but_other_payers_are_not():
    """Kevin's real parking: three members each paid $25 at the same garage (three real purchases),
    but one member's paper receipt plus their bank screenshot is one purchase sent twice."""
    paper = make(receipt_id="A", place="LAZ Parking")
    bank = make(receipt_id="B", place="LAZ PKG L CENTER", date=date(2026, 11, 2))
    flag = check_duplicates([paper, bank])["B"][0]
    assert flag.severity is Severity.WARN and "A" in flag.message
    other_car = make(receipt_id="C", place="Center Street Garage", payer="Member B")
    assert check_duplicates([paper, other_car]) == {}


def test_duplicates_only_within_one_event():
    a = make(receipt_id="A", event_id="E1")
    b = make(receipt_id="B", event_id="E2")
    assert check_duplicates([a, b]) == {}


def test_blocking_flags_need_an_override_note(flags):
    assert not can_approve(flags["R07"])
    assert can_approve(flags["R07"], override_note="Paid by Member B, confirmed in chat")
    assert can_approve(flags["R14"])  # missing receipt only warns


def test_a_cart_or_estimate_needs_a_note_but_a_bank_charge_only_asks():
    for proof in ("cart", "estimate"):
        f = run_checks([make(proof=proof)])["T1"]
        assert [x.code for x in f] == ["not_final"] and not can_approve(f) and can_approve(f, "Final price matched")
    assert run_checks([make(proof="pending_charge")])["T1"][0].severity is Severity.WARN
    assert run_checks([make()])["T1"] == []


def test_overridden_math_books_the_whole_total_under_one_category():
    from collections import OrderedDict

    from treasurer.expense_view import render_expense_report
    from treasurer.post import transaction_rows
    over_read = make(total="5.83")  # lines say $10.00, the receipt says $5.83 with $0.83 tax
    view = render_expense_report({"event_id": "E", "name": "Mixer", "date": "2026-11-01"},
                                 OrderedDict(T1=transaction_rows(over_read)))
    assert ["Other", 5.0] in [r[:2] for r in view.grid]  # not the $10.00 the lines add up to
