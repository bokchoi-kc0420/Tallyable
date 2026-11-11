"""The "Books are in!" card after Push, and finishing an event."""
from datetime import date
from decimal import Decimal

from test_app import draft, new_app

from treasurer.models import Status


def pushed_app():
    """Fake event with R01 approved (Member A paid), the rest left out, $100 cash in, pushed."""
    at = new_app().run()
    next(b for b in at.button if b.label.startswith("Use the fake event")).click().run()
    for sb in at.selectbox:
        if sb.key and sb.key.startswith("payer-R"):
            sb.set_value("Member A")
    at.run()
    draft(at)
    for rid in list(at.session_state["receipts"]):
        at.session_state["receipts"][rid] = at.session_state["receipts"][rid].model_copy(
            update={"status": Status.APPROVED if rid == "R01" else Status.REJECTED})
    at.sidebar.radio[0].set_value("3. Summary").run()
    at.text_input(key="income-Cash").set_value("100.00").run()
    at.download_button(key="dl-xlsx-row").click().run()  # no Google Sheet: saving is the push
    assert not at.exception
    return at


def test_done_card_counts_left_out_and_goes_stale_after_an_edit():
    at = pushed_app()
    card = " ".join(m.value for m in at.markdown)
    assert "Your book is ready!" in card  # no Google Sheet in tests: the no-sheet wording
    assert "1 receipt (13 left out) and $100.00 income" in card
    assert at.button(key="to-closeout").proto.type == "primary"  # Close out is the next step now
    at.text_input(key="income-Cash").set_value("120.00").run()
    assert any("You changed something since" in m.value for m in at.markdown)
    next(b for b in at.button if b.label == "Save again").click().run()
    assert any("Your book is ready!" in m.value for m in at.markdown)


def test_finish_shows_open_items_moves_to_past_events_and_reopens():
    at = pushed_app()
    next(b for b in at.button if b.label == "Next: Close out").click().run()
    at.button(key="finish-event").click().run()
    assert not at.exception
    page = " ".join(h.value for h in at.get("html"))
    assert "is closed out!" in page and "Set your starting balance" in page  # never set: no made-up balance
    assert any("1 person still owed" in m.value for m in at.markdown)  # honest about Member A
    assert any(b.label == "Reopen" for b in at.sidebar.button)  # its stub sits in Past events
    assert any('class="tly-stub"' in m.value for m in at.sidebar.markdown)  # finished = torn-off stub
    at.button(key="reopen-event").click().run()
    assert not at.session_state["event"]["finished"]
    assert at.sidebar.radio(key="step").value == "4. Close out"
    assert any(b.key == "finish-event" for b in at.button)


def test_start_the_next_event_from_the_finish_page():
    at = pushed_app()
    at.sidebar.radio[0].set_value("4. Close out").run()
    at.button(key="finish-event").click().run()
    at.button(key="next-event").click().run()
    assert not at.exception
    assert at.session_state["receipts"] == {} and "finished" not in at.session_state["event"]
    assert at.sidebar.radio(key="step").value == "1. Upload"


def test_club_balance_adds_this_years_saved_events(tmp_path):
    from treasurer import session_store
    from treasurer.sheets import EventInfo
    from ui import finish

    finish.PAST = tmp_path
    old = {"event": {"event_id": "EVT-A", "name": "A", "date": date(2026, 10, 1)}, "receipts": {}, "images": {},
           "income": {"Cash": "50.00"}}
    last_year = {**old, "event": {"event_id": "EVT-B", "name": "B", "date": date(2025, 10, 1)}}
    session_store.save(tmp_path / "a.json", old)
    session_store.save(tmp_path / "b.json", last_year)
    ev = EventInfo("EVT-C", "C", date(2026, 11, 14), 10, start_balance=Decimal("1000"))
    assert finish.club_balance(ev, Decimal("-20")) == Decimal("1030")


def test_ticket_color_menu_shows_the_color_just_picked():
    at = new_app().run()
    at.sidebar.radio(key="ticket-color").set_value("Sage").run()
    assert at.session_state["event"]["color"] == "Sage"
    assert [p.proto.popover.label for p in at.sidebar.get("popover")] [-1:] == ["Sage"]  # was one pick behind


def test_new_event_from_the_sidebar_opens_on_the_first_step():
    at = pushed_app()
    at.sidebar.radio[0].set_value("4. Close out").run()
    at.button(key="finish-event").click().run()
    at.sidebar.button(key="new-event").click().run()  # a finished event needs no confirm
    assert at.sidebar.radio(key="step").value == "1. Upload"  # was stuck on Close out
    assert at.header[0].value == "Start a new event"
