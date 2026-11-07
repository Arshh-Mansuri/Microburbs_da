"""Tune the pull toward neighbours and the distance weighting on earlier folds only.

    python analysis/tune_sparse.py
"""

from __future__ import annotations

import itertools

import pandas as pd

import rent_model as rm
from tune_fields import FOLDS
from validate_groups import score


def main() -> None:
    leases = rm.load_leases()
    leases = leases.loc[leases["listing_date"] <= FOLDS[0][1]]
    rows = []
    for shrink, half, neighbours in itertools.product([0.0, 0.5, 1.0, 2.0, 4.0], [None, 250, 500], [10, 20]):
        table = score(leases, FOLDS, shrink_adverts=shrink, distance_half_m=half, neighbours=neighbours)
        by = table.set_index("group")
        rows.append({
            "shrink": shrink, "half_m": half, "neighbours": neighbours,
            "all": by.loc["All later adverts", "median miss"],
            "all_within": by.loc["All later adverts", "within $100"],
            "new_flat": by.loc["Flat never advertised before", "median miss"],
            "new_flat_mean": by.loc["Flat never advertised before", "mean miss"],
            "no_type": by.loc["Building, no matching flat type", "median miss"],
            "new_building": by.loc["Building never advertised", "median miss"],
        })
        print(rows[-1], flush=True)
    print(pd.DataFrame(rows).sort_values(["all", "new_flat"]).to_string(index=False))


if __name__ == "__main__":
    main()
