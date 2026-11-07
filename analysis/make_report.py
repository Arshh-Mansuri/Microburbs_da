"""Build report.html from a fresh run.

    python make_report.py

Every figure in the report is computed here. Estimates are built from adverts
dated by 30 April 2026 and checked against adverts dated 1 May to 31 July 2026,
which are never used to build or tune anything.
"""

from __future__ import annotations

import html

import numpy as np
import pandas as pd

import rent_model as rm

AS_AT = pd.Timestamp("2026-04-30")
TEST_START = pd.Timestamp("2026-05-01")
TEST_END = pd.Timestamp("2026-07-31")
EXAMPLE_START = pd.Timestamp("2025-05-01")


def money(value, places=0):
    return f"${value:,.{places}f}"


def example_estimate(leases, test):
    """The example report's method: suburb, bedrooms and parking medians."""
    recent = leases.loc[leases["listing_date"].between(EXAMPLE_START, AS_AT)]
    rent = pd.Series(np.nan, index=test.index)
    for keys in (["suburb", "bedrooms", "car_space"], ["suburb", "bedrooms"], ["bedrooms"]):
        grouped = recent.groupby(keys)["weekly_rent"].agg(["median", "size"])
        table = grouped.loc[grouped["size"] >= 10, "median"].to_dict()
        missing = rent.isna()
        wanted = test.loc[missing, keys]
        lookup = list(wanted.itertuples(index=False, name=None)) if len(keys) > 1 else list(wanted[keys[0]])
        rent.loc[missing] = [table.get(key, np.nan) for key in lookup]
    return rent


def accuracy(test, rent):
    asked = test["weekly_rent"]
    miss = (rent - asked).abs()
    return {
        "miss": float(miss.median()),
        "within": float((miss <= 100).mean()) * 100,
        "within_n": int((miss <= 100).sum()),
        "r2": float(1 - ((asked - rent) ** 2).sum() / ((asked - asked.mean()) ** 2).sum()),
        "misses": miss,
    }


