# Weekly rents for every City of Sydney flat

Microburbs Hackathon, task 4. We estimate two weekly asking rents, one with a car space and one without, for all
65,777 flats in the City of Sydney as at 31 July 2026.

On a separate check (trained on adverts to 30 April 2026, then tested on 3,954 adverts from May to July 2026), the
typical miss is **$45.00 a week**, compared with $100.00 for the example suburb method. **77.1%** of estimates land
within $100, compared with 56.8% for the example, and R squared is 0.872.

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
   its own asks, brought forward the same way, take 75% of the weight and the building the rest.

All settings were chosen on three earlier folds (validating on Aug–Oct 2025, Nov 2025–Jan 2026 and Feb–Apr 2026).
The May–July 2026 adverts were used once, to score the frozen rule. The final rents refit on every advert up to
31 July 2026. Nothing dated after that is used.

| Step | Typical miss | Within $100 | R squared |
|---|---|---|---|
| Suburb, bedrooms and parking (example) | $100.00 | 56.8% | 0.645 |
| Same building, last year of adverts only | $59.41 | 69.4% | 0.781 |
| Same building, older asks brought forward | $53.48 | 72.0% | 0.820 |
| Plus nearest buildings | $52.29 | 72.2% | 0.834 |
| Plus the flat's own past asks and bathrooms | $45.00 | 77.1% | 0.872 |

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
