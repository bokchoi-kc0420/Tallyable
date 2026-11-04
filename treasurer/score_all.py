"""Read every fake receipt with Claude and score it against the answer key.

    python -m treasurer.score_all
    python -m treasurer.score_all --model claude-haiku-5-5
    python -m treasurer.score_all --budget 0.50

Prints an estimate first, then field accuracy, every miss, tokens, cost and time.
Stops early if the running cost passes --budget (default $1.00).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .claude_extract import estimate
from .extract import ExtractionError
from .loader import load_answer_key
from .reader import ANSWER_KEY, ROOT, make_extractor
from .score import score


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", help="e.g. claude-haiku-5-5 (default: TALLYABLE_MODEL or claude-sonnet-5-5)")
    p.add_argument("--budget", type=float, default=1.00, help="stop once the run has cost this many dollars")
    args = p.parse_args(argv)

    ex, label = make_extractor()
    if label != "claude":
        print("No ANTHROPIC_API_KEY found in .env, so there is nothing real to score. Add the key first.")
        return 1
    if args.model:
        ex.model = args.model

    truth = {r.receipt_id: r for r in load_answer_key(ANSWER_KEY) if r.image_file}
    est = estimate(ex.model, len(truth))
    print(f"{ex.model}: {len(truth)} receipts, estimated at most ${est:.2f}. Budget ${args.budget:.2f}.")
    if est > args.budget:
        print("The estimate is over budget. Use a cheaper --model or raise --budget.")
        return 1
    drafts, failed = {}, []
    start = time.time()
    for rid, t in truth.items():
        if ex.cost() >= args.budget:
            print(f"Stopping: spent ${ex.cost():.3f}, budget ${args.budget:.2f}.")
            break
        path = ANSWER_KEY.parent / t.image_file
        print(f"reading {path.name} ...", end=" ", flush=True)
        try:
            drafts[rid] = ex.extract(path.read_bytes(), path.name, t.event_id, rid)
            print("ok")
        except ExtractionError as e:
            failed.append(rid)
            print(f"FAILED: {e}")
    secs = time.time() - start

    s = score(drafts, truth)
    print(f"\nModel {ex.model} · {len(drafts)}/{len(truth)} receipts read · {secs:.0f}s · ~${ex.cost():.3f}")
    print(f"Overall field accuracy: {s.overall:.1%}")
    for f, acc in s.by_field().items():
        print(f"  {f:<9} {acc:.1%}")
    if s.misses:
        print(f"\nMisses ({len(s.misses)}):")
        for m in s.misses:
            print(f"  {m}")

    out = ROOT / "output" / f"score_{ex.model}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "model": ex.model, "seconds": round(secs, 1), "cost_usd": round(ex.cost(), 4),
        "overall": s.overall, "by_field": s.by_field(), "misses": s.misses, "failed": failed,
        "usage": ex.usage,
        "drafts": {rid: json.loads(r.model_dump_json()) for rid, r in drafts.items()},
    }, indent=2))
    print(f"\nSaved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