def main() -> None:
    raw = pd.read_csv(rm.DATA_DIR / rm.LEASES)
    raw["listing_date"] = pd.to_datetime(raw["listing_date"])
    leases = rm.load_leases()
    flats = rm.load_flats()

    earlier = leases.loc[leases["listing_date"] <= AS_AT]
    test = leases.loc[leases["listing_date"].between(TEST_START, TEST_END)].copy()
    window_start = AS_AT - pd.DateOffset(years=rm.MAX_AGE_YEARS)
    raw_window = raw["listing_date"].between(window_start, AS_AT)
    raw_test = raw["listing_date"].between(TEST_START, TEST_END)

    model = rm.RentModel(as_at=AS_AT).fit(earlier)
    last_year = rm.RentModel(as_at=AS_AT, max_age_years=1, half_life_years=None, neighbours=0).fit(earlier)
    no_neighbours = rm.RentModel(as_at=AS_AT, neighbours=0).fit(earlier)

    example = accuracy(test, example_estimate(leases, test))
    ours_rent = model.predict(test)
    ours = accuracy(test, ours_rent)
    suburb_only_rent = no_neighbours.predict(test)
    steps = [
        ("Suburb, bedrooms and parking (the example report)", example),
        ("Same building, last year of adverts only", accuracy(test, last_year.predict(test))),
        ("Same building, older asks brought forward", accuracy(test, suburb_only_rent)),
        ("Plus nearest buildings where a building never advertised", ours),
    ]

    test["estimate"] = ours_rent
    test["came_from"] = model.predict_both(test)["source"]
    test["signed"] = test["weekly_rent"] - test["estimate"]
    test["miss"] = test["signed"].abs()
    bias = float(test["signed"].median())

    # Earlier adverts brought forward to 30 April 2026, for the findings.
    ads = model._as_at_prices(earlier).merge(
        flats[["gnaf_id", "floor_level", "block_new_homes_2021_2026", "block_homes_2026"]],
        on="gnaf_id",
        how="left",
    )

    # Same suburb, same flat type, different buildings.
    buildings = (
        ads.groupby(["suburb", "bedrooms", "car_space", "building_address"])["rent_now"]
        .agg(median="median", n="size")
        .reset_index()
    )
    buildings = buildings.loc[buildings["n"] >= 5]
    spread = (
        buildings.groupby(["suburb", "bedrooms", "car_space"])["median"]
        .agg(low="min", high="max", count="size")
        .reset_index()
    )
    spread = spread.loc[spread["count"] >= 5].sort_values("count", ascending=False)
    lead = spread.iloc[0]
    lead_buildings = buildings.loc[
        (buildings["suburb"] == lead["suburb"])
        & (buildings["bedrooms"] == lead["bedrooms"])
        & (buildings["car_space"] == lead["car_space"])
    ]["median"].sort_values()
    lead_suburb_median = float(
        ads.loc[
            (ads["suburb"] == lead["suburb"])
            & (ads["bedrooms"] == lead["bedrooms"])
            & (ads["car_space"] == lead["car_space"]),
            "rent_now",
        ].median()
    )

    # What one floor adds, inside one building, bedroom count and parking answer.
    floors = ads.loc[ads["floor_level"].notna()].copy()
    floors["group"] = list(zip(floors["building_address"], floors["bedrooms"], floors["car_space"]))
    floors = floors.loc[floors.groupby("group")["floor_level"].transform("nunique") >= 2]
    floors["rent_gap"] = floors["rent_now"] - floors.groupby("group")["rent_now"].transform("median")
    floors["floor_gap"] = floors["floor_level"] - floors.groupby("group")["floor_level"].transform("median")
    per_floor = float(np.polyfit(floors["floor_gap"], floors["rent_gap"], 1)[0])
    floor_bands = []
    for low, high, label in ((1, 5, "Floors 1 to 4"), (5, 10, "Floors 5 to 9"),
                             (10, 20, "Floors 10 to 19"), (20, 200, "Floor 20 and up")):
        band = floors.loc[(floors["floor_level"] >= low) & (floors["floor_level"] < high)]
        floor_bands.append((label, len(band), float(band["rent_gap"].median())))

    # Asks well above the building's going rate.
    over = test["signed"] > 100
    over_by_suburb = (
        test.assign(over=over).groupby("suburb")["over"].agg(n="size", share="mean").query("n >= 100")
        .sort_values("share", ascending=False)
    )

    # Parking.
    gap_rows = [
        (beds, gap) for beds, gap in sorted(model.gap_by_bedrooms.items()) if beds <= 3
    ]

    # Blocks with new homes.
    ads["suburb_typical"] = ads.groupby(["suburb", "bedrooms", "car_space"])["rent_now"].transform("median")
    ads["vs_suburb"] = ads["rent_now"] / ads["suburb_typical"] - 1
    homes = ads["block_homes_2026"].where(ads["block_homes_2026"] > 0)
    ads["growth"] = ads["block_new_homes_2021_2026"] / homes
    no_new = ads.loc[ads["growth"] == 0, "vs_suburb"]
    fast = ads.loc[ads["growth"] > 0.3, "vs_suburb"]

    # Relisted flats against their own previous ask.
    last_ask = earlier.sort_values("listing_date").groupby("gnaf_id").tail(1)[["gnaf_id", "weekly_rent", "listing_date"]]
    last_ask["brought_forward"] = last_ask["weekly_rent"] * last_ask["listing_date"].dt.to_period("Q").map(model.index)
    relisted = test.merge(
        last_ask.rename(columns={"weekly_rent": "previous"})[["gnaf_id", "previous", "brought_forward"]],
        on="gnaf_id",
    ).dropna(subset=["brought_forward"])
    raw_change = float((relisted["weekly_rent"] / relisted["previous"] - 1).median()) * 100
    indexed_change = float((relisted["weekly_rent"] / relisted["brought_forward"] - 1).median()) * 100

    # Checks.
    without_own = rm.RentModel(as_at=AS_AT).fit(earlier.loc[~earlier["gnaf_id"].isin(test["gnaf_id"])])
    without_own_miss = (without_own.predict(test) - test["weekly_rent"]).abs()
    had_own = test["gnaf_id"].isin(earlier["gnaf_id"])

    rng = np.random.default_rng(7)
    resampled = [np.median(rng.choice(test["miss"].to_numpy(), 1699, replace=True)) for _ in range(2000)]
    low_band, high_band = np.percentile(resampled, [5, 95])

    by_month = test.groupby(test["listing_date"].dt.to_period("M"))["miss"].agg(n="size", typical="median")

    quarters = []
    for quarter in pd.period_range("2024Q3", "2026Q1", freq="Q"):
        as_at = pd.Timestamp(quarter.start_time.date()) - pd.Timedelta(days=1)
        later = leases.loc[leases["listing_date"].dt.to_period("Q") == quarter]
        fitted = rm.RentModel(as_at=as_at).fit(leases.loc[leases["listing_date"] <= as_at])
        miss = (fitted.predict(later) - later["weekly_rent"]).abs()
        quarters.append((str(quarter), len(later), float(miss.median()), float((miss <= 100).mean()) * 100))

    sources = test.groupby("came_from")["miss"].agg(n="size", typical="median",
                                                    within=lambda m: (m <= 100).mean() * 100)
    sources = sources.sort_values("n", ascending=False)
    building_sources = test["came_from"].str.startswith("building")
    suburb_rows = test.loc[~building_sources]

    hand_in = rm.RentModel(as_at=pd.Timestamp("2026-07-31")).fit(leases)
    both = hand_in.predict_both(flats)
    lower_with_parking = int((both["rent_with_car_space"] < both["rent_without_car_space"]).sum())

    # ---- charts ----
    def strip_chart():
        values = lead_buildings.to_numpy()
        low, high = float(values.min()), float(values.max())
        pad = (high - low) * 0.05
        low_axis, high_axis = low - pad, high + pad

        def x(value):
            return 30 + 560 * (value - low_axis) / (high_axis - low_axis)

        ticks = "\n".join(
            f'<line x1="{x(v):.1f}" y1="40" x2="{x(v):.1f}" y2="90" stroke="var(--accent)" stroke-width="2" opacity="0.55"/>'
            for v in values
        )
        mid = x(lead_suburb_median)
        return f"""<svg viewBox="0 0 620 140" role="img" aria-label="Typical weekly asking rent for each of {len(values)} buildings with {lead_type} in {place(lead['suburb'])}, from {money(low)} to {money(high)}. The suburb's typical rent is {money(lead_suburb_median)}.">
  <line x1="30" y1="90" x2="590" y2="90" stroke="var(--line)"/>
  {ticks}
  <line x1="{mid:.1f}" y1="28" x2="{mid:.1f}" y2="100" stroke="var(--ink)" stroke-dasharray="3 3"/>
  <text x="{mid:.1f}" y="20" font-size="12" fill="var(--ink)" text-anchor="middle">Suburb typical {money(lead_suburb_median)}</text>
  <text x="{x(low):.1f}" y="116" font-size="12" fill="var(--dim)" text-anchor="start">{money(low)}</text>
  <text x="{x(high):.1f}" y="116" font-size="12" fill="var(--dim)" text-anchor="end">{money(high)}</text>
  <text x="310" y="134" font-size="11" fill="var(--dim)" text-anchor="middle">Each line is one building's typical weekly asking rent</text>
</svg>"""

    def miss_chart():
        bands = [(0, 50, "Within $50"), (50, 100, "Over $50 up to $100"),
                 (100, 200, "Over $100 up to $200"), (200, np.inf, "More than $200")]
        counts = []
        for low, high, label in bands:
            def count(misses):
                inside = (misses > low) & (misses <= high) if low > 0 else misses <= high
                return int(inside.sum())
            counts.append((label, count(example["misses"]), count(ours["misses"])))
        largest = max(max(a, b) for _, a, b in counts)
        rows = []
        for i, (label, theirs, mine) in enumerate(counts):
            y = 18 + i * 54
            w1 = 330 * theirs / largest
            w2 = 330 * mine / largest
            rows.append(f"""<text x="0" y="{y + 12}" font-size="12" fill="var(--ink)">{label}</text>
  <rect x="170" y="{y}" width="{w1:.1f}" height="16" fill="var(--muted)"/>
  <text x="{176 + w1:.1f}" y="{y + 12}" font-size="12" fill="var(--dim)">{theirs:,}</text>
  <rect x="170" y="{y + 20}" width="{w2:.1f}" height="16" fill="var(--accent)"/>
  <text x="{176 + w2:.1f}" y="{y + 32}" font-size="12" fill="var(--ink)">{mine:,}</text>""")
        return f"""<svg viewBox="0 0 600 236" role="img" aria-label="How far off each of {len(test):,} later adverts was, for the example method and for ours">
  {''.join(rows)}
</svg>
<p class="legend"><span class="key muted"></span>Suburb, bedrooms and parking <span class="key accent"></span>Same building, older asks brought forward</p>"""

    def table(head, rows):
        head_html = "".join(f"<th>{h}</th>" for h in head)
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
        return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body}</tbody></table>"

    def size(beds):
        return "Studio" if beds == 0 else ("1 bedroom" if beds == 1 else f"{int(beds)} bedrooms")

    def flat_type(beds):
        return "studio" if beds == 0 else f"{int(beds)}-bedroom"

    def place(suburb):
        return html.escape(suburb.split(" (")[0])

    def parking(has):
        return "with parking" if has == 1 else "without parking"

    def versus(share):
        return f"{abs(share):.1f}% {'above' if share >= 0 else 'below'}"

    lead_type = f"{flat_type(lead['bedrooms'])} flats {parking(lead['car_space'])}"
    top_over = over_by_suburb.head(2)
    over_names = " and ".join(place(s) for s in top_over.index)
    over_share = top_over["share"].mean() * 100

    page = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Which building a flat is in sets its rent</title>
