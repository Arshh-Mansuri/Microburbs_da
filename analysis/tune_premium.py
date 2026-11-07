"""Test ways to stop a car space pricing below no car space, on earlier folds only.

    python analysis/tune_premium.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import rent_model as rm
from tune_fields import FOLDS


def fixes(both: pd.DataFrame, model: rm.RentModel, adverts: pd.DataFrame) -> dict:
    with_parking = both["rent_with_car_space"].to_numpy()
    without_parking = both["rent_without_car_space"].to_numpy()
    flipped = with_parking < without_parking
    middle = (with_parking + without_parking) / 2
    gaps = np.array([
        model._bounded_gap(suburb, bedrooms, anchor)
        for suburb, bedrooms, anchor in zip(adverts["suburb"], adverts["bedrooms"], middle)
    ])
    return {
        "keep as is": (with_parking, without_parking),
        "raise with to without": (np.maximum(with_parking, without_parking), without_parking),
        "lower without to with": (with_parking, np.minimum(with_parking, without_parking)),
        "both to the middle": (np.where(flipped, middle, with_parking), np.where(flipped, middle, without_parking)),
        "middle plus or minus half the local gap": (
            np.where(flipped, middle + gaps / 2, with_parking),
            np.where(flipped, middle - gaps / 2, without_parking),
        ),
    }


def main() -> None:
    leases = rm.load_leases()
    totals = {}
    for start, end in FOLDS:
        earlier = leases.loc[leases["listing_date"] < start]
        later = leases.loc[leases["listing_date"].between(start, end)]
        model = rm.RentModel(as_at=start - pd.Timedelta(days=1)).fit(earlier)
        both = model.predict_both(later)
        for name, (with_parking, without_parking) in fixes(both, model, later).items():
            rent = np.where(later["car_space"] == 1, with_parking, without_parking)
            totals.setdefault(name, []).append(np.abs(rent - later["weekly_rent"].to_numpy()))
    for name, misses in totals.items():
        miss = np.concatenate(misses)
        print(f"{name:42s} miss ${np.median(miss):.2f}  within $100 {np.mean(miss <= 100) * 100:.1f}%")


if __name__ == "__main__":
    main()
