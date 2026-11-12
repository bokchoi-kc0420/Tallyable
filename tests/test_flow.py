from decimal import Decimal
from pathlib import Path

import pytest

from treasurer.checks import run_checks
from treasurer.extract import ExtractionError, StubExtractor
from treasurer.loader import load_answer_key
from treasurer.models import Status
from treasurer.post import LocalCsvSink, event_totals
from treasurer.score import score

FAKE = Path(__file__).parent.parent / "fake_event"
KEY = FAKE / "answer_key.csv"


@pytest.fixture(scope="module")
def truth():
    return {r.receipt_id: r for r in load_answer_key(KEY)}


@pytest.fixture(scope="module")
def drafts():
    ex = StubExtractor(KEY)
    out = {}
    for p in sorted((FAKE / "receipts").glob("*.jpg")):
        out[p.stem] = ex.extract(p.read_bytes(), p.name, "EVT-FAKE-01", p.stem)
    return out


def test_stub_rejects_unknown_image():
    with pytest.raises(ExtractionError):
        StubExtractor(KEY).extract(b"", "selfie.jpg", "E", "R99")


def test_scorer_counts_exactly_the_stub_misreads(drafts, truth):
    truth_with_images = {k: v for k, v in truth.items() if k in drafts}
    s = score(drafts, truth_with_images)
    assert sorted(s.misses) == ["R02.tax", "R05.line3.unit", "R08.place", "R13.tip"]
    assert 0.9 < s.overall < 1.0


def test_tax_and_tip_misreads_trip_the_math_check(drafts):
    flags = run_checks(list(drafts.values()))
    assert any(f.code == "math_error" for f in flags["R02"])
    assert any(f.code == "math_error" for f in flags["R13"])


def test_push_is_idempotent(tmp_path, truth):
    sink = LocalCsvSink(tmp_path / "tx.csv")
    approved = [r.model_copy(update={"status": Status.APPROVED}) for r in list(truth.values())[:3]]
    assert sink.post(approved) == ["R01", "R02", "R03"]
    posted = [r.model_copy(update={"status": Status.POSTED}) for r in approved]  # what the app does after a push
    assert sink.post(posted) == []  # second click writes nothing
    lines = (tmp_path / "tx.csv").read_text().strip().splitlines()
    assert len(lines) == 1 + sum(len(r.items) for r in approved)


def test_a_reopened_receipt_replaces_its_old_rows(tmp_path, truth):
    """Kevin's first real run: a $0 receipt was pushed and could not be fixed."""
    sink = LocalCsvSink(tmp_path / "tx.csv")
    first, other = [r.model_copy(update={"status": Status.APPROVED}) for r in list(truth.values())[:2]]
    sink.post([first, other])
    fixed = first.model_copy(update={"place": "Fixed Place"})  # reopened, edited, approved again
    assert sink.post([fixed, other.model_copy(update={"status": Status.POSTED})]) == ["R01"]
    text = (tmp_path / "tx.csv").read_text()
    assert "Fixed Place" in text and first.place not in text
    assert len(text.strip().splitlines()) == 1 + len(first.items) + len(other.items)
    left_out = fixed.model_copy(update={"status": Status.REJECTED})  # reopened and left out: gone from the books
    sink.post([left_out, other.model_copy(update={"status": Status.POSTED})])
    assert "Fixed Place" not in (tmp_path / "tx.csv").read_text()


def test_next_event_with_same_receipt_ids_still_posts(tmp_path, truth):
    sink = LocalCsvSink(tmp_path / "tx.csv")
    first = [r.model_copy(update={"status": Status.APPROVED}) for r in list(truth.values())[:2]]
    second = [r.model_copy(update={"status": Status.APPROVED, "event_id": "EVT-NEXT"}) for r in first]
    assert sink.post(first) == ["R01", "R02"]
    assert sink.post(second) == ["R01", "R02"]  # new event, ids start over: not "already posted"


def test_only_approved_receipts_count(truth):
    rs = [r.model_copy(update={"status": Status.APPROVED if r.receipt_id == "R01" else Status.DRAFTED})
          for r in truth.values()]
    t = event_totals(rs, {"Zelle": Decimal("100.00")})
    assert t["expenses"] == Decimal("31.07")
    assert t["net"] == Decimal("68.93")
