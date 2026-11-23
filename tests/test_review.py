"""Savings get their own box on Review: splitting them out and back must never move or lose a line."""
from decimal import Decimal

from treasurer.models import LineItem
from ui.review import merge_savings, split_savings


def line(item: str, price: str, above: bool = False) -> LineItem:
    return LineItem(category="Drink", item=item, unit=1, price=Decimal(price), for_item_above=above)


def test_savings_go_back_under_their_item():
    items = [line("Lemonade", "3.99"), line("Member Savings", "-1.98", True), line("Soda", "3.99"),
             line("Member Savings", "-1.98", True), line("Coupon", "-1.00")]
    bought, savings, after = split_savings(items)
    assert [i.item for i in bought] == ["Lemonade", "Soda"]
    assert merge_savings(bought, savings, after) == items


def test_a_saving_whose_item_is_deleted_comes_off_the_whole_order():
    items = [line("Lemonade", "3.99"), line("Soda", "3.99"), line("Member Savings", "-1.98", True)]
    bought, savings, after = split_savings(items)
    merged = merge_savings(bought[:1], savings, after)
    assert [i.item for i in merged] == ["Lemonade", "Member Savings"]
    assert not merged[-1].for_item_above
