"""Write the hand-in file: two weekly rents for every flat.

    python make_rents.py --team your-team-name

The rule is frozen before this runs. Here it is refitted on every advert dated
by 31 July 2026 and applied to all 65,777 flats. The held-out figures reported
in the notebook come from the May to July check and are not refitted.
"""

from __future__ import annotations

import argparse

import pandas as pd

import rent_model as rm

AS_AT = pd.Timestamp("2026-07-31")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", required=True, help="team name, lowercase, spaces as hyphens")
    parser.add_argument("--folder", default=str(rm.DATA_DIR))
    args = parser.parse_args()

    leases = rm.load_leases(args.folder)
    flats = rm.load_flats(args.folder)

    too_late = leases["listing_date"] > AS_AT
    if too_late.any():
        raise SystemExit(f"{too_late.sum()} adverts are dated after {AS_AT.date()}")

    model = rm.RentModel(as_at=AS_AT).fit(leases)
    rents = model.predict_both(flats)

    out = pd.DataFrame(
        {
            "gnaf_id": flats["gnaf_id"],
            "rent_with_car_space": (rents["rent_with_car_space"] * 2).round() / 2,
            "rent_without_car_space": (rents["rent_without_car_space"] * 2).round() / 2,
        }
    )

    if len(out) != len(flats):
        raise SystemExit("row count does not match the input")
    if out["gnaf_id"].duplicated().any():
        raise SystemExit("duplicate gnaf_id")
    if out[["rent_with_car_space", "rent_without_car_space"]].isna().any().any():
        raise SystemExit("blank rent")

    team = args.team.strip().lower().replace(" ", "-")
    path = f"{args.folder}/rents_{team}.csv"
    out.to_csv(path, index=False)

    print(f"Adverts used: {model.adverts_used:,}")
    print(f"Flats written: {len(out):,} to {path}")
    print(rents["source"].value_counts().to_string())


if __name__ == "__main__":
    main()
