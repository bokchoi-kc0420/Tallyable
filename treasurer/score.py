"""Score AI drafts against the answer key: share of fields read correctly."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Receipt

RECEIPT_FIELDS = ["place", "date", "tax", "tip", "total"]
ITEM_FIELDS = ["category", "item", "unit", "price"]


@dataclass
class Score:
    correct: dict[str, int] = field(default_factory=dict)
    total: dict[str, int] = field(default_factory=dict)
    misses: list[str] = field(default_factory=list)

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


def score(drafts: dict[str, Receipt], truth: dict[str, Receipt]) -> Score:
    """Both dicts are keyed by the same receipt id. Items are matched by position;
    a missing or extra line counts every field on that line as wrong."""
    s = Score()
    for rid, t in truth.items():
        d = drafts.get(rid)
        for f in RECEIPT_FIELDS:
            s.add(f, d is not None and _norm(getattr(d, f)) == _norm(getattr(t, f)), rid)
        for n in range(max(len(t.items), len(d.items) if d else 0)):
            ti = t.items[n] if n < len(t.items) else None
            di = d.items[n] if d and n < len(d.items) else None
            for f in ITEM_FIELDS:
                ok = ti is not None and di is not None and _norm(getattr(di, f)) == _norm(getattr(ti, f))
                s.add(f, ok, f"{rid}.line{n + 1}")
    return s
