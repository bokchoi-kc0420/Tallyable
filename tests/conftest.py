import os

# Never call the real API in tests, even if a .env with a key exists locally.
os.environ["TALLYABLE_EXTRACTOR"] = "stub"
os.environ["TALLYABLE_SHEET_ID"] = ""  # and never write to a real Google Sheet

import tempfile

os.environ["TALLYABLE_OUTPUT_DIR"] = tempfile.mkdtemp(prefix="tallyable-test-")  # keep real logs clean

import sys

import pytest


@pytest.fixture(autouse=True)
def fresh_output_dir(tmp_path, monkeypatch):
    """Each test gets its own output folder, so saved sessions and logs don't leak between tests."""
    monkeypatch.setenv("TALLYABLE_OUTPUT_DIR", str(tmp_path / "output"))
    for name in [m for m in sys.modules if m == "ui" or m.startswith("ui.")]:
        del sys.modules[name]  # ui.common reads the folder on import, so import it fresh
