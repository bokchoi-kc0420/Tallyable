"""score_all and try_one, with the stub standing in for Claude (no API, no cost)."""
import json
from pathlib import Path

from treasurer import score_all, try_one
from treasurer.extract import StubExtractor

KEY = Path(__file__).parent.parent / "fake_event" / "answer_key.csv"
HOLDOUT = Path(__file__).parent.parent / "fake_event_holdout" / "answer_key.csv"


class PaidStub(StubExtractor):
    """Looks like ClaudeExtractor to the scripts: has model, usage and cost()."""
    model = "claude-sonnet-5-5"

    def __init__(self, key=KEY):
        super().__init__(key)  # stub misreads are keyed to main-set ids, so holdout reads clean
        self.usage = []

    def extract(self, image, filename, event_id, receipt_id):
        self.usage.append({"receipt_id": receipt_id, "model": self.model, "input": 2000, "output": 500})
        return super().extract(image, filename, event_id, receipt_id)

    def cost(self):
        return 0.009 * len(self.usage)


def fake_reader(monkeypatch, module, key=KEY):
    ex = PaidStub(key)
    monkeypatch.setattr(module, "make_extractor", lambda: (ex, "claude"))
    return ex


def test_score_all_reports_accuracy_and_saves_json(monkeypatch, tmp_path, capsys):
    fake_reader(monkeypatch, score_all)
    monkeypatch.setattr(score_all, "ROOT", tmp_path)
    assert score_all.main([]) == 0
    out = capsys.readouterr().out
    assert "14/14 receipts read" in out and "Overall field accuracy" in out
    saved = json.loads((tmp_path / "output" / "score_claude-sonnet-5-5.json").read_text())
    assert sorted(saved["misses"]) == ["R02.tax", "R05.line3.unit", "R08.place", "R13.tip"]


def test_score_all_holdout_scores_the_unseen_set(monkeypatch, tmp_path, capsys):
    fake_reader(monkeypatch, score_all, HOLDOUT)
    monkeypatch.setattr(score_all, "ROOT", tmp_path)
    assert score_all.main(["--set", "holdout"]) == 0
    out = capsys.readouterr().out
    assert "holdout set" in out and "12/12 receipts read" in out
    saved = json.loads((tmp_path / "output" / "score_claude-sonnet-5-5_holdout.json").read_text())
    assert saved["set"] == "holdout" and saved["overall"] == 1.0
    assert not (tmp_path / "output" / "score_claude-sonnet-5-5.json").exists()  # main-set result untouched


def test_holdout_shares_nothing_with_the_main_set():
    from treasurer.loader import load_answer_key
    main, held = load_answer_key(KEY), load_answer_key(HOLDOUT)
    assert {r.receipt_id for r in main}.isdisjoint(r.receipt_id for r in held)
    main_items = {i.item.casefold() for r in main for i in r.items}
    assert main_items.isdisjoint(i.item.casefold() for r in held for i in r.items)
    for r in held:  # every holdout receipt adds up, so a miss is the model's, not the key's
        assert r.subtotal + r.tax + r.tip == r.total, r.receipt_id


def test_score_all_stops_at_budget(monkeypatch, tmp_path, capsys):
    fake_reader(monkeypatch, score_all)
    monkeypatch.setattr(score_all, "ROOT", tmp_path)
    assert score_all.main(["--budget", "0.30"]) == 0       # estimate $0.28 fits
    assert score_all.main(["--budget", "0.10"]) == 1       # estimate over budget: refuses to start
    assert "over budget" in capsys.readouterr().out


def test_score_all_without_key_explains(monkeypatch, capsys):
    monkeypatch.setattr(score_all, "make_extractor", lambda: (StubExtractor(KEY), "stub"))
    assert score_all.main([]) == 1
    assert "No ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_try_one_prints_the_reading_and_flags(monkeypatch, capsys):
    fake_reader(monkeypatch, try_one)
    assert try_one.main([str(KEY.parent / "receipts" / "R02.jpg")]) == 0
    out = capsys.readouterr().out
    assert "Chicken Shack" in out and "FLAG math_error" in out
