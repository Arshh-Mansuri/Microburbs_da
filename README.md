# Weekly rents for every City of Sydney flat

Microburbs Hackathon, task 4. We estimate two weekly asking rents, one with a car space and one without, for all
65,777 flats in the City of Sydney as at 31 July 2026.

Across 20 rolling two-month tests before May 2026 (45,592 adverts, each test fitted only on earlier adverts), the
typical miss is **$51.00 a week** and **73.9%** of estimates land within $100. On the later May to July 2026 adverts
the typical miss is $45.37, compared with $100.00 for the example suburb method, with 77.4% within $100 against
56.8%, and R squared 0.871. May to July was looked at across several versions, so treat $45.37 as optimistic; the
rolling figure is the fairer guide to the scored test.

## For the judges

Team **Uni Trifecta**. Live rent check: [microburbsdataanalysis.vercel.app](https://microburbsdataanalysis.vercel.app).

### Submission

| File | What it is |
|---|---|
| `analysis/rents_uni-trifecta.csv` | Both weekly rents for all 65,777 flats, in input order |
| `report.html` | Findings, the separate check, method and limits |
| `pitch.mp4` | 45-second pitch |
| `demo.mp4` | Three-minute walkthrough of the analysis and the rent check |
| `README.md` | This file |
| `pitch.pdf` | Slides behind the pitch (extra) |
| `dashboard.html` | One-page summary of the results (extra) |

The CSV has exactly the columns `gnaf_id, rent_with_car_space, rent_without_car_space`. Every gnaf_id appears
once and both rents are filled for every flat, so no scored answer is blank. All values are positive and end in
whole dollars or 50 cents.

### Results in brief

| Measure | Example method, May–July | Ours, May–July | Ours, 20 rolling tests before May 2026 |
|---|---|---|---|
| Typical (median) miss | $100.00 | **$45.37** | **$51.00** |
| Within $100 | 56.8% | **77.4%** | **73.9%** |
| R squared | 0.645 | **0.871** | |

The rolling tests mirror the hand-in: fit on adverts up to the end of a month, then score the next two months.
They are run by `analysis/validate_rolling.py`, which never reads May to July. No later period is left untouched
before the scored August–September test, so we report both.

Scored by the evidence the fitted model actually used, across the same rolling tests:

| Case | Adverts | Typical miss | Within $100 |
|---|---|---|---|
| All | 45,592 | $51.50 | 73.7% |
| No parking / with parking | 20,389 / 25,203 | $45.50 / $58.00 | 77.8% / 70.5% |
| Flat has no own advert history in the window | 26,734 | $63.00 | 68.0% |
| No usable building history (priced from neighbours or suburb) | 4,654 | $90.00 | 54.8% |
| No usable nearby match either (suburb or bedrooms only) | 15 | $478.50 | 13.3% |

These groups come from the shared-shift version, before the per-side change in step 6 below. Their sources depend
on the three-year window and on borrowing across parking, so they differ from the simpler groups in the May–July
table under Method.

Taken on the previous version, which scored $45.44 on May to July:

- **Stable across time.** By month the typical miss was $44.12 in May, $44.12 in June and $47.76 in July. Across
  seven earlier quarters it ran $50 to $60.
- **Stable across samples.** Resampling 1,699 adverts, the size of the scored test, gives a typical miss between
  $43.09 and $47.16 in 90% of draws.
- **Small bias.** The median estimate sits $1.24 above the ask.

### How we kept the check honest

- **Nothing after 31 July 2026.** No advert dated after the as-at date is read, and the live for-rent listings
  endpoint was not used.
- **Tuned on earlier adverts only.** Every setting was chosen on adverts before May 2026, on three earlier folds
  or on the 20 rolling tests.
- **May to July is not a clean test.** It was scored after each version was frozen, but looking at it across
  versions makes it optimistic. The growth lift was switched off after losing on it. Every step is reported,
  including the one that cost 44 cents there.
- **Ideas that failed stay in the repository.** Forcing a car space to price above no car space, a floor
  adjustment, and lifting rents for growth after 31 July each looked plausible but lost on the checks. The floor
  test is in the notebook, and the scripts for the other two are listed under Layout.

### Checking it in two minutes

1. Open `report.html`. The step table shows each improvement from the $100 example down to $45.37.
2. Open the live rent check, search for an address such as `1611/301 Botany Rd`, then enter a rent to see how it
   compares with similar flats.
3. To reproduce the CSV, follow Running it below. `analysis/make_rents.py` refuses to run if any advert is dated
   after 31 July 2026. It also stops before writing if the row count is wrong, a gnaf_id repeats or a rent is
   blank.

### Limits

About 12% of asks came in more than $100 above their building's usual rate, mostly in Potts Point and Surry
Hills. Past adverts alone cannot see renovations or furnishing, so these remain the largest misses. Flats priced
without usable building history miss by $90 typically, and the handful with no nearby match either by far more.
Together they are about one advert in ten. A CatBoost model on past-only building summaries is the next thing we
would benchmark for these sparse cases.

## What decides a flat's rent

The building a flat is in matters most. In Zetland, two-bedroom flats with parking ask anywhere from $978 to $1,500
a week depending on the building, while the suburb median is $1,165. Floor barely matters: each extra floor adds
about $1.46 a week once the building is known. `report.html` covers these findings in full.

## Method

1. Take earlier asking rents from the last 3 years and bring each one forward to 31 July 2026 using a citywide
   quarterly median index. Older adverts count for less, with a 3-year half-life.
2. Estimate the rent as the weighted median for the flat's own building, bedroom count and parking. One earlier
   advert is enough.
3. If that building has never advertised that type of flat, use the median of the 10 nearest buildings within
   1,000 metres that have.
4. If none are in reach, fall back to suburb × bedrooms × parking (10 or more adverts), then suburb × bedrooms,
   then bedrooms alone, then the nearest bedroom count.
5. Where only one parking side has evidence, the other side is that rent plus or minus a parking gap. The gap comes
   from the suburb and bedroom count where both sides are well advertised, and is capped at 25% of the rent.
   The typical gap is about $76 a week.
6. Two fields then move both rents for the individual flat. Where 3 or more adverts in the building share its
   bedrooms, bathrooms and parking, the estimate shifts to their median. Where the flat itself advertised before,
   its own asks, brought forward the same way, take 75% of the weight and the building the rest. Each parking
   side uses its own evidence first and borrows the other side's only when it has none. On the 20 rolling tests,
   own asks carry nearly all of this gain ($57.00 to $51.50). Bathrooms alone give $57.00 to $56.50 and add little
   once own asks are in. Shifting each side separately beat one shared shift in 8 windows, tied 10 and lost 2
   ($51.50 to $51.00 pooled).
7. A building with few adverts is pulled toward its neighbours, which count as half an advert, and nearby buildings
   count for less with distance, halving every 500 metres.

Settings were chosen on three earlier folds (validating on Aug–Oct 2025, Nov 2025–Jan 2026 and Feb–Apr 2026)
or on the 20 rolling tests, all before May 2026. The table below scores each version on May to July 2026, which
was looked at across versions, so read it as a development record rather than a clean test. The final rents
refit on every advert up to 31 July 2026. Nothing dated after that is used.

| Step | Typical miss | Within $100 | R squared |
|---|---|---|---|
| Suburb, bedrooms and parking (example) | $100.00 | 56.8% | 0.645 |
| Same building, last year of adverts only | $59.41 | 69.4% | 0.781 |
| Same building, older asks brought forward | $53.48 | 72.0% | 0.820 |
| Plus nearest buildings | $52.29 | 72.2% | 0.834 |
| Plus the flat's own past asks and bathrooms | $45.00 | 77.1% | 0.872 |
| Plus thin buildings pulled toward their neighbours | $45.44 | 77.2% | 0.871 |
| Plus each parking side shifted by its own evidence | $45.37 | 77.4% | 0.871 |

The last step was chosen on the earlier folds ($49.45 to $48.35) and won or tied in six of seven earlier quarters.
It costs 44 cents on the May–July headline but helps the hard cases, scored separately by `analysis/validate_groups.py`:

| May–July group | Adverts | Median miss before / after | Mean miss before / after | Within $100 before / after |
|---|---|---|---|---|
| Flat never advertised before | 1,225 | $64.12 / $61.47 | $105.06 / $103.83 | 67.3% / 68.1% |
| Building, no matching flat type | 120 | $101.25 / $108.41 | $155.62 / $165.16 | 50.0% / 48.3% |
| Building never advertised | 25 | $127.47 / $124.12 | $204.45 / $208.02 | 36.0% / 36.0% |

On the rent check, half of new adverts for a flat with its own advert history landed within a band 7.4% wide
around the estimate, against about 13% for a flat priced from its building alone.

## Layout

The repository root is the website, deployed as a static site on Vercel. The analysis lives in `analysis/`, which
`.vercelignore` keeps out of the deployment.

| File | What it is |
|---|---|
| `index.html` | Rent check: a tenant finds their flat, enters their rent and sees how it compares |
| `report.html` | Findings, separate check and method |
| `dashboard.html` | Summary dashboard |
| `analysis/rent_model.py` | The estimator (`RentModel`) and the `check` scoring function |
| `analysis/make_rents.py` | Refits as at 31 July 2026 and writes `analysis/rents_<team>.csv` |
| `analysis/make_report.py` | Builds `report.html` |
| `analysis/make_dashboard.py` | Builds `dashboard.html` |
| `analysis/make_rent_check.py` | Builds `index.html` |
| `analysis/tune_fields.py` | Chooses the own-advert weight and bathroom minimum on the three earlier folds |
| `analysis/tune_sparse.py` | Chooses the pull toward neighbours and the distance weighting on the same folds |
| `analysis/tune_premium.py` | Tests forcing a car space to price above no car space (it costs accuracy, so not used) |
| `analysis/validate_rolling.py` | 20 rolling two-month tests before May 2026: each step, each parking side, and groups by the evidence used |
| `analysis/tune_horizon.py` | Tests lifting both rents for growth after the as-at date (it lost on the May–July check, so it is off) |
| `analysis/validate_groups.py` | Scores never-advertised flats and buildings separately from the headline |
| `analysis/make_pitch.py` | Builds `pitch.pdf` |
| `analysis/baseline_rent.ipynb` | Reproduces the example's $100 baseline, then each improvement step |
| `analysis/rents_<team>.csv` | `gnaf_id, rent_with_car_space, rent_without_car_space` for all 65,777 flats |

## Running it

Put the three supplied CSVs in `analysis/` (`rents-past-leases-city-of-sydney.csv`,
`rents-input-flats-city-of-sydney.csv`, `blocks-homes-and-people-2021-2026.csv`), then from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install pandas numpy jupyter
.venv/bin/python analysis/make_rents.py --team <team-name>
.venv/bin/python analysis/make_report.py
.venv/bin/python analysis/make_dashboard.py
.venv/bin/python analysis/make_rent_check.py
```

Tested with Python 3.9.6, pandas 2.3.3 and numpy 2.0.2. A full run takes under a minute.

## Data rules

The supplied CSVs are for use on the day only, so they are not republished here and are listed in `.gitignore`.
No API keys or API output are stored in this repository, and the live for-rent listings endpoint was not used.
