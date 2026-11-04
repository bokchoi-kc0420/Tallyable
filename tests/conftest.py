import os

# Never call the real API in tests, even if a .env with a key exists locally.
os.environ["TALLYABLE_EXTRACTOR"] = "stub"
