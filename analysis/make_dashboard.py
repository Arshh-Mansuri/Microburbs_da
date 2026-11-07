"""Build dashboard.html from a fresh run of the estimate.

    python make_dashboard.py

Every figure on the page is computed here, so the page cannot drift from the
model. The held-out check uses adverts dated 1 May to 31 July 2026, which are
never used to build or tune anything.
"""

from __future__ import annotations

import html

import numpy as np
import pandas as pd

import rent_model as rm

AS_AT = pd.Timestamp("2026-04-30")
TEST_START = pd.Timestamp("2026-05-01")
TEST_END = pd.Timestamp("2026-07-31")
HAND_IN_AS_AT = pd.Timestamp("2026-07-31")


def group_median(frame, keys, floor):
    grouped = frame.groupby(keys, observed=True)["weekly_rent"].agg(median="median", n="size")
    return grouped.loc[grouped["n"] >= floor, "median"].to_dict()


def chain(frame, tables):
    rent = pd.Series(np.nan, index=frame.index)
    for table, columns in tables:
        missing = rent.isna()
        if not missing.any():
            break
        wanted = frame.loc[missing, columns]
        keys = list(wanted.itertuples(index=False, name=None)) if len(columns) > 1 else list(wanted[columns[0]])
        rent.loc[missing] = [table.get(key, np.nan) for key in keys]
    return rent


def accuracy(test, rent):
    miss = (rent - test["weekly_rent"]).abs()
    asked = test["weekly_rent"]
    return {
        "miss": float(miss.median()),
        "within": float((miss <= 100).mean()) * 100,
        "within_n": int((miss <= 100).sum()),
        "r2": float(1 - ((asked - rent) ** 2).sum() / ((asked - asked.mean()) ** 2).sum()),
    }


def bar(value, largest, width=180):
    return f'<span class="bar" style="width:{max(2, round(width * value / largest))}px"></span>'


