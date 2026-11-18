"""The hosted link: one folder per Google account, and no linking another club's sheet."""
import json


def test_each_signed_in_account_gets_its_own_folder(monkeypatch):
    from ui import common
    local = common.base()
    monkeypatch.setattr(common, "signed_in_email", lambda: "a@ucdavis.edu")
    a = common.base()
    monkeypatch.setattr(common, "signed_in_email", lambda: "b@ucdavis.edu")
    assert len({local, a, common.base()}) == 3  # locally nothing changes; two clubs never share a folder


def test_hosted_link_refuses_a_sheet_the_signed_in_person_cant_edit(monkeypatch):
    from ui import connect

    class Book:
        title = "Club books"

        def batch_update(self, body):
            pass

    class Client:
        def open_by_key(self, key):
            return Book()

        def list_permissions(self, key):
            return [{"type": "user", "role": "writer", "emailAddress": "bot@x.iam.gserviceaccount.com"},
                    {"type": "user", "role": "owner", "emailAddress": "Treasurer@ucdavis.edu"}]

    monkeypatch.setattr(connect, "bot_client", lambda root, key: Client())
    assert connect.check({"book": "x"}, "treasurer@ucdavis.edu") is None
    assert "isn't an editor" in connect.check({"book": "x"}, "someone-else@ucdavis.edu")
    assert connect.check({"book": "x"}) is None  # locally (no sign-in) the old check is unchanged


def test_google_key_from_one_env_var(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"client_email": "bot@x.iam.gserviceaccount.com"}))
    from ui import common
    assert common.GCP_KEY["client_email"] == "bot@x.iam.gserviceaccount.com"
