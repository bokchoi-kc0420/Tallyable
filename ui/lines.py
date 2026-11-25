"""Review's line items: our own grid of boxes instead of st.data_editor, so nothing can be dragged, sorted or
opened as a menu (friend's #9). One row per line; the receipt's own wording is shaded; left-out lines and savings
each get their own box under the items. Hovering a row shades where that line sits on the photo (#18)."""
from __future__ import annotations

import html
from decimal import Decimal

import streamlit as st

from treasurer.models import LineItem, Receipt
from ui.common import dec, ss, usd

CATEGORIES = ["Food", "Drink", "Other"]
# Qty, Item, On receipt, Price, Category, Leave out, remove: one set of widths for the header and every row.
WIDTHS = [0.55, 1.4, 1.35, 0.8, 1.35, 0.95, 0.3]
SAVING_WIDTHS = [3.4, 2, 0.9, 0.4]  # Saving, Comes off, Price, remove


def ver(rid: str) -> str:
    """Part of every box's key. It changes when lines are added or removed, so no box keeps another line's value."""
    return f"{rid}-{ss.get(f'lines-v-{rid}', 0)}"


def set_items(rid: str, items: list[LineItem]) -> None:
    ss.receipts[rid] = ss.receipts[rid].model_copy(update={"items": items})
    ss[f"lines-v-{rid}"] = ss.get(f"lines-v-{rid}", 0) + 1


def add_line(rid: str) -> None:
    """Button callback: a blank line at the end of the receipt to fill in."""
    set_items(rid, [*ss.receipts[rid].items, LineItem(category="Other", item="New item", unit=1, price=Decimal("0"))])


def drop_line(rid: str, n: int) -> None:
    """Button callback: take a line off. A saving printed under it now comes off the whole order."""
    items = ss.receipts[rid].items
    rest = items[n + 1:]
    k = next((j for j, i in enumerate(rest) if not (i.for_item_above and i.price < 0)), len(rest))
    loose = [i.model_copy(update={"for_item_above": False}) for i in rest[:k]]
    set_items(rid, [*items[:n], *loose, *rest[k:]])


def put_back(rid: str, n: int) -> None:
    """Button callback: a left-out line goes back in the books."""
    items = list(ss.receipts[rid].items)
    items[n] = items[n].model_copy(update={"returned": False})
    set_items(rid, items)


def edited(i: LineItem, **changes) -> LineItem | None:
    """The line with what was typed, or None for an empty name or a qty that isn't a whole number over 0."""
    try:
        return LineItem.model_validate({**i.model_dump(), **changes, "unit": int(str(changes.get("unit", i.unit)).strip())})
    except ValueError:
        return None


def head(labels: list[str], widths: list[float], key: str) -> None:
    with st.container(key=key):
        for col, label in zip(st.columns(widths, vertical_alignment="center", gap="small"), labels, strict=True):
            col.html(f"<p>{label}</p>")


def shaded(col, text: str) -> None:
    """Read-only: there to check against the photo, not to edit."""
    col.html(f'<p class="tly-printed">{html.escape(text)}</p>')


def remove(col, rid: str, n: int, can: bool) -> None:
    col.button("", icon=":material/delete:", type="tertiary", key=f"rm-line-{ver(rid)}-{n}", on_click=drop_line,
               args=(rid, n), disabled=not can, help="Take this line off" if can else "A receipt needs one line")


def bought_row(rid: str, n: int, i: LineItem, can_drop: bool) -> LineItem | None:
    k = f"{ver(rid)}-{n}"
    with st.container(key=f"line-{rid}-{n}"):
        c = st.columns(WIDTHS, vertical_alignment="center", gap="small")
        unit = c[0].text_input("Qty", str(i.unit), key=f"qty-{k}", label_visibility="collapsed")
        item = c[1].text_input("Item", i.item, key=f"item-{k}", label_visibility="collapsed")
        shaded(c[2], i.printed or i.item)
        price = c[3].text_input("Price", f"{i.price:.2f}", key=f"price-{k}", label_visibility="collapsed")
        cat = c[4].selectbox("Category", CATEGORIES, index=CATEGORIES.index(i.category), key=f"cat-{k}",
                             label_visibility="collapsed")
        out = c[5].checkbox("Leave out", i.returned, key=f"out-{k}", label_visibility="collapsed",
                            help="A personal buy, or returned: it moves to Left out")
        remove(c[6], rid, n, can_drop)
    return edited(i, unit=unit, item=item.strip(), price=dec(price), category=cat, returned=out)