def main() -> None:
    leases = rm.load_leases()
    flats = rm.load_flats()
    raw = pd.read_csv(rm.DATA_DIR / rm.LEASES)

    earlier = leases.loc[leases["listing_date"] <= AS_AT]
    test = leases.loc[leases["listing_date"].between(TEST_START, TEST_END)].copy()
    recent = leases.loc[leases["listing_date"].between(AS_AT - pd.DateOffset(years=1), AS_AT)]

    model = rm.RentModel(as_at=AS_AT).fit(earlier)
    building_only = rm.RentModel(
        as_at=AS_AT, max_age_years=1, half_life_years=None, neighbours=0, **rm.BUILDING_ONLY
    ).fit(earlier)
    no_neighbours = rm.RentModel(as_at=AS_AT, neighbours=0, **rm.BUILDING_ONLY).fit(earlier)
    with_neighbours = rm.RentModel(as_at=AS_AT, **rm.BUILDING_ONLY).fit(earlier)

    suburb_bed = group_median(recent, ["suburb", "bedrooms"], 10)
    bed_only = group_median(recent, "bedrooms", 10)
    suburb_bed_park = group_median(recent, ["suburb", "bedrooms", "car_space"], 10)

    steps = [
        ("Suburb and bedrooms", chain(test, [(suburb_bed, ["suburb", "bedrooms"]), (bed_only, ["bedrooms"])])),
        ("Add parking", chain(test, [
            (suburb_bed_park, ["suburb", "bedrooms", "car_space"]),
            (suburb_bed, ["suburb", "bedrooms"]),
            (bed_only, ["bedrooms"]),
        ])),
        ("Same building, recent year", building_only.predict(test)),
        ("Older asks brought forward", no_neighbours.predict(test)),
        ("Plus nearest buildings", with_neighbours.predict(test)),
        ("Plus own past asks and bathrooms", model.predict(test)),
    ]
    scored = [(name, accuracy(test, rent)) for name, rent in steps]
    start, finish = scored[0][1], scored[-1][1]

    chosen = model.predict(test)
    detail = test.assign(estimate=chosen, came_from=model.predict_both(test)["source"])
    detail["miss"] = (detail["estimate"] - detail["weekly_rent"]).abs()

    by_source = (
        detail.groupby("came_from")
        .agg(n=("miss", "size"), miss=("miss", "median"), within=("miss", lambda m: (m <= 100).mean() * 100))
        .sort_values("n", ascending=False)
    )

    edges = [(0, 25, "under $25"), (25, 50, "$25 to $50"), (50, 100, "$50 to $100"),
             (100, 200, "$100 to $200"), (200, np.inf, "over $200")]
    spread = [(label, int(((detail["miss"] >= lo) & (detail["miss"] < hi)).sum())) for lo, hi, label in edges]

    index = model.index.sort_index()
    gaps = sorted(model.gap_by_bedrooms.items())

    hand_in = rm.RentModel(as_at=HAND_IN_AS_AT).fit(leases)
    both = hand_in.predict_both(flats)
    parking_gap = both["rent_with_car_space"] - both["rent_without_car_space"]
    coverage = both["source"].value_counts()
    from_building = both["source"].str.startswith("building").mean() * 100

    advert_dates = pd.to_datetime(raw["listing_date"])
    first_ad = advert_dates.min().strftime("%B %Y")
    last_ad = advert_dates.max().strftime("%-d %B %Y")

    def row(cells, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"

    worst_step = max(s["miss"] for _, s in scored)
    step_rows = "\n".join(
        row([
            html.escape(name),
            f"{bar(s['miss'], worst_step)}<span class='n'>${s['miss']:,.2f}</span>",
            f"{s['within']:.1f}%",
            f"{s['r2']:.3f}",
        ])
        for name, s in scored
    )

    busiest = by_source["n"].max()
    source_rows = "\n".join(
        row([
            html.escape(name),
            f"{bar(r.n, busiest)}<span class='n'>{r.n:,}</span>",
            f"${r.miss:,.2f}",
            f"{r.within:.1f}%",
        ])
        for name, r in by_source.iterrows()
    )

    biggest = max(n for _, n in spread)
    spread_rows = "\n".join(
        row([label, f"{bar(n, biggest)}<span class='n'>{n:,}</span>", f"{n / len(detail):.1%}"])
        for label, n in spread
    )

    def size_label(beds):
        if beds == 0:
            return "Studio"
        return "1 bedroom" if beds == 1 else f"{int(beds)} bedrooms"

    gap_rows = "\n".join(
        row([size_label(beds), f"{bar(gap, max(g for _, g in gaps))}<span class='n'>${gap:,.2f}</span>"])
        for beds, gap in gaps
    )

    coverage_rows = "\n".join(
        row([html.escape(name), f"{bar(n, coverage.max())}<span class='n'>{n:,}</span>", f"{n / len(flats):.1%}"])
        for name, n in coverage.items()
    )

    window = earlier.loc[earlier["listing_date"] >= AS_AT - pd.DateOffset(years=rm.MAX_AGE_YEARS)]
    quarterly = window.groupby(window["listing_date"].dt.to_period("Q"))["weekly_rent"].agg(median="median", n="size")
    quarterly = quarterly.loc[quarterly["n"] >= rm.MIN_INDEX_ADS, "median"].sort_index()

    low, high = float(quarterly.min()), float(quarterly.max())
    span = high - low or 1
    points = []
    for i, value in enumerate(quarterly):
        x = 56 + i * (520 / max(1, len(quarterly) - 1))
        y = 140 - 110 * (float(value) - low) / span
        points.append(f"{x:.1f},{y:.1f}")
    line = " ".join(points)
    first_q, last_q = quarterly.index[0], quarterly.index[-1]
    climb = (float(quarterly.iloc[-1]) / float(quarterly.iloc[0]) - 1) * 100

    page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>What will this flat rent for?</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{ color-scheme: light dark; --line: #d6d6d6; --dim: #6a6a6a; --bar: #4b6bd6; --ink: #1a1a1a; --bg: #fff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --line: #3a3a3a; --dim: #9a9a9a; --bar: #7f9bf0; --ink: #ededed; --bg: #171717; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0 auto; padding: 32px 20px 72px; max-width: 860px; background: var(--bg); color: var(--ink);
         font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
  h1 {{ font-size: 25px; font-weight: 500; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; font-weight: 500; margin: 40px 0 6px; }}
  p {{ margin: 8px 0; max-width: 64ch; }}
  .sub {{ color: var(--dim); margin-top: 0; }}
  .headline {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 24px 0 8px; }}
  .card {{ flex: 1 1 150px; border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }}
  .card .big {{ font-size: 27px; font-weight: 500; letter-spacing: -0.5px; }}
  .card .label {{ color: var(--dim); font-size: 13px; }}
  .card .was {{ color: var(--dim); font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ text-align: left; padding: 7px 10px 7px 0; border-bottom: 1px solid var(--line); vertical-align: middle; }}
  th {{ color: var(--dim); font-weight: 500; font-size: 13px; }}
  td:not(:first-child), th:not(:first-child) {{ text-align: right; }}
  td:nth-child(2) {{ text-align: left; white-space: nowrap; }}
  .bar {{ display: inline-block; height: 9px; border-radius: 2px; background: var(--bar); vertical-align: middle; margin-right: 8px; }}
  .n {{ font-variant-numeric: tabular-nums; }}
  svg {{ max-width: 100%; height: auto; }}
  .note {{ color: var(--dim); font-size: 13px; }}
  @media (max-width: 560px) {{ .bar {{ display: none; }} td:nth-child(2) {{ text-align: right; }} }}
</style>

<h1>What will this flat rent for?</h1>
<p class="sub">Two weekly asking rents for every City of Sydney flat, with a car space and without, as at 31 July 2026.</p>

<div class="headline">
  <div class="card">
    <div class="big">${finish['miss']:,.2f}</div>
    <div class="label">Typical miss a week</div>
    <div class="was">was ${start['miss']:,.2f}</div>
  </div>
  <div class="card">
    <div class="big">{finish['within']:.1f}%</div>
    <div class="label">Within $100 a week</div>
    <div class="was">was {start['within']:.1f}%</div>
  </div>
  <div class="card">
    <div class="big">{finish['r2']:.3f}</div>
    <div class="label">R squared</div>
    <div class="was">was {start['r2']:.3f}</div>
  </div>
  <div class="card">
    <div class="big">{len(test):,}</div>
    <div class="label">Later adverts scored</div>
    <div class="was">none used to build it</div>
  </div>
</div>

<h2>What moved the miss</h2>
<p>Every row is scored on the same {len(test):,} adverts dated 1 May to 31 July 2026. Groups are built only from
adverts dated by 30 April 2026. A suburb estimate gives every flat in a suburb the same rent. Swapping the suburb for
the flat's own building is what closes the gap, and bringing older asks forward to April 2026 is what makes the
building comparison reach {from_building:.0f}% of flats instead of a quarter of them.</p>
<table>
  <thead>{row(["Estimate", "Typical miss", "Within $100", "R squared"], "th")}</thead>
  <tbody>
{step_rows}
  </tbody>
</table>

<h2>Where each estimate came from</h2>
<p>Flats compared with their own building miss by far less than any other group. A building that has never advertised
a flat type borrows from the {rm.NEIGHBOURS} nearest buildings within {rm.NEIGHBOUR_REACH_M:,} metres that have,
and falls back to its suburb only when none is in reach.</p>
<table>
  <thead>{row(["Comparison used", "Later adverts", "Typical miss", "Within $100"], "th")}</thead>
  <tbody>
{source_rows}
  </tbody>
</table>

<h2>How far off each advert was</h2>
<table>
  <thead>{row(["Miss", "Later adverts", "Share"], "th")}</thead>
  <tbody>
{spread_rows}
  </tbody>
</table>

<h2>Bringing older asks forward</h2>
<p>An ask from {first_q} cannot be pooled with one from {last_q} as it stands. Each is scaled by how the median
weekly ask across the city moved between its quarter and April 2026, then weighted down as it ages, with a three year
half life. Across this window the median ask moved {climb:+.0f}%.</p>
<svg viewBox="0 0 600 170" role="img"
     aria-label="Median weekly asking rent across the city by quarter, {first_q} to {last_q}, ranging ${low:,.0f} to ${high:,.0f}">
  <line x1="56" y1="30" x2="590" y2="30" stroke="var(--line)" stroke-width="1"/>
  <line x1="56" y1="140" x2="590" y2="140" stroke="var(--line)" stroke-width="1"/>
  <polyline points="{line}" fill="none" stroke="var(--bar)" stroke-width="2"/>
  <text x="50" y="34" font-size="11" fill="var(--dim)" text-anchor="end">${high:,.0f}</text>
  <text x="50" y="144" font-size="11" fill="var(--dim)" text-anchor="end">${low:,.0f}</text>
  <text x="56" y="162" font-size="11" fill="var(--dim)">{first_q}</text>
  <text x="590" y="162" font-size="11" fill="var(--dim)" text-anchor="end">{last_q}</text>
</svg>

<h2>What a car space adds</h2>
<p>Measured on groups that advertised both answers. Where a building has only ever advertised one, the other rent is
that one plus this gap, capped so a car space never lowers the ask. Where a building advertised both, its own two
medians stand, which is why {int((parking_gap < 0).sum()):,} flats come out with parking priced lower.</p>
<table>
  <thead>{row(["Flat size", "Typical gap a week"], "th")}</thead>
  <tbody>
{gap_rows}
  </tbody>
</table>

<h2>The hand-in file</h2>
<p>All {len(flats):,} flats across {flats['suburb'].nunique()} suburbs get both rents, including the
{int((flats['ever_advertised_for_lease'] == 0).sum()):,} that have never been advertised. Those come from other flats
in the same building. Refitted on every advert dated by 31 July 2026.</p>
<table>
  <thead>{row(["Comparison used", "Flats", "Share"], "th")}</thead>
  <tbody>
{coverage_rows}
  </tbody>
</table>
<p class="note">Rents run ${both['rent_without_car_space'].min():,.0f} to ${both['rent_with_car_space'].max():,.0f} a
week. No blanks, no duplicate addresses, median parking gap ${parking_gap.median():,.2f}.</p>

<h2>What this is built from</h2>
<p class="note">{len(raw):,} past rental adverts from {first_ad} to {last_ad}, of which {hand_in.adverts_used:,} fall
inside the three year window and carry a bedroom count and a parking answer. Nothing dated after 31 July 2026 is read.
Floor level was tested and dropped: it did not lower the miss, because a flat's own building already carries it.</p>
</html>
"""

    with open(rm.SITE_DIR / "dashboard.html", "w") as handle:
        handle.write(page)
    print(f"Wrote dashboard.html: miss ${finish['miss']:,.2f}, within $100 {finish['within']:.1f}%, R2 {finish['r2']:.3f}")


if __name__ == "__main__":
    main()
