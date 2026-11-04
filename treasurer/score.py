"""Score AI drafts against the answer key: share of fields read correctly."""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .models import Receipt

RECEIPT_FIELDS = ["place", "date", "tax", "tip", "total"]
ITEM_FIELDS = ["category", "item", "unit", "price"]


@dataclass
class Score:
    correct: dict[str, int] = field(default_factory=dict)
    total: dict[str, int] = field(default_factory=dict)
    misses: list[str] = field(default_factory=list)
    extra_lines: int = 0  # lines the AI invented; not in `overall`, reported separately

    def add(self, name: str, ok: bool, where: str) -> None:
        self.total[name] = self.total.get(name, 0) + 1
        self.correct[name] = self.correct.get(name, 0) + int(ok)
        if not ok:
            self.misses.append(f"{where}.{name}")

    @property
    def overall(self) -> float:
        t = sum(self.total.values())
        return sum(self.correct.values()) / t if t else 0.0

    def by_field(self) -> dict[str, float]:
        return {k: self.correct[k] / self.total[k] for k in self.total}


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def align(truth_items: list, draft_items: list, min_similarity: float = 0.5) -> list[tuple[int, int | None]]:
    """Pair each true line with the draft line that best matches it.

    Matching by position alone is unfair: if the AI adds one extra line at the top,
    every line after it would count as wrong. So lines are paired by how similar
    the item names are (with a bonus when the price matches too), best pairs
    first, each draft line used once. Returns (truth index, draft index or None).
    """
    pairs = []
    for ti, t in enumerate(truth_items):
        for di, d in enumerate(draft_items):
            s = _similar(t.item, d.item) + (0.3 if t.price == d.price else 0) - 0.01 * abs(ti - di)
            pairs.append((s, ti, di))
    taken_t, taken_d, out = set(), set(), {}
    for s, ti, di in sorted(pairs, reverse=True):
        if ti in taken_t or di in taken_d or s < min_similarity:
            continue
        taken_t.add(ti)
        taken_d.add(di)
        out[ti] = di
    return [(ti, out.get(ti)) for ti in range(len(truth_items))]


def score(drafts: dict[str, Receipt], truth: dict[str, Receipt]) -> Score:
    """Both dicts are keyed by the same receipt id. Lines are paired with align().
    A true line the AI missed counts every field on it as wrong; a line the AI
    invented is listed in misses as `extra_line` and counted in `extra_lines`."""
    s = Score()
    for rid, t in truth.items():
        d = drafts.get(rid)
        for f in RECEIPT_FIELDS:
            s.add(f, d is not None and _norm(getattr(d, f)) == _norm(getattr(t, f)), rid)
        pairs = align(t.items, d.items) if d else [(n, None) for n in range(len(t.items))]
        for ti, di in pairs:
            for f in ITEM_FIELDS:
                ok = di is not None and _norm(getattr(d.items[di], f)) == _norm(getattr(t.items[ti], f))
                s.add(f, ok, f"{rid}.line{ti + 1}")
        used = {di for _, di in pairs if di is not None}
        for di in range(len(d.items) if d else 0):
            if di not in used:
                s.extra_lines += 1
                s.misses.append(f"{rid}.extra_line{di + 1}")
    return s