def saving_row(rid: str, n: int, i: LineItem, on: str, can_drop: bool) -> LineItem | None:
    k = f"{ver(rid)}-{n}"
    with st.container(key=f"line-{rid}-{n}"):
        c = st.columns(SAVING_WIDTHS, vertical_alignment="center", gap="small")
        item = c[0].text_input("Saving", i.item, key=f"item-{k}", label_visibility="collapsed")
        shaded(c[1], on)
        price = c[2].text_input("Price", f"{i.price:.2f}", key=f"price-{k}", label_visibility="collapsed")
        remove(c[3], rid, n, can_drop)
    return edited(i, item=item.strip(), price=dec(price))


def left_out_box(r: Receipt, out: list[int]) -> str:
    """Left-out lines in their own dashed box, greyed, each with Put back. Returns why they're left out."""
    rid = r.receipt_id
    with st.container(key=f"left-out-box-{rid}"):
        st.html(f'<p class="tly-out-head"><span>Left out</span><b>&minus;{usd(r.returned_amount)}</b></p>')
        for n in out:
            i = r.items[n]
            with st.container(key=f"line-{rid}-{n}", horizontal=True, vertical_alignment="center"):
                st.html(f'<p class="tly-out-line">{i.unit} &middot; {html.escape(i.item)} &middot; {i.price:.2f}</p>')
                st.button("Put back", icon=":material/undo:", type="tertiary", key=f"back-{ver(rid)}-{n}",
                          on_click=put_back, args=(rid, n))
        return st.segmented_control("Left out because", ["personal", "returned"], default=r.left_out_why,
                                    format_func={"personal": "Personal", "returned": "Returned"}.get,
                                    key=f"why-{rid}") or r.left_out_why


def savings_box(r: Receipt, savings: list[int], can_drop: bool) -> dict[int, LineItem | None]:
    """Member savings, coupons and promos in their own green box (Kevin's pick B), each saying which item it comes off."""
    rid = r.receipt_id
    owners = r.owners
    total = sum((r.items[n].amount for n in savings), Decimal("0"))
    rows = {}
    with st.container(key=f"savings-box-{rid}"):
        st.html(f'<p class="tly-savings-head"><span>Savings</span><b>{usd(total)}</b></p>')
        head(["Saving", "Comes off", "Price", ""], SAVING_WIDTHS, f"head-s-{rid}")
        for n in savings:
            on = owners[n].item if owners[n] is not r.items[n] else "Whole order"
            rows[n] = saving_row(rid, n, r.items[n], on, can_drop)
    return rows


def photo_bands(r: Receipt) -> None:
    """Hovering a line shades its strip of the photo. One band per photo, moved by whichever row is hovered."""
    rid = r.receipt_id
    rules = [f".stMain:has(.st-key-line-{rid}-{n}:hover) .st-key-shot-{rid} [data-testid='stImage']::after "
             f"{{ top: {i.spot[0] * 100:.2f}%; height: {(i.spot[1] - i.spot[0]) * 100:.2f}%; "
             f"left: {i.spot[2] * 100:.2f}%; width: {(i.spot[3] - i.spot[2]) * 100:.2f}%; opacity: 1; }}"
             for n, i in enumerate(r.items) if i.spot]
    if rules:
        st.html(f"<style>{''.join(rules)}</style>")


def items_table(r: Receipt) -> tuple[list[LineItem | None], str]:
    """Draws the items, the left-out box and the savings box. Returns the lines as typed, in the receipt's order
    (None for a line whose boxes can't be read), and why the left-out ones are out."""
    rid = r.receipt_id
    can_drop = len(r.items) > 1
    bought = [n for n, i in enumerate(r.items) if i.price >= 0 and not i.returned]
    out = [n for n, i in enumerate(r.items) if i.price >= 0 and i.returned]
    savings = [n for n, i in enumerate(r.items) if i.price < 0]
    items: list[LineItem | None] = list(r.items)
    with st.container(key=f"grid-{rid}"):
        head(["Qty", "Item", "On receipt", "Price", "Category", "Leave out", ""], WIDTHS, f"head-{rid}")
        for n in bought:
            items[n] = bought_row(rid, n, r.items[n], can_drop)
        # Kevin's pick 10A: the last row of the table, right where the new line will show up
        st.button("Add an item the reader missed", icon=":material/add_circle:", type="tertiary",
                  key=f"add-line-{rid}", on_click=add_line, args=(rid,), width="stretch")
    why = left_out_box(r, out) if out else r.left_out_why
    if savings:
        for n, i in savings_box(r, savings, can_drop).items():
            items[n] = i
    photo_bands(r)
    return items, why
