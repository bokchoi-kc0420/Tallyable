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
    loading(pushing, f"Tally is writing to {sink.label}", f"{len(receipts)} receipts, plus the event's income", None)
    try:
        written = sink.post(receipts, event, income)
    except Exception as e:  # network drop, sheet unshared mid-push, quota
        pushing.empty()
        st.error(f"The push stopped partway: {e}. Nothing is double-counted: click Push again and "
                 "receipts already written are skipped.")
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
    ss.last_push = (f"**Pushed {len(written)} receipts to {sink.label}!**" if written
                    else "**Already up to date.** Every approved receipt is in the books.")
    st.rerun()  # redraw the table and step bar with the posted status


def downloads(sink, receipts: list[Receipt], event: EventInfo, income: dict[str, Decimal]) -> None:
    """The books as one Excel file, or one CSV per report."""
    on_sheets = sink.label == "Google Sheets"
    # With Google Sheets connected the books are already there, so the Excel copy is tucked away:
    # it must never look like the next step after Push.
    with st.expander("Download a copy instead (Excel)") if on_sheets else st.container():
        if not on_sheets:
            st.subheader("Download the books")
        st.caption("Every report in one formatted Excel file, for approved receipts. Open it in Excel, or bring "
                   "it into your own Google Sheet with File > Import. No sharing needed.")
        views = local_views(receipts, event, income, saved_reimbursements(sink))
        st.download_button("Download the whole book (Excel)", type="secondary" if on_sheets else "primary",
                           icon=":material/download:", data=book_xlsx(views, local_transactions(receipts), TX_FIELDS),
                           file_name=f"{event.event_id}_books.xlsx", key="dl-xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with st.expander("Or one report at a time (CSV)"):
        cols = st.columns(len(views))
        for col, (title, view) in zip(cols, views.items(), strict=True):
            col.download_button(title, grid_to_csv(view.grid), file_name=f"{event.event_id}_{title.replace(' ', '_')}.csv",
                                mime="text/csv", key=f"dl-{title}")


def show(event: EventInfo) -> None:
    st.header("Summary and push")
    step_bar("3. Summary")
    receipts = list(ss.receipts.values())
    if not receipts:
        guide("Nothing to sum up yet!", "Upload and check your receipts first, then I'll add them up here.",
              key="summary-empty", to="1. Upload")
        return
    st.subheader("Income")
    st.caption("Money that came in for this event. Expenses come from the receipts you approved.")
    income = income_box()
    metrics(receipts, income)
    with st.container(border=True):
        st.markdown("**Money in vs out**")
        money_panel(receipts, income)

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
        st.caption("Google Sheets isn't connected, so Push saves the books on this computer.")
    if st.button(f"Push to {sink.label}", type="primary", disabled=bool(waiting), icon=":material/upload:"):
        push(sink, receipts, event, income)
    url = getattr(sink, "url", None)
    if ss.get("last_push") and not any(r.status is Status.APPROVED for r in ss.receipts.values()):
        with st.container(border=True, key="after-push"):
            c = st.columns([2.6, 1.3, 1.4], vertical_alignment="center")
            c[0].markdown(md(ss.last_push + " Next, see who's owed money and check the funder's rules."))
            if url:
                c[1].link_button("Open the sheet", url, icon=":material/open_in_new:", width="stretch")
            c[2].button("Go to Close out →", type="primary", on_click=go, args=("4. Close out",), key="to-closeout",
                        width="stretch")
        if ss.get("format_errors"):
            st.warning(md("Your numbers are in the sheet, but Google wouldn't apply the colors and layout on: "
                          + "; ".join(ss.format_errors) + ". Send this to whoever set up Tallyable."))

    if any(r.counts for r in receipts):
        downloads(sink, receipts, event, income)

    st.subheader("Run stats")
    s = st.columns(3)
    s[0].metric("Minutes in tool", f"{(time.time() - ss.started) / 60:.1f}")
    s[1].metric("Edits to drafts", ss.edits)
    s[2].metric("Flags open", sum(1 for fl in run_checks(receipts).values() for f in fl if f.severity is Severity.BLOCK))
    runs = read_runs(RUN_LOG)
    if runs:
        st.caption(f"Past runs, from {RUN_LOG}")
        st.dataframe(pd.DataFrame(runs), width="stretch", hide_index=True)
