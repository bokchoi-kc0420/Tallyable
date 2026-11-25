"""Review's line items: removing a line must never move or lose another one."""
from datetime import date
from decimal import Decimal

from treasurer.models import LineItem, Receipt
from ui.common import ss
from ui.lines import drop_line


def line(item: str, price: str, above: bool = False) -> LineItem:
    return LineItem(category="Drink", item=item, unit=1, price=Decimal(price), for_item_above=above)


def test_a_saving_whose_item_is_removed_comes_off_the_whole_order():
    items = [line("Lemonade", "3.99"), line("Soda", "3.99"), line("Member Savings", "-1.98", True), line("Ice", "2.00")]
    ss.receipts = {"R1": Receipt(receipt_id="R1", event_id="E", place="Safeway", date=date(2026, 11, 13),
                                 items=items, total=Decimal("7.99"))}
    drop_line("R1", 1)
    left = ss.receipts["R1"].items
    assert [i.item for i in left] == ["Lemonade", "Member Savings", "Ice"]
    assert not left[1].for_item_above


def test_a_saving_under_a_deposit_line_belongs_to_the_item_above_it():
    """Safeway prints CRV between the soda and its Member Savings: leaving out the soda takes its saving too."""
    items = [line("Lemonade", "3.99"), line("CRV SFTDK SNGL TAX", "0.10"), line("Member Savings", "-1.98", True),
             line("Soda", "3.99")]
    r = Receipt(receipt_id="R1", event_id="E", place="Safeway", date=date(2026, 11, 13), items=items, total=Decimal("6.10"))
    assert r.owners[2].item == "Lemonade"
    out = r.model_copy(update={"items": [items[0].model_copy(update={"returned": True}), *items[1:]]})
    assert out.returned_amount == Decimal("2.01")


def test_lines_leave_out_put_back_add_and_remove():
    """The grid's own boxes: Leave out moves a line to Left out, Put back brings it back, add and trash work."""
    from test_app import new_app, upload_and_draft
    at = new_app().run()
    upload_and_draft(at)
    at.sidebar.radio[0].set_value("2. Review").run()
    items = lambda: at.session_state["receipts"]["R01"].items  # noqa: E731
    at.checkbox(key="out-R01-0-0").check().run()
    assert items()[0].returned and not at.exception
    at.button(key="back-R01-1-0").click().run()
    assert not items()[0].returned
    at.button(key="add-line-R01").click().run()
    assert len(items()) == 4
    at.text_input(key="price-R01-3-3").set_value("2.50").run()
    assert items()[3].price == Decimal("2.50")
    at.button(key="rm-line-R01-3-3").click().run()
    assert [i.item for i in items()] == ["Water 24pk", "Paper plates", "Napkins"]