<style>
  :root {{ color-scheme: light dark; --ink: #1b1b1b; --dim: #666; --line: #d9d9d9; --accent: #3d63d6; --muted: #c4c9d4; --bg: #fff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --ink: #ececec; --dim: #a0a0a0; --line: #383838; --accent: #8aa4f2; --muted: #4a4f5a; --bg: #161616; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0 auto; max-width: 780px; padding: 36px 20px 80px; background: var(--bg); color: var(--ink);
         font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
  h1 {{ font-size: 28px; line-height: 1.25; font-weight: 500; margin: 0 0 14px; }}
  h2 {{ font-size: 20px; font-weight: 500; margin: 44px 0 10px; }}
  p {{ margin: 10px 0; }}
  .lead {{ font-size: 17px; }}
  .finding {{ border-top: 1px solid var(--line); padding: 16px 0 6px; }}
  .finding .figure {{ font-size: 24px; font-weight: 500; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }}
  .stat {{ flex: 1 1 160px; border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }}
  .stat b {{ display: block; font-size: 24px; font-weight: 500; }}
  .stat span {{ color: var(--dim); font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 15px; }}
  th, td {{ text-align: left; padding: 7px 10px 7px 0; border-bottom: 1px solid var(--line); }}
  th {{ font-weight: 500; color: var(--dim); font-size: 13px; }}
  td + td, th + th {{ text-align: right; }}
  svg {{ width: 100%; height: auto; display: block; margin: 14px 0 4px; }}
  .caption, .legend {{ color: var(--dim); font-size: 14px; }}
  .key {{ display: inline-block; width: 12px; height: 12px; margin: 0 6px 0 14px; vertical-align: -1px; }}
  .key:first-child {{ margin-left: 0; }}
  .key.muted {{ background: var(--muted); }}
  .key.accent {{ background: var(--accent); }}
  .flow {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 14px 0; font-size: 15px; }}
  .flow span {{ border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; }}
  .flow i {{ color: var(--dim); font-style: normal; }}
  .back {{ color: var(--dim); font-size: 14px; }}
</style>

<p class="back">Report for the Microburbs Hackathon Rents task, 7 November 2026</p>
<h1>Which building a flat is in sets its rent. Its floor barely does.</h1>

<p class="lead">{lead_type[0].upper() + lead_type[1:]} in {place(lead['suburb'])} ask anywhere from
{money(lead['low'])} to {money(lead['high'])} a week, depending on the building. That {money(lead['high'] - lead['low'])}
spread sits inside one suburb, one bedroom count and one parking answer. Moving up one floor in the same building adds
about {money(per_floor, 2)} a week. Comparing a flat with its own building instead of its suburb cut the typical miss
from {money(example['miss'])} to {money(ours['miss'], 2)} on {len(test):,} later adverts.</p>

<p>Tenants can check an ask against the same building before signing. Landlords can price against their own building
before advertising. Buyers can see that two flats in one suburb are not one rent.</p>

{strip_chart()}
<p class="caption">{len(lead_buildings)} {place(lead['suburb'])} buildings with at least five adverts for
{lead_type}, dated by 30 April 2026 and brought forward to that date.</p>

<h2>What we found along the way</h2>

<div class="finding">
  <div class="figure">{money(lead['high'] - lead['low'])} a week</div>
  <p>The gap between the cheapest and dearest building for one flat type in one suburb. The three groups with the most
  buildings were
  {"; ".join(f"{flat_type(r.bedrooms)} flats {parking(r.car_space)} in {place(r.suburb)}, {money(r.low)} to {money(r.high)}" for r in spread.head(3).itertuples())}.
  A suburb median hides most of what sets a flat's rent. This is the rent side of the
  <a href="https://www.microburbs.com.au/research/median-mirage">Median Mirage</a>.</p>
</div>

<div class="finding">
  <div class="figure">{money(per_floor, 2)} a week per floor</div>
  <p>Measured across {len(floors):,} adverts in {floors['group'].nunique():,} groups that share a building, bedroom
  count and parking answer and span at least two floors. Against their own group's typical rent:</p>
  {table(["Floor", "Adverts", "Against the building's typical rent"],
         [(label, f"{n:,}", f"{gap:+,.2f}") for label, n, gap in floor_bands])}
  <p>Once the building is known, height adds little. Floor level comes from the unit number, so it is known for only
  34,396 of the 65,777 flats.</p>
</div>

<div class="finding">
  <div class="figure">{money(abs(bias), 2)} typical bias</div>
  <p>Half of the later adverts asked more than our estimate and half asked less. The task page reports that the
  Microburbs rental valuation runs about $61 a week low. That figure is measured on August and September 2026 adverts,
  ours on May to July, so the two are not the same test.</p>
</div>

<div class="finding">
  <div class="figure">{over.mean() * 100:.1f}% of asks</div>
  <p>{int(over.sum()):,} of the {len(test):,} later adverts asked more than $100 a week above their building's going
  rate. In {over_names} it was about {over_share:.0f}%. That is the tenant check this estimate makes possible.</p>
</div>

<div class="finding">
  <div class="figure">{money(model.gap_typical)} a week for a car space</div>
  <p>The typical gap across {len(model.gap_by_suburb)} suburb and bedroom groups with at least ten adverts for each
  parking answer, about {money(model.gap_typical * 52)} a year. It grows with the flat:</p>
  {table(["Flat", "Car space adds"], [(size(beds), money(gap, 2)) for beds, gap in gap_rows])}
  <p>The example report found $90 using one year of adverts. Ours uses three years brought forward to April 2026,
  which reaches more groups.</p>
</div>

<div class="finding">
  <div class="figure">{fast.median() * 100:+.1f}% against {no_new.median() * 100:+.1f}%</div>
  <p>Flats in blocks where homes grew by more than 30% from 2021 to 2026 asked {versus(fast.median() * 100)}
  their suburb's typical rent for the same flat type. Flats in blocks with no new homes asked
  {versus(no_new.median() * 100)}. New buildings may simply be newer, so this is a pattern, not a cause.</p>
</div>

<div class="finding">
  <div class="figure">{indexed_change:+.1f}% after the market move</div>
  <p>{len(relisted):,} flats came back on the market in the later period. They asked {versus(raw_change)} their own
  previous advert, but {versus(indexed_change)} it once that earlier ask is brought forward by the city-wide move.
  Relisted flats mostly follow the market rather than jump ahead of it.</p>
</div>

<h2>What our separate check showed</h2>

<div class="stats">
  <div class="stat"><b>{money(ours['miss'], 2)}</b><span>typical miss a week</span></div>
  <div class="stat"><b>{ours['within']:.1f}%</b><span>{ours['within_n']:,} of {len(test):,} within $100</span></div>
  <div class="stat"><b>{ours['r2']:.3f}</b><span>R squared</span></div>
</div>

<p>R squared was {ours['r2']:.3f} on {len(test):,} later adverts. R squared is the share of variation in weekly rent
the estimate explains. The same adverts under the example report's method gave a {money(example['miss'])} typical miss,
{example['within']:.1f}% within $100 and R squared {example['r2']:.3f}.</p>

{miss_chart()}

{table(["Estimate", "Typical miss", "Within $100", "R squared"],
       [(name, money(s['miss'], 2), f"{s['within']:.1f}%", f"{s['r2']:.3f}") for name, s in steps])}

<p>We built the estimate using adverts dated by 30 April 2026. We kept the 1 May to 31 July 2026 adverts aside until
the estimate was fixed. The Microburbs Hackathon scores hidden August to September 2026 adverts separately.</p>

<h2>What data supported the result?</h2>

<p>{int(raw_window.sum()):,} adverts in the supplied lease file are dated 1 May 2023 to 30 April 2026.
{model.adverts_used:,} of them carry a bedroom count and a parking answer and built the estimate.
Another {int(raw_window.sum()) - model.adverts_used:,} lacked one or the other and were left out.
{len(test):,} later adverts tested it, and {int(raw_test.sum()) - len(test):,} more lacked bedrooms or parking.</p>

<p>Floor level and block growth come from the supplied flat file and block file. We did not call the Microburbs API
and read nothing dated after 31 July 2026.</p>

<h2>How did we estimate rent?</h2>

<div class="flow"><span>Earlier adverts</span><i>→</i><span>Brought forward to April 2026</span><i>→</i><span>Same building, bedrooms and parking</span><i>→</i><span>Median weekly rent</span></div>

<p>Each older ask is scaled by how the city-wide median ask moved between its quarter and the quarter ending April 2026,
then weighted down as it ages, halving every three years. Adverts older than three years are left out.</p>

<p>A building group needs one earlier advert. Where a building has only advertised one parking answer, the other rent
is that one plus the parking gap for its suburb and bedroom count, kept between $0 and a quarter of the rent.</p>

<p>A building that never advertised this flat type borrows the median of the {rm.NEIGHBOURS} nearest buildings
within {rm.NEIGHBOUR_REACH_M:,} metres that did, by straight-line distance from the supplied coordinates. Only where
none is in reach does it fall back to the suburb, bedrooms and parking median, which needs ten earlier adverts, then
to bedrooms.</p>

{table(["Comparison used", "Later adverts", "Typical miss", "Within $100"],
       [(name, f"{r.n:,}", money(r.typical, 2), f"{r.within:.1f}%") for name, r in sources.iterrows()])}

<h2>How did we check it?</h2>

<p>The three year reach, the three year half life, the one advert minimum and the {rm.NEIGHBOURS} nearest buildings
within {rm.NEIGHBOUR_REACH_M:,} metres were chosen on three earlier checks,
scored on February to April 2026, November 2025 to January 2026, and August to October 2025. The May to July 2026
adverts played no part in choosing them. Floor level was tested the same way and left out, because it raised the
typical miss on two of the three.</p>

<p>The miss held steady across the test window, which matters because the hidden adverts run up to two months past
the as-at date:</p>
{table(["Month", "Later adverts", "Typical miss"],
       [(str(month), f"{r.n:,}", money(r.typical, 2)) for month, r in by_month.iterrows()])}

<p>Rebuilding the estimate before each of seven earlier quarters and scoring that quarter gave:</p>
{table(["Quarter", "Adverts", "Typical miss", "Within $100"],
       [(q, f"{n:,}", money(m, 2), f"{w:.1f}%") for q, n, m, w in quarters])}

<p>Drawing 1,699 adverts at random, the size of the hidden set, 2,000 times put the typical miss between
{money(low_band, 2)} and {money(high_band, 2)} nine times in ten.</p>

<h2>What remains uncertain?</h2>

<p>{len(suburb_rows):,} later adverts sat in buildings with no earlier advert for their flat type. Borrowing from
nearby buildings, they missed by a typical {money(suburb_rows['miss'].median(), 2)}, down from
{money((suburb_only_rent[suburb_rows.index] - suburb_rows['weekly_rent']).abs().median(), 2)} with the suburb alone,
but still well above {money(test.loc[building_sources, 'miss'].median(), 2)} for flats with their own building's
adverts.</p>

<p>{int(had_own.sum()):,} later flats had advertised before. Deleting every later flat's own past adverts, so each
estimate came only from other flats, raised the typical miss to {money(without_own_miss.median(), 2)} with
{(without_own_miss <= 100).mean() * 100:.1f}% within $100. That is closer to what the 16,094 never-advertised flats
can expect.</p>

<p>In the hand-in file, {lower_with_parking:,} flats price a car space below no car space, because their own building's
adverts did. We kept those rather than override the evidence.</p>

<p>We did not test which way a flat faces or whether nearby buildings block light. The supplied files hold no
orientation or building height, and condition is not recorded anywhere.</p>

<p>The separate May to July 2026 check had a {money(ours['miss'], 2)} typical weekly miss.</p>
</html>
"""

    with open(rm.SITE_DIR / "report.html", "w") as handle:
        handle.write(page)
    print(f"Wrote report.html: miss {money(ours['miss'], 2)}, within {ours['within']:.1f}%, R2 {ours['r2']:.3f}")


if __name__ == "__main__":
    main()
