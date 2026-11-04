import os

# Never call the real API in tests, even if a .env with a key exists locally.
os.environ["TALLYABLE_EXTRACTOR"] = "stub"
os.environ["TALLYABLE_SHEET_ID"] = ""  # and never write to a real Google Sheet
