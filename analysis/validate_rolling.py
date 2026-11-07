"""Rolling, time-ordered scores grouped by the evidence the fitted model actually used.

    python analysis/validate_rolling.py

Each window fits on adverts up to the end of a month and scores the next two
months, like the hand-in. Windows stop before May 2026, so this never reads the
May to July check. Groups come from each prediction's source, so they reflect
the three-year window and borrowing across parking, not just earlier adverts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import rent_model as rm

CUTOFFS = pd.date_range("2024-07-31", "2026-02-28", freq="ME")

VARIANTS = {
    "building and neighbours only": {"own_weight": 0.0, "bathrooms": False, "side_shifts": False},
    "plus bathrooms": {"own_weight": 0.0, "bathrooms": True, "side_shifts": False},
    "plus own adverts": {"own_weight": rm.OWN_WEIGHT, "bathrooms": False, "side_shifts": False},
    "plus both, shared shift (previous)": {"own_weight": rm.OWN_WEIGHT, "bathrooms": True, "side_shifts": False},
    "plus both, shift per parking side (current)": {"own_weight": rm.OWN_WEIGHT, "bathrooms": True, "side_shifts": True},
}


def groups(source: pd.Series, car_space: pd.Series) -> dict:
    own = source.str.contains("own adverts")
    building = source.str.startswith("building")
    nearby = source.str.startswith("nearby")
    return {
        "all": np.ones(len(source), bool),
        "no parking": (car_space == 0).to_numpy(),
        "with parking": (car_space == 1).to_numpy(),
        "no own history": (~own).to_numpy(),
        "no usable building history": (~building).to_numpy(),
        "no usable nearby match": (~building & ~nearby).to_numpy(),
    }


def main() -> None:
    leases = rm.load_leases()
    misses = {}
    for cutoff in CUTOFFS:
        start, end = cutoff + pd.Timedelta(days=1), cutoff + pd.offsets.MonthEnd(2)
        earlier = leases.loc[leases["listing_date"] <= cutoff]
        later = leases.loc[leases["listing_date"].between(start, end)]
        model = rm.RentModel(as_at=cutoff).fit(earlier)
        bathrooms_table = model.building_bathrooms
        asked = later["weekly_rent"].to_numpy()
        for name, variant in VARIANTS.items():
            model.own_weight = variant["own_weight"]
            model.building_bathrooms = bathrooms_table if variant["bathrooms"] else {}
            model.side_shifts = variant["side_shifts"]
            both = model.predict_both(later)
            rent = np.where(later["car_space"] == 1, both["rent_with_car_space"], both["rent_without_car_space"])
            miss = np.abs(np.round(rent * 2) / 2 - asked)
            if name.endswith("(current)"):
                chosen = groups(both["source"], later["car_space"])
            for group, rows in (chosen if name.endswith("(current)") else {}).items():
                misses.setdefault(("groups", group), []).append(miss[rows])
            misses.setdefault(name, []).append(miss)
            misses.setdefault((name, "no parking"), []).append(miss[(later["car_space"] == 0).to_numpy()])
            misses.setdefault((name, "with parking"), []).append(miss[(later["car_space"] == 1).to_numpy()])
        print(cutoff.date(), flush=True)

    def row(miss_list):
        per_window = [float(np.median(m)) for m in miss_list]
        pooled = np.concatenate(miss_list)
        return {"adverts": len(pooled), "median miss": np.median(pooled), "mean miss": pooled.mean(),
                "within $100": f"{np.mean(pooled <= 100):.1%}", "mean of window medians": np.mean(per_window)}

    print("\nVariants, pooled over 20 two-month windows")
    table = pd.DataFrame({name: row(misses[name]) for name in VARIANTS}).T
    for side in ("no parking", "with parking"):
        table[f"median, {side}"] = [np.median(np.concatenate(misses[(name, side)])) for name in VARIANTS]
    print(table.round(2).to_string())

    current = misses["plus both, shared shift (previous)"]
    sides = misses["plus both, shift per parking side (current)"]
    wins = sum(np.median(s) < np.median(c) for s, c in zip(sides, current))
    ties = sum(np.median(s) == np.median(c) for s, c in zip(sides, current))
    print(f"\nShift per parking side beats the shared shift in {wins} of 20 windows ({ties} ties)")

    print("\nCurrent model by the evidence it actually used")
    names = ["all", "no parking", "with parking", "no own history", "no usable building history",
             "no usable nearby match"]
    print(pd.DataFrame({g: row(misses[("groups", g)]) for g in names}).T.round(2).to_string())


if __name__ == "__main__":
    main()
