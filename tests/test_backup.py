"""The hosted link's saved data survives a Heroku restart (a wiped disk). Needs a Postgres to talk to:
set TEST_DATABASE_URL, otherwise these skip."""
import os
import shutil

import pytest

from treasurer import backup

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="no TEST_DATABASE_URL")


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    backup._db.cache_clear()
    backup._db().execute("DELETE FROM files")
    yield
    backup._db.cache_clear()


def test_a_wiped_disk_gets_every_account_file_back(db, tmp_path):
    folder = tmp_path / "users" / "abc"
    (folder / "real" / "events").mkdir(parents=True)
    (folder / "real" / "clubs.json").write_text('{"clubs": 1}')
    (folder / "real" / "events" / "e1.photos").write_bytes(b"\xff\xd8 photo")
    (folder / "real" / "events" / "e1.json.tmp").write_text("half written")
    seen = backup.push(folder, tmp_path, {})

    (folder / "real" / "clubs.json").write_text('{"clubs": 2}')  # an edit after the first save
    (folder / "real" / "events" / "e1.photos").unlink()  # a reset event
    backup.push(folder, tmp_path, seen)

    shutil.rmtree(tmp_path / "users")  # the restart
    backup.restore(folder, tmp_path)
    assert (folder / "real" / "clubs.json").read_text() == '{"clubs": 2}'
    assert not (folder / "real" / "events" / "e1.photos").exists()
    assert not (folder / "real" / "events" / "e1.json.tmp").exists()


def test_one_account_never_gets_another_accounts_files(db, tmp_path):
    (tmp_path / "users" / "a").mkdir(parents=True)
    (tmp_path / "users" / "a" / "mode.txt").write_text("real")
    backup.push(tmp_path / "users" / "a", tmp_path, {})
    shutil.rmtree(tmp_path / "users")
    assert backup.restore(tmp_path / "users" / "ab", tmp_path) == {}
