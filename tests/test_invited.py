"""The hosted link reads real receipts only for invited Google emails, so strangers can't spend the API credit."""
from ui import common


def test_only_invited_emails_read_on_the_hosted_link(monkeypatch):
    monkeypatch.setattr(common, "hosted", lambda: True)
    monkeypatch.setattr(common.st, "secrets", {"INVITED": "kev@example.com, Treasurer@Club.org"})
    for email, ok in [("kev@example.com", True), ("treasurer@club.org", True), ("stranger@gmail.com", False)]:
        monkeypatch.setattr(common, "signed_in_email", lambda e=email: e)
        assert common.invited() is ok
    monkeypatch.setattr(common.st, "secrets", {})
    assert not common.invited()  # no list yet: nobody spends credit


def test_everyone_reads_locally(monkeypatch):
    monkeypatch.setattr(common, "hosted", lambda: False)
    assert common.invited()
