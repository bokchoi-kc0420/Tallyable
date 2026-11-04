from decimal import Decimal
from pathlib import Path

from treasurer.loader import load_answer_key
from treasurer.models import LineItem
from treasurer.score import align, score

KEY = Path(__file__).parent.parent / "fake_event" / "answer_key.csv"
R03 = next(r for r in load_answer_key(KEY) if r.receipt_id == "R03")


def test_perfect_draft_scores_100():
    assert score({"R03": R03}, {"R03": R03}).overall == 1.0


def test_one_invented_line_does_not_shift_the_rest():
    fake = LineItem(category="Other", item="Bag fee", unit=1, price=Decimal("0.10"))
    draft = R03.model_copy(update={"items": [fake, *R03.items]})
    s = score({"R03": draft}, {"R03": R03})
    assert s.overall == 1.0
    assert s.extra_lines == 1 and s.misses == ["R03.extra_line1"]


def test_missed_line_counts_its_fields_wrong():
    draft = R03.model_copy(update={"items": R03.items[1:]})
    s = score({"R03": draft}, {"R03": R03})
    assert all(m.startswith("R03.line1.") for m in s.misses) and len(s.misses) == 4


def test_misspelled_item_still_pairs_and_only_name_is_wrong():
    first = R03.items[0]
    typo = first.model_copy(update={"item": first.item.replace("e", "3", 1)})
    draft = R03.model_copy(update={"items": [typo, *R03.items[1:]]})
    assert score({"R03": draft}, {"R03": R03}).misses == ["R03.line1.item"]


def test_reordered_lines_pair_by_name():
    draft = R03.model_copy(update={"items": list(reversed(R03.items))})
    assert align(R03.items, draft.items)[0] == (0, len(R03.items) - 1)
    assert score({"R03": draft}, {"R03": R03}).overall == 1.0
