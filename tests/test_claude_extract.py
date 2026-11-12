"""ClaudeExtractor against a fake client: no network, no key."""
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from treasurer.claude_extract import ClaudeExtractor, ExtractedItem, ExtractedReceipt
from treasurer.extract import ExtractionError


class FakeClient:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.calls = []
        resp = NS(parsed_output=parsed, stop_reason=stop_reason, model="claude-opus-5-5",
                  usage=NS(input_tokens=1500, output_tokens=300))
        self.beta = NS(messages=NS(parse=lambda **kw: self.calls.append(kw) or resp))


def reading(**over):
    base = dict(place="Bulk Warehouse", date="2026-11-12", tax="1.61", tip="0.00", total="$31.07",
                items=[ExtractedItem(item="Water 24pk", category="Drink", unit=2, price="4.99")])
    return ExtractedReceipt(**{**base, **over})


def test_maps_reading_to_receipt():
    client = FakeClient(reading())
    ex = ClaudeExtractor(client=client)
    r = ex.extract(b"jpg-bytes", "R01.jpg", "EVT", "R01")
    assert r.total == Decimal("31.07") and r.payer is None and r.image_hash
    assert r.items[0].amount == Decimal("9.98")
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5" and call["output_format"] is ExtractedReceipt
    assert call["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"
    assert ex.cost() == pytest.approx(1500 * 4 / 1e6 + 300 * 20 / 1e6)


def test_refusal_and_bad_date_raise_extraction_error():
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=FakeClient(None, "refusal")).extract(b"x", "R01.jpg", "EVT", "R01")
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=FakeClient(reading(date="Nov 12"))).extract(b"x", "R01.jpg", "EVT", "R01")


def test_no_date_uses_today_and_says_so():  # a phone order screen with no date crashed the read
    from datetime import date
    r = ClaudeExtractor(client=FakeClient(reading(date=""))).extract(b"x", "R01.png", "EVT", "R01")
    assert r.date == date.today() and "No date" in r.review_note


def test_qty_zero_line_is_not_charged():  # Dollar Tree: "Bag Fee 0 0.10 0.00N" was counted as $0.10
    items = [ExtractedItem(item="Mini cups", category="Other", unit=2, price="1.50"),
             ExtractedItem(item="Bag Fee", category="Other", unit=0, price="0.10")]
    r = ClaudeExtractor(client=FakeClient(reading(items=items))).extract(b"x", "R01.jpg", "EVT", "R01")
    assert [i.item for i in r.items] == ["Mini cups"]


def test_a_cart_screenshot_is_called_out_as_not_a_final_receipt():
    r = ClaudeExtractor(client=FakeClient(reading(proof="cart"))).extract(b"x", "cart.png", "EVT", "R01")
    assert "not a final receipt" in r.review_note
    assert ClaudeExtractor(client=FakeClient(reading())).extract(b"x", "R01.jpg", "EVT", "R01").review_note is None


def test_reader_uses_stub_in_tests():
    from treasurer.reader import make_extractor
    assert make_extractor()[1] == "stub"


def test_pdf_goes_as_a_document_block():
    client = FakeClient(reading())
    ClaudeExtractor(client=client).extract(b"%PDF-1.7", "R16.pdf", "EVT", "R16")
    assert client.calls[0]["messages"][0]["content"][0]["type"] == "document"


def test_discount_prices_parse_as_negative():
    from treasurer.claude_extract import _money
    for text in ("-$4.00", "$-4.00", "−4.00", "($4.00)"):
        assert _money(text, "price", "x.png") == Decimal("-4.00")
