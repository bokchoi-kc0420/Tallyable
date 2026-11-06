"""Tests for the event close-out rules, graded against the fake event."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import treasurer.closeout as co
from treasurer.loader import load_answer_key

ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / "fake_event" / "answer_key.csv"
EVENT = co.Event("EVT-FAKE-01", "Fall Mentor Mixer (FAKE)", date(2026, 11, 14), attendees=45)


@pytest.fixture(scope="module")
def approved():
    """What a correct review approves: everything except the R11 duplicate,
    with R06's mis-added handwritten total corrected to the real sum."""
    out = []
    for r in load_answer_key(KEY):
        if r.receipt_id == "R11":
            continue
        if r.receipt_id == "R06":
            r = r.model_copy(update={"total": r.computed_total, "review_note": "Handwritten total mis-added"})
        out.append(r)
    return out


def codes(flags):
    return [f.code for f in flags]


def test_posted_total_matches_answer_key(approved):
    assert sum(r.posted_amount for r in approved) == Decimal("571.75")


def test_cfc_food_under_cap_for_45_people(approved):
    assert "food_over_cap" not in codes(co.check_funder_rules(EVENT, approved, co.CFC))


def test_cfc_food_over_cap_for_30_people(approved):
    small = co.Event(EVENT.event_id, EVENT.name, EVENT.event_date, attendees=30)
    flags = co.check_funder_rules(small, approved, co.CFC)
    assert "food_over_cap" in codes(flags)
    assert "$360.00" in next(f.message for f in flags if f.code == "food_over_cap")


def test_cfc_club_share(approved):
    # cost 571.75 -> max grant at 90% is 514.58 (half-up)
    assert "club_share_too_low" not in codes(co.check_funder_rules(EVENT, approved, co.CFC, requested=Decimal("514.57")))
    assert "club_share_too_low" in codes(co.check_funder_rules(EVENT, approved, co.CFC, requested=Decimal("520")))


def test_cfc_max_award(approved):
    assert "over_max_award" in codes(co.check_funder_rules(EVENT, approved, co.CFC, requested=Decimal("2600")))


def test_cfc_report_due_21_days_after():
    assert co.report_due(EVENT, co.CFC) == date(2026, 12, 5)
    assert co.report_due(EVENT, co.ORG) is None


def test_missing_receipt_blocks_for_funder(approved):
    msgs = [f.message for f in co.check_funder_rules(EVENT, approved, co.CFC) if f.code == "no_receipt_for_funder"]
    assert len(msgs) == 1 and msgs[0].startswith("R14")


def test_org_bans_food_and_warns_on_decorations(approved):
    flags = co.check_funder_rules(EVENT, approved, co.ORG)
    banned = {f.message.split(":")[0] for f in flags if f.code == "banned_category"}
    assert {"R02", "R03", "R05", "R06", "R07"} <= banned
    maybe = " ".join(f.message for f in flags if f.code == "maybe_banned")
    assert "Balloons" in maybe and "Table cover" in maybe


def test_org_purchase_window(approved):
    late = co.check_funder_rules(EVENT, approved, co.ORG, applied_on=date(2027, 1, 5))
    assert "outside_window" in codes(late)
    ok = co.check_funder_rules(EVENT, approved, co.ORG, applied_on=date(2026, 11, 18))
    assert "outside_window" not in codes(ok)


def test_payer_summary_balances(approved):
    lines = co.payer_summary(approved, reimbursed={"Member A": Decimal("10.00")})
    assert sum(line.fronted for line in lines) == Decimal("571.75")
    assert any(line.payer == "(no payer)" for line in lines)          # R07
    a = next(line for line in lines if line.payer == "Member A")
    assert a.owed == a.fronted - Decimal("10.00")
    assert [line.owed for line in lines] == sorted((line.owed for line in lines), reverse=True)


def test_funder_report_csv_has_items_flags_and_owed(approved):
    text = co.funder_report_csv(EVENT, approved, co.CFC, requested=Decimal("520"))
    assert "Example event grant" in text and "571.75" in text
    assert "club_share_too_low" in text and "R14" in text and "MISSING" in text
    assert "Member A" in text


def test_max_request_for_cfc_keeps_club_share(approved):
    most, steps = co.max_request(EVENT, approved, co.CFC)
    assert most == Decimal("514.58")           # 571.75 x 90%, half-up
    assert "club_share_too_low" not in codes(co.check_funder_rules(EVENT, approved, co.CFC, requested=most))


def test_max_request_removes_food_over_cap(approved):
    small = co.Event(EVENT.event_id, EVENT.name, EVENT.event_date, attendees=30)  # cap $360
    most, steps = co.max_request(small, approved, co.CFC)
    assert most < Decimal("514.58") and any("over the $360.00 cap" in s for s in steps)


def test_max_request_for_org_drops_food_and_caps_at_250(approved):
    most, steps = co.max_request(EVENT, approved, co.ORG)
    assert any("doesn't fund" in s for s in steps)
    assert most <= Decimal("250")
