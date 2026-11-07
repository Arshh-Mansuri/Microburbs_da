"""Build the site's index.html: a tenant enters their flat and rent, and sees how it
compares with what similar flats were asking at 31 July 2026.

    python make_rent_check.py

The page is self-contained. Estimates come from the same rule as the hand-in,
refitted on every advert to 31 July 2026. The spread shown around each estimate
comes from the May to July 2026 check, scored on a model fitted to 30 April.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import rent_model as rm

AS_AT = pd.Timestamp("2026-07-31")
CHECK_FROM = pd.Timestamp("2026-05-01")
BEDROOMS = [0, 1, 2, 3, 4, 5]
SOURCES = [
    "building advertised both",
    "building, parking gap",
    "nearby buildings",
    "nearby buildings, parking gap",
    "suburb advertised both",
    "suburb, parking gap",
    "bedrooms, parking gap",
    "nearest bedroom count",
    "citywide",
]


def evidence(source: str) -> str:
    if "own adverts" in source:
        return "own"
    if source.startswith("building"):
        return "building"
    if source.startswith("nearby"):
        return "nearby"
    return "suburb"


def spreads(leases: pd.DataFrame) -> dict:
    """How far later asks landed from the estimate, by what the estimate rested on."""
    earlier = leases.loc[leases["listing_date"] < CHECK_FROM]
    later = leases.loc[leases["listing_date"].between(CHECK_FROM, AS_AT)]
    as_at = CHECK_FROM - pd.Timedelta(days=1)
    asked = later["weekly_rent"].to_numpy()

    def scored(model):
        both = model.predict_both(later)
        estimate = np.where(later["car_space"] == 1, both["rent_with_car_space"], both["rent_without_car_space"])
        return asked / estimate, np.abs(asked - estimate), both["source"].map(evidence).to_numpy()

    # Every later advert had a building or a neighbour to lean on, so the suburb
    # spread is measured on the same adverts with the neighbour step switched off.
    ratio, miss, kind = scored(rm.RentModel(as_at=as_at).fit(earlier))
    suburb_ratio, suburb_miss, suburb_kind = scored(rm.RentModel(as_at=as_at, neighbours=0).fit(earlier))
    found = {}
    for name in ("own", "building", "nearby", "suburb"):
        if name == "suburb":
            ratio, miss, kind = suburb_ratio, suburb_miss, suburb_kind
        chosen = kind == name
        q10, q25, q75, q90 = np.quantile(ratio[chosen], [0.1, 0.25, 0.75, 0.9])
        found[name] = {
            "q": [round(q, 4) for q in (q10, q25, q75, q90)],
            "miss": round(float(np.median(miss[chosen])), 2),
            "n": int(chosen.sum()),
        }
    return found


def split_address(address: str) -> tuple[str, str]:
    if ", " in address:
        unit, street = address.split(", ", 1)
        return unit, street
    return "", address


def main() -> None:
    leases = rm.load_leases()
    flats = rm.load_flats()
    model = rm.RentModel(as_at=AS_AT).fit(leases)

    ads = model._as_at_prices(leases)
    counts = ads.groupby(["building_address", "bedrooms", "car_space"]).size().to_dict()
    own_counts = ads.groupby(["gnaf_id", "bedrooms"]).size().to_dict()
    refined = model.predict_both(flats)

    buildings = (
        flats.groupby(["building_address", "suburb"], sort=False)[["latitude", "longitude"]]
        .median()
        .reset_index()
    )
    suburbs = sorted(flats["suburb"].unique())
    suburb_id = {name: i for i, name in enumerate(suburbs)}

    def pair(building_address, bedrooms, suburb, latitude=np.nan, longitude=np.nan):
        with_parking, without_parking, source = model._pair(
            building_address, float(bedrooms), suburb, latitude, longitude
        )
        return [
            round(with_parking * 2) / 2,
            round(without_parking * 2) / 2,
            SOURCES.index(source),
            counts.get((building_address, float(bedrooms), 1.0), 0),
            counts.get((building_address, float(bedrooms), 0.0), 0),
        ]

    building_rows = []
    building_id = {}
    for i, row in enumerate(buildings.itertuples(index=False)):
        building_id[(row.building_address, row.suburb)] = i
        building_rows.append(
            [suburb_id[row.suburb]]
            + [pair(row.building_address, b, row.suburb, row.latitude, row.longitude) for b in BEDROOMS]
        )

    suburb_rows = [[pair(None, b, name) for b in BEDROOMS] for name in suburbs]

    streets, street_id, flat_rows = [], {}, []
    for row, own in zip(flats.itertuples(index=False), refined.itertuples(index=False)):
        unit, street = split_address(row.address)
        if street not in street_id:
            street_id[street] = len(streets)
            streets.append(street)
        flat_row = [
            unit,
            street_id[street],
            building_id[(row.building_address, row.suburb)],
            -1 if pd.isna(row.bedrooms) else int(min(row.bedrooms, 5)),
            -1 if pd.isna(row.car_space) else int(row.car_space),
        ]
        # The flat's own asks and bathroom count only apply at its recorded bedrooms.
        flags = ("own adverts" in own.source) * 1 + ("bathrooms" in own.source) * 2
        if flags:
            flat_row += [
                round(own.rent_with_car_space * 2) / 2,
                round(own.rent_without_car_space * 2) / 2,
                flags,
                own_counts.get((row.gnaf_id, row.bedrooms), 0),
            ]
        flat_rows.append(flat_row)

    data = {
        "streets": streets,
        "flats": flat_rows,
        "buildings": building_rows,
        "suburbs": suburbs,
        "suburbRents": suburb_rows,
        "sources": SOURCES,
        "spread": spreads(leases),
        "neighbours": rm.NEIGHBOURS,
        "reach": rm.NEIGHBOUR_REACH_M,
        "years": rm.MAX_AGE_YEARS,
    }
    payload = json.dumps(data, separators=(",", ":"))
    html = PAGE.replace("__DATA__", payload)
    with open(rm.SITE_DIR / "index.html", "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"Wrote index.html: {len(flat_rows):,} flats, {len(building_rows):,} buildings, "
          f"{len(html) / 1e6:.1f} MB")
    for name, found in data["spread"].items():
        print(name, found)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Is my rent fair? City of Sydney rent check</title>
<style>
  :root { --navy: #002664; --red: #d7153a; --ink: #22272b; --muted: #5b6770; --panel: #f2f2f2; --line: #cdd3d6;
          --good: #00838f; --warn: #b65c00; --bad: #b81237; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color: var(--ink); background: #fff; line-height: 1.45; }
  header { background: var(--navy); color: #fff; padding: 14px 0; }
  header .wrap { display: flex; align-items: baseline; gap: 14px; }
  header strong { font-size: 18px; }
  header span { opacity: .8; font-size: 14px; }
  .wrap { max-width: 780px; margin: 0 auto; padding: 0 20px; }
  main { padding: 32px 0 60px; }
  .progress-label { font-size: 13px; color: var(--muted); }
  .progress { display: flex; gap: 4px; margin: 6px 0 18px; }
  .progress div { flex: 1; height: 3px; background: #e4e4e4; }
  .progress div.done { background: var(--red); }
  .back { background: none; border: 0; color: var(--navy); font-weight: 600; font-size: 14px; padding: 0;
          cursor: pointer; margin-bottom: 18px; }
  h1 { font-size: 24px; margin: 0 0 6px; line-height: 1.25; }
  .hint { color: var(--muted); margin: 0 0 18px; font-size: 15px; }
  input[type=text] { width: 100%; max-width: 520px; padding: 11px 12px; font-size: 16px; border: 1px solid #757575;
                     border-radius: 4px; }
  input[type=text]:focus { outline: 3px solid #2e5299; outline-offset: 1px; }
  .money { position: relative; max-width: 340px; }
  .money span { position: absolute; left: 12px; top: 11px; font-size: 16px; }
  .money input { padding-left: 26px; }
  .results { max-width: 520px; border: 1px solid var(--line); border-top: 0; border-radius: 0 0 4px 4px; }
  .results button { display: block; width: 100%; text-align: left; background: #fff; border: 0;
                    border-top: 1px solid #eee; padding: 10px 12px; font-size: 15px; cursor: pointer; }
  .results button:hover, .results button:focus { background: #e8eef8; }
  .results small { color: var(--muted); }
  .choices { display: flex; flex-wrap: wrap; gap: 10px; }
  .choice { min-width: 92px; padding: 11px 16px; border: 1px solid #757575; border-radius: 4px; background: #fff;
            font-size: 16px; cursor: pointer; }
  .choice.on { border: 2px solid var(--navy); background: #e8eef8; font-weight: 600; }
  .note { font-size: 14px; color: var(--muted); margin: 12px 0 0; }
  .primary { margin-top: 22px; background: var(--navy); color: #fff; border: 0; border-radius: 4px; padding: 12px 30px;
             font-size: 15px; font-weight: 600; cursor: pointer; }
  .primary:disabled { opacity: .45; cursor: default; }
  .link { background: none; border: 0; padding: 0; color: var(--navy); text-decoration: underline; font-weight: 600;
          cursor: pointer; font-size: 14px; }
  select { padding: 10px; font-size: 16px; border: 1px solid #757575; border-radius: 4px; min-width: 260px; }
  .answered { background: var(--panel); border-radius: 4px; padding: 18px 22px; margin-top: 36px; }
  .answered h2 { font-size: 16px; margin: 0 0 8px; }
  .answered ol { list-style: none; margin: 0; padding: 0; }
  .answered li { display: flex; justify-content: space-between; gap: 12px; padding: 11px 0; border-top: 1px solid #e2e2e2; }
  .answered li:first-child { border-top: 0; }
  .answered .q { font-weight: 600; font-size: 14px; }
  .answered .a { font-size: 14px; color: var(--muted); }
  .verdict { border-left: 6px solid var(--good); padding: 4px 0 4px 18px; margin: 4px 0 22px; }
  .verdict.high { border-color: var(--warn); }
  .verdict.very-high { border-color: var(--bad); }
  .verdict.low { border-color: var(--navy); }
  .verdict h1 { font-size: 26px; }
  .verdict p { margin: 4px 0 0; font-size: 17px; }
  .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0 0 26px; }
  .card { background: var(--panel); border-radius: 4px; padding: 14px; }
  .card b { display: block; font-size: 22px; }
  .card span { font-size: 13px; color: var(--muted); }
  .scale { position: relative; height: 74px; margin: 6px 0 28px; }
  .track { position: absolute; left: 0; right: 0; top: 30px; height: 12px; border-radius: 6px;
           background: linear-gradient(90deg, #dfe6ee 0%, #dfe6ee 100%); }
  .band { position: absolute; top: 30px; height: 12px; background: #9fb3d1; }
  .mid { position: absolute; top: 30px; height: 12px; background: var(--navy); opacity: .85; }
  .mark { position: absolute; top: 18px; width: 3px; height: 36px; background: var(--red); transform: translateX(-1px); }
  .mark-label { position: absolute; top: 0; font-size: 13px; font-weight: 700; color: var(--red);
                transform: translateX(-50%); white-space: nowrap; }
  .tick-label { position: absolute; top: 50px; font-size: 12px; color: var(--muted); transform: translateX(-50%);
                white-space: nowrap; }
  .legend { font-size: 13px; color: var(--muted); display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 22px; }
  .legend i { display: inline-block; width: 14px; height: 10px; margin-right: 6px; vertical-align: middle; }
  h2 { font-size: 18px; margin: 26px 0 6px; }
  .small { font-size: 14px; color: var(--muted); }
  footer { border-top: 1px solid #e4e4e4; padding: 18px 0 40px; font-size: 13px; color: var(--muted); }
  @media (max-width: 600px) { .cards { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header><div class="wrap"><strong>Rent check</strong><span>City of Sydney flats, asking rents at 31 July 2026</span></div></header>
<main><div class="wrap" id="app"></div></main>
<footer><div class="wrap">
  Estimates come from earlier asking rents in public rental adverts, brought forward to 31 July 2026. They describe
  what new adverts ask, not what every sitting tenant pays, and they cannot see condition, views, furniture or
  inclusions. This is a guide, not legal or financial advice.
  <p><a href="report.html">How the estimates were made and checked</a> &middot; <a href="dashboard.html">Dashboard</a></p>
</div></footer>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const STEPS = 4;
const BED_LABEL = ["Studio", "1 bedroom", "2 bedrooms", "3 bedrooms", "4 bedrooms", "5 or more bedrooms"];
const BED_SHORT = ["Studio", "1", "2", "3", "4", "5+"];
const index = D.flats.map(f => ((f[0] ? f[0] + ", " : "") + D.streets[f[1]]).toUpperCase());
const state = { step: 1, flat: null, suburb: null, bedrooms: null, parking: null, rent: null };

const $ = html => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; };
const money = v => "$" + Math.round(v).toLocaleString("en-AU");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const titleCase = s => s.toLowerCase().replace(/\b([a-z])/g, m => m.toUpperCase());

function addressOf(i) {
  const f = D.flats[i];
  return titleCase((f[0] ? f[0] + ", " : "") + D.streets[f[1]]);
}

function place() {
  if (state.flat !== null) return addressOf(state.flat);
  return state.suburb !== null ? D.suburbs[state.suburb] + " (building not listed)" : "";
}

function estimate() {
  const row = state.flat !== null
    ? D.buildings[D.flats[state.flat][2]][1 + state.bedrooms]
    : D.suburbRents[state.suburb][state.bedrooms];
  let [withP, withoutP, src, nWith, nWithout] = row;
  const source = D.sources[src];
  let kind = source.startsWith("building") ? "building" : source.startsWith("nearby") ? "nearby" : "suburb";
  let own = 0, bathrooms = false;
  const f = state.flat !== null ? D.flats[state.flat] : null;
  if (f && f.length > 5 && f[3] === state.bedrooms) {
    [withP, withoutP] = [f[5], f[6]];
    bathrooms = (f[7] & 2) > 0;
    if (f[7] & 1) { own = f[8]; kind = "own"; }
  }
  return { rent: state.parking ? withP : withoutP, other: state.parking ? withoutP : withP,
           withP, withoutP, source, kind, nWith, nWithout, own, bathrooms };
}

function progress() {
  const bars = Array.from({ length: STEPS }, (_, i) => `<div class="${i < state.step ? "done" : ""}"></div>`).join("");
  return `<div class="progress-label">Step ${Math.min(state.step, STEPS)} of ${STEPS}</div><div class="progress">${bars}</div>`;
}

function answered() {
  const rows = [];
  if (state.step > 1) rows.push([1, "What is the address?", place()]);
  if (state.step > 2) rows.push([2, "How many bedrooms?", BED_LABEL[state.bedrooms]]);
  if (state.step > 3) rows.push([3, "Does the rent include a car space?", state.parking ? "Yes" : "No"]);
  if (state.step > 4) rows.push([4, "What is the weekly rent?", money(state.rent)]);
  if (!rows.length) return "";
  return `<section class="answered"><h2>What you've answered</h2><ol>${rows.map(([n, q, a]) =>
    `<li><div><div class="q">${n}. ${q}</div><div class="a">${esc(a)}</div></div>
     <button class="link" data-go="${n}">Change</button></li>`).join("")}</ol></section>`;
}

function render() {
  const app = document.getElementById("app");
  app.innerHTML = "";
  const back = state.step > 1 ? `<button class="back" data-go="${state.step - 1}">&lsaquo; Back</button>` : "";
  const body = [stepAddress, stepBedrooms, stepParking, stepRent, stepResult][state.step - 1]();
  app.append($(`${state.step <= STEPS ? progress() : ""}${back}${body}${answered()}`));
  app.querySelectorAll("[data-go]").forEach(b => b.onclick = () => { state.step = +b.dataset.go; render(); });
  (wire[state.step] || (() => {}))(app);
}

function stepAddress() {
  return `<h1>What is the address of the flat?</h1>
    <p class="hint">Start typing the unit number and street, for example "1406 157 Redfern".</p>
    <input type="text" id="q" autocomplete="off" aria-label="Address" value="${state.flat !== null ? esc(addressOf(state.flat)) : ""}">
    <div class="results" id="results"></div>
    <p class="note">Can't find it? <button class="link" id="nosearch">Choose the suburb instead</button></p>
    <div id="suburbPick" hidden>
      <select id="suburb"><option value="">Select a suburb</option>${D.suburbs.map((s, i) =>
        `<option value="${i}" ${state.suburb === i && state.flat === null ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <div><button class="primary" id="suburbNext" disabled>Next</button></div>
    </div>`;
}

function stepBedrooms() {
  const known = state.flat !== null ? D.flats[state.flat][3] : -1;
  return `<h1>How many bedrooms does the flat have?</h1>
    ${known >= 0 ? `<p class="hint">Records for this flat show ${BED_LABEL[known].toLowerCase()}. Change it if that is wrong.</p>` : ""}
    <div class="choices">${BED_SHORT.map((b, i) => `<button class="choice ${state.bedrooms === i ? "on" : ""}" data-bed="${i}">${b}</button>`).join("")}</div>
    <div><button class="primary" id="next" ${state.bedrooms === null ? "disabled" : ""}>Next</button></div>`;
}

function stepParking() {
  const known = state.flat !== null ? D.flats[state.flat][4] : -1;
  return `<h1>Does the rent include a car space?</h1>
    ${known >= 0 ? `<p class="hint">Records for this flat show ${known ? "a car space" : "no car space"}.</p>` : ""}
    <div class="choices">${["Yes", "No"].map((label, i) => {
      const value = i === 0;
      return `<button class="choice ${state.parking === value ? "on" : ""}" data-park="${value ? 1 : 0}">${label}</button>`;
    }).join("")}</div>
    <div><button class="primary" id="next" ${state.parking === null ? "disabled" : ""}>Next</button></div>`;
}

function stepRent() {
  return `<h1>What is the current weekly rent?</h1>
    <p class="hint">If you are about to sign, enter the weekly rent in the advert.</p>
    <div class="money"><span>$</span><input type="text" id="rent" inputmode="decimal" aria-label="Weekly rent"
      value="${state.rent !== null ? state.rent : ""}"></div>
    <div><button class="primary" id="next" ${state.rent === null ? "disabled" : ""}>Check my rent</button></div>`;
}

function verdictFor(rent, e, q) {
  const ratio = rent / e.rent;
  if (ratio > q[3]) return ["very-high", "Your rent is well above similar flats",
    "Nine in ten new adverts for flats like yours ask less."];
  if (ratio > q[2]) return ["high", "Your rent is on the high side",
    "It is above the middle half of new adverts for flats like yours."];
  if (ratio >= q[1]) return ["fair", "Your rent is in line with similar flats",
    "It sits within the middle half of new adverts for flats like yours."];
  if (ratio >= q[0]) return ["low", "Your rent is on the low side",
    "It is below the middle half of new adverts for flats like yours."];
  return ["low", "Your rent is well below similar flats",
    "Nine in ten new adverts for flats like yours ask more."];
}

function evidenceText(e) {
  const extra = e.bathrooms ? " It is also adjusted to flats in this building with the same number of bathrooms." : "";
  if (e.kind === "own")
    return `This flat itself was advertised ${e.own} time${e.own === 1 ? "" : "s"} in the last ${D.years} years. Its own
      past asks, brought forward to July 2026 prices, carry three quarters of the weight, and the rest of the building
      the remainder.${extra}`;
  return baseEvidence(e) + extra;
}

function baseEvidence(e) {
  const bed = ["studio flats", "1-bedroom flats", "2-bedroom flats", "3-bedroom flats", "4-bedroom flats",
               "flats with 5 or more bedrooms"][state.bedrooms];
  const side = state.parking ? "with a car space" : "without a car space";
  const otherSide = state.parking ? "without a car space" : "with a car space";
  const n = state.parking ? e.nWith : e.nWithout;
  const nOther = state.parking ? e.nWithout : e.nWith;
  const gap = Math.abs(e.withP - e.withoutP);
  if (state.flat === null)
    return `Without a building to go on, the estimate is the typical ask for ${bed} ${side} across
      ${esc(D.suburbs[state.suburb])}. Buildings in one suburb can differ by hundreds of dollars a week, so treat it as a rougher guide.`;
  if (e.kind === "building" && n > 0)
    return `Based on ${n} advert${n === 1 ? "" : "s"} for ${bed} ${side} in this building over the last ${D.years} years,
      with older asks brought forward to July 2026 prices and recent ones counting most.`;
  if (e.kind === "building")
    return `This building has ${nOther} advert${nOther === 1 ? "" : "s"} for ${bed} ${otherSide} over the last ${D.years} years.
      We ${state.parking ? "added" : "took off"} the typical car space difference for similar flats nearby, ${money(gap)} a week.`;
  if (e.kind === "nearby")
    return `This building has not advertised ${bed} recently, so the estimate is the middle ask of the ${D.neighbours}
      nearest buildings within ${D.reach.toLocaleString("en-AU")} metres that have.`;
  return `There are no recent adverts for ${bed} in or near this building, so the estimate uses the suburb as a whole.
      Treat it as a rougher guide.`;
}

function stepResult() {
  const e = estimate();
  const spread = D.spread[e.kind];
  const q = spread.q;
  const [cls, headline, sub] = verdictFor(state.rent, e, q);
  const low = e.rent * q[1], high = e.rent * q[2];
  const lo10 = e.rent * q[0], hi90 = e.rent * q[3];
  const diff = state.rent - e.rent;
  const minV = Math.min(lo10, state.rent) * 0.95, maxV = Math.max(hi90, state.rent) * 1.05;
  const pos = v => ((v - minV) / (maxV - minV) * 100).toFixed(2) + "%";
  const what = `${BED_LABEL[state.bedrooms].toLowerCase()}, ${state.parking ? "with" : "without"} a car space`;
  const advice = cls === "high" || cls === "very-high"
    ? `<h2>What you can do</h2>
       <p>If you are about to sign, the typical ask of ${money(e.rent)} and the range above are a reasonable basis for
       negotiating. If this is a rent increase on an existing lease, NSW Fair Trading explains how often rent can go up,
       and you can apply to the NSW Civil and Administrative Tribunal if you think an increase is excessive.</p>`
    : `<h2>What this means</h2>
       <p>Your rent is ${diff <= 0 ? "at or below" : "close to"} what landlords are asking for comparable flats. If your
       landlord proposes a rise, compare it with the typical ask of ${money(e.rent)} a week.</p>`;
  return `<div class="verdict ${cls}"><h1>${headline}</h1><p>${sub}</p></div>
    <div class="cards">
      <div class="card"><b>${money(state.rent)}</b><span>Your weekly rent</span></div>
      <div class="card"><b>${money(e.rent)}</b><span>Typical ask for this flat</span></div>
      <div class="card"><b>${diff >= 0 ? "+" : "−"}${money(Math.abs(diff))}</b>
        <span>${diff >= 0 ? "Above" : "Below"} typical, about ${money(Math.abs(diff) * 52)} a year</span></div>
    </div>
    <p><b>${esc(place())}</b>, ${what}.</p>
    <div class="scale" aria-hidden="true">
      <div class="track"></div>
      <div class="band" style="left:${pos(lo10)};width:calc(${pos(hi90)} - ${pos(lo10)})"></div>
      <div class="mid" style="left:${pos(low)};width:calc(${pos(high)} - ${pos(low)})"></div>
      <div class="mark" style="left:${pos(state.rent)}"></div>
      <div class="mark-label" style="left:${pos(state.rent)}">You ${money(state.rent)}</div>
      <div class="tick-label" style="left:${pos(low)}">${money(low)}</div>
      <div class="tick-label" style="left:${pos(high)}">${money(high)}</div>
    </div>
    <div class="legend"><span><i style="background:var(--navy)"></i>Middle half of new adverts, ${money(low)} to ${money(high)}</span>
      <span><i style="background:#9fb3d1"></i>Eight in ten, ${money(lo10)} to ${money(hi90)}</span></div>
    ${advice}
    <h2>How we estimated it</h2>
    <p class="small">${evidenceText(e)} The ${state.parking ? "same flat without a car space" : "same flat with a car space"}
      would ask about ${money(e.other)} a week.</p>
    <p class="small">The ranges come from a check on ${spread.n.toLocaleString("en-AU")} adverts placed from May to July 2026,
      priced using only earlier adverts. For estimates like this one, half of those adverts landed within
      ${money(spread.miss)} of the estimate.</p>
    <button class="primary" id="restart">Check another flat</button>`;
}

const wire = {
  1(app) {
    const q = app.querySelector("#q"), results = app.querySelector("#results");
    const pick = app.querySelector("#suburbPick"), sub = app.querySelector("#suburb"), subNext = app.querySelector("#suburbNext");
    const search = () => {
      const words = q.value.toUpperCase().replace(/[,/]/g, " ").split(/\s+/).filter(Boolean);
      results.innerHTML = "";
      if (!words.length || (words.length === 1 && words[0].length < 2)) return;
      const found = [];
      for (let i = 0; i < index.length && found.length < 8; i++)
        if (words.every(w => index[i].includes(w))) found.push(i);
      results.innerHTML = found.length
        ? found.map(i => `<button data-flat="${i}">${esc(addressOf(i))}<br><small>${D.suburbs[D.buildings[D.flats[i][2]][0]]}</small></button>`).join("")
        : `<button disabled><small>No flats match. Try fewer words, or choose the suburb below.</small></button>`;
      results.querySelectorAll("[data-flat]").forEach(b => b.onclick = () => {
        const i = +b.dataset.flat, f = D.flats[i];
        state.flat = i; state.suburb = D.buildings[f[2]][0];
        state.bedrooms = f[3] >= 0 ? f[3] : null; state.parking = f[4] >= 0 ? f[4] === 1 : null;
        state.step = 2; render();
      });
    };
    q.oninput = search;
    q.focus();
    app.querySelector("#nosearch").onclick = () => { pick.hidden = false; sub.focus(); };
    sub.onchange = () => { subNext.disabled = sub.value === ""; };
    subNext.onclick = () => {
      state.flat = null; state.suburb = +sub.value; state.step = 2; render();
    };
  },
  2(app) {
    app.querySelectorAll("[data-bed]").forEach(b => b.onclick = () => { state.bedrooms = +b.dataset.bed; render(); });
    app.querySelector("#next").onclick = () => { state.step = 3; render(); };
  },
  3(app) {
    app.querySelectorAll("[data-park]").forEach(b => b.onclick = () => { state.parking = b.dataset.park === "1"; render(); });
    app.querySelector("#next").onclick = () => { state.step = 4; render(); };
  },
  4(app) {
    const input = app.querySelector("#rent"), next = app.querySelector("#next");
    const read = () => {
      const v = parseFloat(input.value.replace(/[$,\s]/g, ""));
      state.rent = v > 0 && v < 20000 ? v : null;
      next.disabled = state.rent === null;
    };
    input.oninput = read;
    input.onkeydown = ev => { if (ev.key === "Enter" && state.rent !== null) next.click(); };
    input.focus();
    next.onclick = () => { state.step = 5; render(); };
  },
  5(app) {
    app.querySelector("#restart").onclick = () => {
      Object.assign(state, { step: 1, flat: null, suburb: null, bedrooms: null, parking: null, rent: null });
      render();
    };
  },
};

render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
