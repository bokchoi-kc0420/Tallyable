"""Draw the books for the fake event and save each report tab as a PNG, to check the
sheet's look without a Google account. Builds the Excel download (same look as the
Google Sheet), then prints it with LibreOffice.

    python scripts/sheet_preview.py [out_dir]        (default: output/sheet_preview)

Needs LibreOffice (`soffice`) and poppler (`pdftoppm`) on the PATH.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from treasurer.loader import load_answer_key  # noqa: E402
from treasurer.models import Status  # noqa: E402
from treasurer.post import TX_FIELDS  # noqa: E402
from treasurer.sheets import EventInfo, local_transactions, local_views  # noqa: E402
from treasurer.xlsx_export import book_xlsx  # noqa: E402


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    receipts = []
    for r in load_answer_key(ROOT / "fake_event" / "answer_key.csv"):
        if r.receipt_id == "R11":  # the planted duplicate
            continue
        if r.receipt_id == "R06":  # the planted math error, fixed the way a reviewer would
            r = r.model_copy(update={"total": r.computed_total})
        receipts.append(r.model_copy(update={"status": Status.APPROVED}))
    event = EventInfo("EVT-FAKE-01", "Fall Mentor Mixer (FAKE)", date(2026, 11, 14), 45)
    income = {"Zelle": Decimal("300"), "Venmo": Decimal("250"), "Cash": Decimal("40"),
              "Grants and funding": Decimal("50")}
    wb = load_workbook(BytesIO(book_xlsx(local_views(receipts, event, income), local_transactions(receipts),
                                         TX_FIELDS)))
    wb.remove(wb["Transactions"])
    for ws in wb.worksheets:  # one landscape page wide per tab
        ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    book = out / "books.xlsx"
    wb.save(book)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out), str(book)],
                   check=True, capture_output=True, timeout=180)
    subprocess.run(["pdftoppm", "-r", "110", "-png", str(out / "books.pdf"), str(out / "page")], check=True)
    for p in sorted(out.glob("page-*.png")):
        print("saved", p)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "sheet_preview")
