"""Saving an event: photos live in their own file, written only when asked, and old files still open."""
import base64
import json
from datetime import date

from treasurer import session_store


def state(images: dict) -> dict:
    return {"event": {"event_id": "EVT-A", "name": "A", "date": date(2026, 11, 14)}, "receipts": {}, "images": images,
            "step": "2. Review"}


def test_photos_get_their_own_file_and_old_files_still_open(tmp_path):
    path = tmp_path / "EVT-A.json"
    session_store.save(path, state({"R01": (b"jpeg bytes", "image/jpeg")}))
    assert b"jpeg bytes" not in path.read_bytes()  # the event file stays small: every click rewrites it
    assert session_store.load(path)["images"] == {"R01": (b"jpeg bytes", "image/jpeg")}

    session_store.save(path, state({"R01": (b"ignored", "image/jpeg")}), photos=False)  # a page switch
    assert session_store.load(path)["images"]["R01"][0] == b"jpeg bytes"

    old = json.loads(session_store.dump(state({})))  # version 1 kept the photos inside the event file
    old.update(version=1, images={"R01": [base64.b64encode(b"v1 photo").decode(), "image/png"]})
    path.write_text(json.dumps(old))
    assert session_store.load(path)["images"] == {"R01": (b"v1 photo", "image/png")}

    session_store.save(path, state({"R01": (b"jpeg bytes", "image/jpeg")}))
    session_store.clear(path)  # deleting an event takes its photos too
    assert list(tmp_path.iterdir()) == []
