"""Step 3: add the event's income, see the totals, and push approved receipts to the books."""
from __future__ import annotations

import itertools
import time
from decimal import Decimal

import pandas as pd
import streamlit as st

from treasurer.checks import Severity, run_checks
from treasurer.models import Receipt, Status
from treasurer.post import TX_FIELDS, event_totals
from treasurer.reader import make_extractor
from treasurer.runlog import log_run, minutes, read_runs
from treasurer.sheets import DEFAULT_SOURCES, EventInfo, local_transactions, local_views
from treasurer.views import grid_to_csv
from treasurer.xlsx_export import book_xlsx
from ui import connect, done_card
from ui.common import RUN_LOG, dec, get_sink, go, guide, html_table, loading, md, money_panel, saved_reimbursements, ss, step_bar, usd

INCOME_CHOICES = ["Zelle", "Venmo", "Cash", "Card / Square", "Ticket sales", "Dues", "Sponsorship",
                  "Grants and funding", "Donations", "Fundraiser", "Other"]
SOURCE_ICONS = {"zelle": "phone_iphone", "venmo": "phone_iphone", "cash app": "phone_iphone", "cash": "payments",
                "card": "credit_card", "square": "credit_card", "ticket": "confirmation_number", "dues": "badge",
                "sponsor": "handshake", "grant": "account_balance", "fund": "account_balance",
                "donation": "volunteer_activism", "fundraiser": "storefront", "bake": "storefront"}


def sources() -> list[str]:
    return [x.strip() for x in ss.event.get("sources", ", ".join(DEFAULT_SOURCES)).split(",") if x.strip()]


def set_sources(names: list[str]) -> None:
    ss.event = {**ss.event, "sources": ", ".join(names)}


def rename_source(old: str) -> None:
    """Dropdown callback: swap a source for another one (or a new name typed in), keeping its amount."""
    new = str(ss.get(f"src-{old}") or "").strip().replace(",", " ")
    names = sources()
    if not new or new == old or new in names:
        ss[f"src-{old}"] = old
        return
    names[names.index(old)] = new
    set_sources(names)
    ss.income = {(new if k == old else k): v for k, v in ss.income.items()}
    if f"income-{old}" in ss:
        ss[f"income-{new}"] = ss[f"income-{old}"]


def remove_source(name: str) -> None:
    set_sources([x for x in sources() if x != name])
    ss.income.pop(name, None)
    ss.pop(f"income-{name}", None)


def add_source() -> None:
    names = sources()
    spares = itertools.chain(INCOME_CHOICES, (f"Other {n}" for n in itertools.count(2)))
    set_sources([*names, next(c for c in spares if c not in names)])


def income_box() -> dict[str, Decimal]:
    """One row per income source: icon, source dropdown, amount, remove. Returns the amounts."""
    names = list(dict.fromkeys(sources())) or list(DEFAULT_SOURCES)
    income = {}
    with st.container(border=True, key="income-box"):
        head = st.columns([0.45, 3, 2, 0.5])
        head[1].markdown('<p class="tly-colhead">Where it came from</p>', unsafe_allow_html=True)
        head[2].markdown('<p class="tly-colhead">Amount ($)</p>', unsafe_allow_html=True)
        for n, k in enumerate(names):
            row = st.columns([0.45, 3, 2, 0.5], vertical_alignment="center")
            icon = next((v for word, v in SOURCE_ICONS.items() if word in k.lower()), "savings")
            with row[0].container(key=f"srcicon-{n % 4}-{n}"):
                st.markdown(f":material/{icon}:")
            row[1].selectbox("Source", [k, *[c for c in INCOME_CHOICES if c not in names]], key=f"src-{k}",
                             label_visibility="collapsed", accept_new_options=True, on_change=rename_source, args=(k,))
            start = ss.income.get(k, "")
            income[k] = dec(row[2].text_input(k, "" if dec(start) == 0 else start, key=f"income-{k}",
                                              placeholder="0.00", label_visibility="collapsed"))
            row[3].button("", icon=":material/remove:", key=f"rm-{k}", help=f"Remove {k}",
                          on_click=remove_source, args=(k,), disabled=len(names) == 1)
        foot = st.columns([3.45, 2.5], vertical_alignment="center")
        foot[0].button("Add a source", icon=":material/add:", key="add-source", on_click=add_source)
        foot[1].markdown(f'<p class="tly-intotal">Total in <b>{usd(sum(income.values(), Decimal("0")))}</b></p>',
                         unsafe_allow_html=True)
    ss.income = {k: str(v) for k, v in income.items()}
    for k in names:
        typed = str(ss.get(f"income-{k}", "")).strip()
        if typed and dec(typed, "-1") != dec(typed, "1"):  # unreadable: dec fell back to its default
            st.warning(md(f"{k}: '{typed}' isn't an amount, so it counts as $0. Type a number like 120.00."))
        elif income[k] < 0:
            st.warning(md(f"{k} is negative ({usd(income[k])}). Refunds you paid out belong on a receipt, not in income."))
    return income


