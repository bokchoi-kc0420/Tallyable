import io
from datetime import date
from decimal import Decimal

from PIL import Image

from treasurer.models import LineItem, Receipt
from treasurer.photo_pdf import receipts_pdf


def _receipt(rid, payer):
    return Receipt(receipt_id=rid, event_id="E1", place="Corner Market", date=date(2026, 10, 3), payer=payer,
                   items=[LineItem(category="Food", item="chips", unit=1, price=Decimal("4.50"))], total=Decimal("4.50"))


def test_one_labeled_page_per_receipt_even_without_a_photo():
    buf = io.BytesIO()
    Image.new("RGB", (400, 800), "gray").save(buf, "JPEG")
    pdf = receipts_pdf([_receipt("R02", "Member B"), _receipt("R01", None)],
                       {"R02": (buf.getvalue(), "image/jpeg")}, {"R02": "Yes"})
    assert pdf.startswith(b"%PDF")
    assert b"/Count 2" in pdf
