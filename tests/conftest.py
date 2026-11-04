import os

# Never call the real API in tests, even if a .env with a key exists locally.
os.environ["TALLYABLE_EXTRACTOR"] = "stub"
os.environ["TALLYABLE_SHEET_ID"] = ""  # and never write to a real Google Sheet

import tempfile

os.environ["TALLYABLE_OUTPUT_DIR"] = tempfile.mkdtemp(prefix="tallyable-test-")  # keep real logs clean
