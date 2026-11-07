"""Does lifting every estimate for growth between the as-at date and the test window help?

    python analysis/tune_horizon.py

Mirrors the scored test: fit on adverts up to the end of a month, score the next
two months. Cut-offs run monthly and stop before the May to July 2026 check.

Rules compared, each using only adverts up to its own cut-off:
  - no lift
  - a flat lift
  - the seasonal lift: how far asks in the same two months a year earlier ran
    above an estimate fitted at that year's cut-off, scaled by a share
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import rent_model as rm

CUTOFFS = pd.date_range("2023-07-31", "2026-02-28", freq="ME")
FLAT_LIFTS = [0.005, 0.01, 0.015, 0.02]
SEASONAL_SHARES = [0.5, 0.75, 1.0]


def windows(leases):
    found = {}
    for cutoff in CUTOFFS:
        start, end = cutoff + pd.Timedelta(days=1), cutoff + pd.offsets.MonthEnd(2)
        earlier = leases.loc[leases["listing_date"] <= cutoff]
        later = leases.loc[leases["listing_date"].between(start, end)]
        rent = rm.RentModel(as_at=cutoff, lift=0.0).fit(earlier).predict(later).to_numpy()
        found[cutoff] = (rent, later["weekly_rent"].to_numpy())
    return found


def seasonal_lift(found, cutoff):
    """Median ask over estimate for the same window one year back, as a lift."""
    last_year = cutoff - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
    if last_year not in found:
        return None
    rent, asked = found[last_year]
    return float(np.median(asked / rent)) - 1


def miss(rent, asked, lift):
    return float(np.median(np.abs(np.round(rent * (1 + lift) * 2) / 2 - asked)))


def main() -> None:
    found = windows(rm.load_leases())
    rows = []
    for cutoff, (rent, asked) in found.items():
        lift = seasonal_lift(found, cutoff)
        if lift is None:
            continue
        row = {"cutoff": cutoff.date(), "adverts": len(asked), "seasonal lift": lift,
               "no lift": miss(rent, asked, 0.0)}
        for flat in FLAT_LIFTS:
            row[f"flat {flat:.1%}"] = miss(rent, asked, flat)
        for share in SEASONAL_SHARES:
            row[f"seasonal x{share}"] = miss(rent, asked, share * lift)
        rows.append(row)
    table = pd.DataFrame(rows)
    print(table.round(3).to_string(index=False))
    rules = [c for c in table.columns if c not in ("cutoff", "adverts", "seasonal lift")]
    print("\nMean miss over cut-offs:")
    print(table[rules].mean().round(2).to_string())
    print("\nWins over no lift:", {r: int((table[r] < table["no lift"]).sum()) for r in rules[1:]})
    july = table.loc[pd.to_datetime(table["cutoff"]).dt.month == 7]
    print("\nJuly cut-offs (the scored test's season):")
    print(july.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