def metrics(receipts: list[Receipt], income: dict[str, Decimal]) -> None:
    t = event_totals(receipts, income)
    target = int(ss.event.get("target", 10))
    with st.container(key="sum-metrics"):
        m = st.columns(4)
        m[0].metric("Income", usd(t["income"]), border=True)
        m[1].metric("Expenses (approved)", usd(t["expenses"]), border=True)
        m[2].metric("Net", usd(t["net"]), border=True,
                    delta=("left over" if t["net"] >= 0 else "short") if t["income"] or t["expenses"] else None,
                    delta_color="normal" if t["net"] >= 0 else "inverse", delta_arrow="off")
        hit = t["margin_pct"] >= target
        m[3].metric("Margin", f"{t['margin_pct']}%", help=f"Your target: {target}% or more (change it under Edit event)",
                    border=True, delta="on target" if hit else f"under {target}% target",
                    delta_color="normal" if hit else "inverse", delta_arrow="off")


def push(sink, receipts: list[Receipt], event: EventInfo, income: dict[str, Decimal]) -> None:
    """Write to the books, mark what's in them as posted, and log the run."""
    pushing = st.empty()
    loading(pushing, f"Tally is writing to {sink.label}", f"{len(receipts)} receipts, plus the event's income", None,
            pose="tally-ledger.png")
    try:
        written = sink.post(receipts, event, income)
    except Exception as e:  # network drop, sheet unshared mid-push, quota
        pushing.empty()
        why = (getattr(e, "error", None) or {}).get("message") or str(e)  # Google's words, without "APIError: [400]"
        st.error(f"The push stopped partway. Google said: {why.rstrip('.')}. Nothing is double-counted: "
                 "click Push again and receipts already written are skipped.")
        return
    pushing.empty()
    ss.format_errors = getattr(sink, "format_errors", [])
    # Every approved receipt is in the books now: just written, or already there from an
    # earlier push (a resumed session, or a second browser tab).
    for rid, rec in list(ss.receipts.items()):
        if rec.status is Status.APPROVED:
            ss.receipts[rid] = rec.model_copy(update={"status": Status.POSTED})
    if written:
        now, flags = time.time(), run_checks(receipts)
        ex, reader = make_extractor()
        log_run(RUN_LOG, {
            "event_id": event.event_id, "reader": reader, "model": getattr(ex, "model", "stub"),
            "receipts": len(receipts), "posted": len(written), "edits": ss.edits,
            "overrides": sum(1 for r in receipts if r.review_note and r.status is not Status.REJECTED
                             and any(f.severity is Severity.BLOCK for f in flags[r.receipt_id])),
            "minutes_draft_to_push": minutes(ss.drafted_at, now),
            "minutes_review_to_push": minutes(ss.review_started, now),
        })
    done_card.mark_pushed()
    st.rerun()  # redraw the table and step bar with the posted status


