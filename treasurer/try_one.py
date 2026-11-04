"""Read one receipt with Claude and print what it saw.

    python -m treasurer.try_one fake_event/receipts/R01.jpg
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .checks import run_checks
from .claude_extract import estimate
from .extract import ExtractionError
from .reader import make_extractor


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    path = Path(argv[0])
    ex, label = make_extractor()
    if label != "claude":
        print("No ANTHROPIC_API_KEY found in .env, so this would only run the stub. Add the key first.")
        return 1
    print(f"Reading with {ex.model} (estimated at most ${estimate(ex.model, 1):.3f})...\n")
    start = time.time()
    try:
        r = ex.extract(path.read_bytes(), path.name, "EVT-FAKE-01", path.stem.upper())
    except ExtractionError as e:
        print(f"Failed: {e}")
        return 1
    print(f"{r.receipt_id}  {r.place}  {r.date}")
    for i in r.items:
        print(f"  {i.category:<6} {i.item:<30} {i.unit} x {i.price}" + ("  (returned)" if i.returned else ""))
    print(f"  tax {r.tax}  tip {r.tip}  printed total {r.total}  items+tax+tip {r.computed_total}")
    if r.review_note:
        print(f"  Claude's note: {r.review_note}")
    for f in run_checks([r])[r.receipt_id]:
        if f.code != "missing_payer":  # no payer tag in this script
            print(f"  FLAG {f.code}: {f.message}")
    u = ex.usage[-1]
    print(f"\n{u['model']} · {u['input']} in / {u['output']} out tokens · ~${ex.cost():.4f} · {time.time() - start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
