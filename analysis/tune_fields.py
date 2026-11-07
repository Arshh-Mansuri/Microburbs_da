"""Choose the own-advert weight and the bathroom split on earlier folds only.

    python analysis/tune_fields.py

Each fold fits on adverts before its start and scores the three months after.
The May to July 2026 adverts are never read here.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import rent_model as rm

FOLDS = [
    (pd.Timestamp("2026-02-01"), pd.Timestamp("2026-04-30")),
    (pd.Timestamp("2025-11-01"), pd.Timestamp("2026-01-31")),
    (pd.Timestamp("2025-08-01"), pd.Timestamp("2025-10-31")),
]


def score(leases, **settings):
    misses, ratios = [], []
    for start, end in FOLDS:
        earlier = leases.loc[leases["listing_date"] < start]
        later = leases.loc[leases["listing_date"].between(start, end)]
        model = rm.RentModel(as_at=start - pd.Timedelta(days=1), **settings).fit(earlier)
        rent = model.predict(later)
        misses.append((rent - later["weekly_rent"]).abs())
        ratios.append(later["weekly_rent"] / rent)
    miss, ratio = pd.concat(misses), pd.concat(ratios)
    q25, q75 = np.quantile(ratio, [0.25, 0.75])
    return {
        "miss": round(miss.median(), 2),
        "within_100": round((miss <= 100).mean() * 100, 1),
        "middle_half_width_pct": round((q75 - q25) * 100, 1),
    }


def main() -> None:
    leases = rm.load_leases()
    leases = leases.loc[leases["listing_date"] < FOLDS[0][1] + pd.Timedelta(days=1)]
    rows = []
    for own_weight, use_bathrooms, min_bathroom_ads in itertools.product(
        [0.0, 0.25, 0.5, 0.75, 1.0], [False, True], [1, 3]
    ):
        if not use_bathrooms and min_bathroom_ads != 1:
            continue
        found = score(
            leases, own_weight=own_weight, use_bathrooms=use_bathrooms, min_bathroom_ads=min_bathroom_ads
        )
        rows.append({"own_weight": own_weight, "bathrooms": use_bathrooms, "min_bath_ads": min_bathroom_ads, **found})
        print(rows[-1], flush=True)
    table = pd.DataFrame(rows).sort_values("miss")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
