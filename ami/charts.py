"""Charts (Altair). Colours follow the job they do: categorical slots in a fixed order, one hue for magnitude.

The slots lead with the AMI brand: navy #000080 and amber #FDA50F, stepped into the lightness band where a thin mark still
reads on white (#1945b8, #f09c0b), then green, magenta, violet, red. The order was validated for colour-vision deficiency
(worst adjacent pair CVD delta-E 15.2, all pairs of the first four >= 15). Amber and magenta sit below 3:1 contrast on white,
so every chart names its series in a legend and on hover and has a data table under it."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

SERIES = ["#1945b8", "#f09c0b", "#008300", "#e87ba4", "#6250d6", "#e34948"]
PROFIT, LOSS = "#1945b8", "#e34948"  # polarity: brand blue vs red
INK, MUTED, GRID = "#161A3A", "#52546E", "#E6E8F0"


def _numbers(table: pd.DataFrame, note: str | None, show: bool = True):
    """Caption, then the exact figures behind the chart (relief for the lighter slots, and what a finance reader wants).
    show=False when the page already prints the same figures in a table right below."""
    if note:
        st.caption(note)
    if not show:
        return
    with st.expander("Data table", icon=":material/table:"):
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="localized") for c in table.columns if c != "Month"})


def _axis_money(title=None):
    return alt.Axis(title=title, format="~s", labelExpr="replace(datum.label, 'G', 'bn')", grid=True, gridColor=GRID,
                    domain=False, tickColor=GRID, labelColor=MUTED, titleColor=MUTED)


def _x_month():
    return alt.X("month:O", title=None, sort=None, axis=alt.Axis(labelAngle=0, labelColor=MUTED, domain=False, ticks=False))


def lines(frame: pd.DataFrame, series: list[str], labels: list[str], title: str, height: int = 260, note: str | None = None,
          table: bool = True):
    """Several money series over months (one axis). frame has a 'month' label column in display order."""
    long = frame.melt(id_vars=["month"], value_vars=series, var_name="series", value_name="amount")
    names = dict(zip(series, labels))
    long["series"] = long["series"].map(names)
    order = list(frame["month"])
    base = alt.Chart(long).encode(
        x=alt.X("month:O", sort=order, title=None, axis=alt.Axis(labelAngle=0, labelColor=MUTED, domain=False, ticks=False)),
        y=alt.Y("amount:Q", axis=_axis_money()),
        color=alt.Color("series:N", sort=labels, scale=alt.Scale(domain=labels, range=SERIES[: len(labels)]),
                        legend=alt.Legend(orient="top", title=None, labelColor=INK)),
        tooltip=[alt.Tooltip("month:O", title="Month"), alt.Tooltip("series:N", title="Series"),
                 alt.Tooltip("amount:Q", title="Amount (VND)", format=",.0f")])
    chart = (base.mark_line(strokeWidth=2) + base.mark_point(size=60, filled=True)).properties(height=height, title=title)
    st.altair_chart(chart.configure_view(stroke=None).configure_title(anchor="start", color=INK, fontSize=14), width="stretch")
    _numbers(frame[["month", *series]].rename(columns={"month": "Month", **names}), note, table)


def bars(frame: pd.DataFrame, value: str, title: str, height: int = 240, signed: bool = False, note: str | None = None):
    """One money series by month. signed=True colours losses differently (polarity), labelled in the tooltip."""
    order = list(frame["month"])
    enc = dict(x=alt.X("month:O", sort=order, title=None, axis=alt.Axis(labelAngle=0, labelColor=MUTED, domain=False, ticks=False)),
               y=alt.Y(f"{value}:Q", axis=_axis_money()),
               tooltip=[alt.Tooltip("month:O", title="Month"), alt.Tooltip(f"{value}:Q", title="Amount (VND)", format=",.0f")])
    if signed:
        frame = frame.assign(result=frame[value].map(lambda v: "Profit" if v >= 0 else "Loss"))
        enc["color"] = alt.Color("result:N", scale=alt.Scale(domain=["Profit", "Loss"], range=[PROFIT, LOSS]),
                                 legend=alt.Legend(orient="top", title=None))
        enc["tooltip"].append(alt.Tooltip("result:N", title="Result"))
    else:
        enc["color"] = alt.value(SERIES[0])
    chart = alt.Chart(frame).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=18).encode(**enc)
    rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=MUTED, strokeWidth=1).encode(y="y:Q")
    st.altair_chart((chart + rule).properties(height=height, title=title).configure_view(stroke=None)
                    .configure_title(anchor="start", color=INK, fontSize=14), width="stretch")
    _numbers(frame[["month", value]].rename(columns={"month": "Month", value: "Amount (VND)"}), note)


def grouped(frame: pd.DataFrame, category: str, value: str, title: str, categories: list[str], height: int = 260,
            note: str | None = None):
    """Money by month split by a small set of categories (at most 4), side by side."""
    order = list(dict.fromkeys(frame["month"]))
    chart = alt.Chart(frame).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("month:O", sort=order, title=None, axis=alt.Axis(labelAngle=0, labelColor=MUTED, domain=False, ticks=False)),
        xOffset=alt.XOffset(f"{category}:N", sort=categories),
        y=alt.Y(f"{value}:Q", axis=_axis_money()),
        color=alt.Color(f"{category}:N", sort=categories, scale=alt.Scale(domain=categories, range=SERIES[: len(categories)]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("month:O", title="Month"), alt.Tooltip(f"{category}:N", title="Programme"),
                 alt.Tooltip(f"{value}:Q", title="Amount (VND)", format=",.0f")])
    st.altair_chart(chart.properties(height=height, title=title).configure_view(stroke=None)
                    .configure_title(anchor="start", color=INK, fontSize=14), width="stretch")
    wide = (frame.pivot_table(index="month", columns=category, values=value, aggfunc="sum", fill_value=0)
            .reindex(index=order, columns=categories).reset_index().rename(columns={"month": "Month"}))
    wide.columns.name = None
    _numbers(wide, note)
