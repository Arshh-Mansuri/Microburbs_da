"""Weekly asking rent for City of Sydney flats.

A flat's rent is the median weekly ask of earlier adverts for the same building,
bedroom count and parking answer. Older asks are brought forward to the as-at
date with a city-wide quarterly index before they are pooled, and weighted down
as they age. Where a building has only ever advertised one parking answer, the
other rent is that one plus a parking gap measured on comparable flats.
Buildings with no advert at all borrow from the nearest buildings that have
one, then fall back to their suburb.

Nothing dated after the as-at date is read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# The supplied CSVs sit beside this file. Built pages go to the site root above it.
DATA_DIR = Path(__file__).resolve().parent
SITE_DIR = DATA_DIR.parent

LEASES = "rents-past-leases-city-of-sydney.csv"
FLATS = "rents-input-flats-city-of-sydney.csv"

# Chosen on earlier adverts only, never on the held-out quarter.
MAX_AGE_YEARS = 3
HALF_LIFE_YEARS = 3
MIN_BUILDING_ADS = 1
MIN_SUBURB_ADS = 10
MIN_INDEX_ADS = 30
NEIGHBOURS = 10
NEIGHBOUR_REACH_M = 1000

# A derived car space never lowers the ask, and never adds more than this share
# of it. Thin groups otherwise throw out gaps wider than the rent itself.
MAX_GAP_SHARE = 0.25

# Metres per degree near Sydney, for straight-line distances between buildings.
METRES_PER_DEGREE_LAT = 110_950
METRES_PER_DEGREE_LON = 92_390


def load_leases(folder: str | Path = DATA_DIR) -> pd.DataFrame:
    """Past adverts that carry a bedroom count and a parking answer."""
    leases = pd.read_csv(f"{folder}/{LEASES}")
    leases["listing_date"] = pd.to_datetime(leases["listing_date"])
    for column in ("bedrooms", "car_space", "weekly_rent"):
        leases[column] = pd.to_numeric(leases[column], errors="coerce")
    usable = leases["bedrooms"].notna() & leases["car_space"].isin([0, 1])
    return leases.loc[usable].copy()


def load_flats(folder: str | Path = DATA_DIR) -> pd.DataFrame:
    flats = pd.read_csv(f"{folder}/{FLATS}")
    for column in ("bedrooms", "car_space", "floor_level"):
        flats[column] = pd.to_numeric(flats[column], errors="coerce")
    return flats


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    return float(values[np.searchsorted(np.cumsum(weights), weights.sum() / 2.0)])


@dataclass
class RentModel:
    as_at: pd.Timestamp
    max_age_years: int = MAX_AGE_YEARS
    half_life_years: float = HALF_LIFE_YEARS
    min_building_ads: int = MIN_BUILDING_ADS
    min_suburb_ads: int = MIN_SUBURB_ADS
    neighbours: int = NEIGHBOURS
    neighbour_reach_m: float = NEIGHBOUR_REACH_M

    index: pd.Series = None
    nearby: dict = field(default_factory=dict)
    adverts_used: int = 0
    building: dict = field(default_factory=dict)
    suburb: dict = field(default_factory=dict)
    suburb_any_parking: dict = field(default_factory=dict)
    by_bedrooms: dict = field(default_factory=dict)
    gap_by_suburb: dict = field(default_factory=dict)
    gap_by_bedrooms: dict = field(default_factory=dict)
    gap_typical: float = 0.0
    citywide: float = 0.0

    def _as_at_prices(self, leases: pd.DataFrame) -> pd.DataFrame:
        """Earlier adverts, brought forward to the as-at date and aged down."""
        window = leases["listing_date"].between(
            self.as_at - pd.DateOffset(years=self.max_age_years), self.as_at
        )
        ads = leases.loc[window].copy()
        ads["quarter"] = ads["listing_date"].dt.to_period("Q")

        quarterly = ads.groupby("quarter")["weekly_rent"].agg(median="median", n="size")
        quarterly = quarterly.loc[quarterly["n"] >= MIN_INDEX_ADS, "median"]
        latest = self.as_at.to_period("Q")
        if latest not in quarterly.index:
            latest = quarterly.index.max()
        self.index = quarterly.loc[latest] / quarterly

        factor = ads["quarter"].map(self.index)
        ads = ads.loc[factor.notna()].copy()
        ads["rent_now"] = ads["weekly_rent"] * factor.dropna().to_numpy()
        if self.half_life_years is None:
            ads["weight"] = 1.0
        else:
            days_old = (self.as_at - ads["listing_date"]).dt.days
            ads["weight"] = 0.5 ** (days_old / (self.half_life_years * 365.25))
        return ads

    def fit(self, leases: pd.DataFrame) -> "RentModel":
        ads = self._as_at_prices(leases)

        def medians(keys, floor):
            return {
                key: weighted_median(group["rent_now"].to_numpy(), group["weight"].to_numpy())
                for key, group in ads.groupby(keys, observed=True)
                if len(group) >= floor
            }

        def parking_gaps(keys, floor):
            found = {}
            for key, group in ads.groupby(keys, observed=True):
                with_parking = group.loc[group["car_space"] == 1]
                without_parking = group.loc[group["car_space"] == 0]
                if len(with_parking) >= floor and len(without_parking) >= floor:
                    found[key] = weighted_median(
                        with_parking["rent_now"].to_numpy(), with_parking["weight"].to_numpy()
                    ) - weighted_median(
                        without_parking["rent_now"].to_numpy(), without_parking["weight"].to_numpy()
                    )
            return found

        self.building = medians(["building_address", "bedrooms", "car_space"], self.min_building_ads)
        self.suburb = medians(["suburb", "bedrooms", "car_space"], self.min_suburb_ads)
        self.suburb_any_parking = medians(["suburb", "bedrooms"], self.min_suburb_ads)
        self.by_bedrooms = medians("bedrooms", self.min_suburb_ads)

        self.gap_by_suburb = parking_gaps(["suburb", "bedrooms"], self.min_suburb_ads)
        self.gap_by_bedrooms = parking_gaps("bedrooms", self.min_suburb_ads)
        self.gap_typical = float(np.median(list(self.gap_by_suburb.values())))

        located = ads.dropna(subset=["latitude", "longitude"])
        places = located.groupby("building_address")[["latitude", "longitude"]].median()
        self.nearby = {}
        for (building_address, bedrooms, car_space), rent in self.building.items():
            if building_address in places.index:
                lat, lon = places.loc[building_address]
                self.nearby.setdefault((bedrooms, car_space), []).append(
                    (lat * METRES_PER_DEGREE_LAT, lon * METRES_PER_DEGREE_LON, rent)
                )
        self.nearby = {key: np.array(rows) for key, rows in self.nearby.items()}

        self.citywide = float(ads["rent_now"].median())
        self.adverts_used = len(ads)
        return self

    def _near(self, bedrooms: float, car_space: float, latitude: float, longitude: float):
        """Median rent of the closest buildings that advertised this flat type."""
        if self.neighbours <= 0 or pd.isna(latitude) or pd.isna(longitude):
            return None
        rows = self.nearby.get((bedrooms, car_space))
        if rows is None:
            return None
        distance = np.hypot(
            rows[:, 0] - latitude * METRES_PER_DEGREE_LAT,
            rows[:, 1] - longitude * METRES_PER_DEGREE_LON,
        )
        closest = np.argsort(distance)[: self.neighbours]
        closest = closest[distance[closest] <= self.neighbour_reach_m]
        if len(closest) == 0:
            return None
        return float(np.median(rows[closest, 2]))

    @staticmethod
    def _nearest(table: dict, bedrooms: float):
        """The closest bedroom count that has evidence, for the rare large flats."""
        if not table or pd.isna(bedrooms):
            return None
        return table[min(table, key=lambda known: abs(known - bedrooms))]

    def parking_gap(self, suburb: str, bedrooms: float) -> float:
        """What a car space adds, from the closest group that advertised both."""
        gap = self.gap_by_suburb.get((suburb, bedrooms))
        if gap is None:
            gap = self.gap_by_bedrooms.get(bedrooms)
        if gap is None:
            gap = self._nearest(self.gap_by_bedrooms, bedrooms)
        if gap is None:
            gap = self.gap_typical
        return gap

    def _bounded_gap(self, suburb: str, bedrooms: float, anchor: float) -> float:
        return min(max(self.parking_gap(suburb, bedrooms), 0.0), MAX_GAP_SHARE * anchor)

    def _pair(self, building_address, bedrooms, suburb, latitude=np.nan, longitude=np.nan):
        with_parking = self.building.get((building_address, bedrooms, 1.0))
        without_parking = self.building.get((building_address, bedrooms, 0.0))
        if with_parking is not None and without_parking is not None:
            return with_parking, without_parking, "building advertised both"
        if with_parking is not None:
            gap = self._bounded_gap(suburb, bedrooms, with_parking)
            return with_parking, with_parking - gap, "building, parking gap"
        if without_parking is not None:
            gap = self._bounded_gap(suburb, bedrooms, without_parking)
            return without_parking + gap, without_parking, "building, parking gap"

        with_parking = self._near(bedrooms, 1.0, latitude, longitude)
        without_parking = self._near(bedrooms, 0.0, latitude, longitude)
        if with_parking is not None and without_parking is not None:
            return with_parking, without_parking, "nearby buildings"
        if with_parking is not None:
            gap = self._bounded_gap(suburb, bedrooms, with_parking)
            return with_parking, with_parking - gap, "nearby buildings, parking gap"
        if without_parking is not None:
            gap = self._bounded_gap(suburb, bedrooms, without_parking)
            return without_parking + gap, without_parking, "nearby buildings, parking gap"

        with_parking = self.suburb.get((suburb, bedrooms, 1.0))
        without_parking = self.suburb.get((suburb, bedrooms, 0.0))
        if with_parking is not None and without_parking is not None:
            return with_parking, without_parking, "suburb advertised both"

        middle = self.suburb_any_parking.get((suburb, bedrooms))
        source = "suburb, parking gap"
        if middle is None:
            middle = self.by_bedrooms.get(bedrooms)
            source = "bedrooms, parking gap"
        if middle is None:
            middle = self._nearest(self.by_bedrooms, bedrooms)
            source = "nearest bedroom count"
        if middle is None:
            middle = self.citywide
            source = "citywide"
        gap = self._bounded_gap(suburb, bedrooms, middle)
        return middle + gap / 2, middle - gap / 2, source

    def predict_both(self, flats: pd.DataFrame) -> pd.DataFrame:
        """Weekly rent with a car space and without, one row per flat."""
        pairs = [
            self._pair(*row)
            for row in zip(
                flats["building_address"],
                flats["bedrooms"],
                flats["suburb"],
                flats["latitude"],
                flats["longitude"],
            )
        ]
        return pd.DataFrame(
            {
                "rent_with_car_space": [p[0] for p in pairs],
                "rent_without_car_space": [p[1] for p in pairs],
                "source": [p[2] for p in pairs],
            },
            index=flats.index,
        )

    def predict(self, adverts: pd.DataFrame) -> pd.Series:
        """The rent for the parking answer each advert carries."""
        both = self.predict_both(adverts)
        chosen = np.where(
            adverts["car_space"] == 1,
            both["rent_with_car_space"],
            both["rent_without_car_space"],
        )
        return pd.Series(chosen, index=adverts.index)


def check(adverts: pd.DataFrame, rent: pd.Series) -> dict:
    """Held-out accuracy against the rent each advert actually asked."""
    asked = adverts["weekly_rent"]
    miss = (rent - asked).abs()
    within = miss <= 100
    r2 = 1 - ((asked - rent) ** 2).sum() / ((asked - asked.mean()) ** 2).sum()
    return {
        "Later adverts": f"{len(adverts):,}",
        "Typical miss": f"${miss.median():,.2f}",
        "Within $100": f"{within.mean():.1%} ({within.sum():,} of {len(adverts):,})",
        "R squared": f"{r2:.3f}",
        "Typical miss, no parking": f"${miss[adverts['car_space'] == 0].median():,.2f}",
        "Typical miss, with parking": f"${miss[adverts['car_space'] == 1].median():,.2f}",
    }