def excel_button(views: dict, receipts: list[Receipt], event: EventInfo, label: str, key: str, **kw) -> bool:
    """The whole book as one Excel file, built on click. True on the rerun after a click."""
    return st.download_button(label, icon=":material/download:", key=key, **kw,
                              data=lambda: book_xlsx(views, local_transactions(receipts), TX_FIELDS),
                              file_name=f"{event.event_id}_books.xlsx",
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def csv_downloads(views: dict, event: EventInfo) -> None:
    with st.expander("Or one report at a time (CSV)"):
        cols = st.columns(len(views))
        for col, (title, view) in zip(cols, views.items(), strict=True):
            col.download_button(title, grid_to_csv(view.grid), file_name=f"{event.event_id}_{title.replace(' ', '_')}.csv",
                                mime="text/csv", key=f"dl-{title}")


def books_row(sink, receipts: list[Receipt], event: EventInfo, income: dict[str, Decimal], views: dict, waiting: list) -> None:
    """Push to Google Sheets and/or get the Excel file. Whichever is done first, Close out becomes the green button."""
    done = bool(ss.event.get("pushed_at") or ss.event.get("excel_at"))
    kind = "secondary" if done else "primary"
    with st.container(horizontal=True, key="push-row"):
        if sink.label == "Google Sheets":
            if st.button("Push to Google Sheets", type=kind, disabled=bool(waiting), icon=":material/upload:"):
                push(sink, receipts, event, income)
            if views and excel_button(views, receipts, event, "Download as Excel", "dl-xlsx-row"):
                ss.event = {**ss.event, "excel_at": time.strftime("%I:%M %p").lstrip("0")}
                st.rerun()
        elif views and excel_button(views, receipts, event, "Save and get Excel", "dl-xlsx-row", type=kind,
                                    disabled=bool(waiting)):
            push(sink, receipts, event, income)  # without Sheets, saving the books is the push
    if not done and not waiting:  # pushing is optional: a club can go straight on
        with st.container(border=True, key="next-card"):
            c = st.columns([4, 1.3], vertical_alignment="center")
            c[0].markdown("**Books sorted?** Next up - pay back whoever fronted the money!")
            c[1].button("Next: Close out", icon=":material/arrow_forward:", icon_position="right", width="stretch",
                        on_click=go, args=("4. Close out",), key="skip-to-closeout")


def show(event: EventInfo) -> None:
    st.header("Summary and push")
    step_bar("3. Summary")
    receipts = list(ss.receipts.values())
    if not receipts:
        guide("Nothing to sum up yet!", "Upload and check your receipts first, then I'll add them up here.",
              key="summary-empty", to="1. Upload")
        return
    st.subheader("Income")
    st.caption("Add what came in. I already counted what went out from your receipts.")
    income = income_box()
    metrics(receipts, income)
    with st.container(border=True):
        st.markdown("**Money in vs out**")
        money_panel(receipts, income)

    with st.expander(f"See all {len(receipts)} receipts"):  # folded, so the books button isn't a long scroll away
        html_table([{"Receipt": r.receipt_id, "Place": r.place, "Payer": r.payer or "(none)", "Status": r.status,
                     "Posts": usd(r.posted_amount) if r.counts else "",
                     "Note": r.review_note or ""} for r in receipts], numeric=("Posts",))

    waiting = [r.receipt_id for r in receipts if r.status is Status.DRAFTED]
    if waiting:
        st.warning(f"Review these first: {', '.join(waiting)}")
    sink, err = get_sink()
    if err:
        st.error(err)
    if sink.label != "Google Sheets":
        with st.expander("Connect Google Sheets (optional - otherwise your books come out as an Excel file)",
                         icon=":material/link:", expanded=not err):
            connect.box("summary")
    views = local_views(receipts, event, income, saved_reimbursements(sink)) if any(r.counts for r in receipts) else {}
    books_row(sink, receipts, event, income, views, waiting)
    done_card.show(sink, receipts, event, income, lambda: push(sink, receipts, event, income))
    if views:
        csv_downloads(views, event)

    st.subheader("Run stats")
    s = st.columns(3)
    s[0].metric("Minutes in tool", f"{(time.time() - ss.started) / 60:.1f}")
    s[1].metric("Edits to drafts", ss.edits)
    s[2].metric("Flags open", sum(1 for fl in run_checks(receipts).values() for f in fl if f.severity is Severity.BLOCK))
    runs = read_runs(RUN_LOG)
    if runs:
        st.caption(f"Past runs, from {RUN_LOG}")
        st.dataframe(pd.DataFrame(runs), width="stretch", hide_index=True)
