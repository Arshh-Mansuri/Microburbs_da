"""Score the estimate separately for the cases the headline number hides.

    python analysis/validate_groups.py

Groups, decided only from adverts before each test window:
  - every later advert
  - flats whose own address never advertised before (the 16,094 never-advertised flats look like this)
  - buildings with no earlier advert for the same bedrooms and parking
  - buildings with no earlier advert at all
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import rent_model as rm
from tune_fields import FOLDS

HELD_OUT = (pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-31"))


def groups(earlier: pd.DataFrame, later: pd.DataFrame) -> dict:
    seen_flat = later["gnaf_id"].isin(earlier["gnaf_id"])
    seen_type = pd.MultiIndex.from_frame(later[["building_address", "bedrooms", "car_space"]]).isin(
        pd.MultiIndex.from_frame(earlier[["building_address", "bedrooms", "car_space"]])
    )
    seen_building = later["building_address"].isin(earlier["building_address"])
    return {
        "All later adverts": np.ones(len(later), bool),
        "Flat never advertised before": ~seen_flat.to_numpy(),
        "Building, no matching flat type": ~seen_type,
        "Building never advertised": ~seen_building.to_numpy(),
    }


def summarise(misses: dict) -> pd.DataFrame:
    rows = []
    for name, miss in misses.items():
        miss = np.concatenate(miss)
        rows.append({
            "group": name,
            "adverts": len(miss),
            "median miss": round(float(np.median(miss)), 2),
            "mean miss": round(float(np.mean(miss)), 2),
            "within $100": f"{np.mean(miss <= 100) * 100:.1f}%",
        })
    return pd.DataFrame(rows)


def score(leases: pd.DataFrame, windows, **settings) -> pd.DataFrame:
    misses = {}
    for start, end in windows:
        earlier = leases.loc[leases["listing_date"] < start]
        later = leases.loc[leases["listing_date"].between(start, end)]
        model = rm.RentModel(as_at=start - pd.Timedelta(days=1), **settings).fit(earlier)
        miss = np.abs(model.predict(later).to_numpy() - later["weekly_rent"].to_numpy())
        for name, chosen in groups(earlier, later).items():
            misses.setdefault(name, []).append(miss[chosen])
    return summarise(misses)


def main() -> None:
    leases = rm.load_leases()
    print("Earlier folds (Aug 2025 to Apr 2026, used for tuning)")
    print(score(leases, FOLDS).to_string(index=False))
    print("\nMay to July 2026 check")
    print(score(leases, [HELD_OUT]).to_string(index=False))


if __name__ == "__main__":
    main()
