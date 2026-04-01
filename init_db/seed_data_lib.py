import csv
import datetime as dt
import random
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

APP_BASES = [
    "Canvas",
    "Pulse",
    "Orbit",
    "Hive",
    "Echo",
    "Bloom",
    "Forge",
    "Atlas",
]
PLATFORMS = ("iOS", "Android")
COUNTRIES = ("US", "GB", "DE", "FR", "CA", "JP")
COUNTRY_INSTALL_MULTIPLIERS = {
    "US": 1.35,
    "GB": 0.82,
    "DE": 0.78,
    "FR": 0.76,
    "CA": 0.69,
    "JP": 0.74,
}
COUNTRY_REVENUE_MULTIPLIERS = {
    "US": 1.40,
    "GB": 1.08,
    "DE": 1.05,
    "FR": 0.98,
    "CA": 1.02,
    "JP": 1.18,
}


class SeedRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str
    platform: str
    date: dt.date
    country: str
    installs: int
    in_app_revenue: float
    ads_revenue: float
    ua_cost: float

    def as_dict(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "platform": self.platform,
            "date": self.date.isoformat(),
            "country": self.country,
            "installs": self.installs,
            "in_app_revenue": round(self.in_app_revenue, 2),
            "ads_revenue": round(self.ads_revenue, 2),
            "ua_cost": round(self.ua_cost, 2),
        }


def build_seed_rows(seed: int = 20250331) -> list[dict[str, object]]:
    rng = random.Random(seed)
    start_date = dt.date(2020, 1, 1)
    end_date = dt.date(2026, 3, 31)
    rows: list[dict[str, object]] = []

    # Assign platforms to apps randomly - some apps on both, some on only one platform
    app_platforms: dict[str, list[str]] = {}
    for base_name in APP_BASES:
        platform_choice = rng.choice(["both", "iOS", "Android"])
        if platform_choice == "both":
            app_platforms[base_name] = list(PLATFORMS)
        elif platform_choice == "iOS":
            app_platforms[base_name] = ["iOS"]
        else:
            app_platforms[base_name] = ["Android"]

    current = start_date
    while current <= end_date:
        seasonal = 1.0 + (0.14 if current.month in {11, 12} else 0.04 if current.month in {6, 7, 8} else 0.0)
        for base_name in APP_BASES:
            for platform in app_platforms[base_name]:
                app_name = f"{base_name}"
                app_factor = 0.82 + (APP_BASES.index(base_name) * 0.07)
                platform_install_factor = 1.28 if platform == "Android" else 0.88
                iap_per_install = 0.19 if platform == "iOS" else 0.07
                ads_per_install = 0.045 if platform == "Android" else 0.018
                for country in COUNTRIES:
                    daily_noise = rng.uniform(0.92, 1.08)
                    installs = int(
                        max(
                            18,
                            round(
                                85
                                * app_factor
                                * platform_install_factor
                                * COUNTRY_INSTALL_MULTIPLIERS[country]
                                * seasonal
                                * daily_noise
                            ),
                        )
                    )
                    in_app_revenue = (
                        installs * iap_per_install * COUNTRY_REVENUE_MULTIPLIERS[country] * rng.uniform(0.94, 1.06)
                    )
                    ads_revenue = (
                        installs * ads_per_install * COUNTRY_REVENUE_MULTIPLIERS[country] * rng.uniform(0.94, 1.06)
                    )
                    expected_revenue = in_app_revenue + ads_revenue
                    ua_cost = expected_revenue * (0.41 if platform == "iOS" else 0.56) * rng.uniform(0.95, 1.05)
                    rows.append(
                        SeedRow(
                            app_name=app_name,
                            platform=platform,
                            date=current,
                            country=country,
                            installs=installs,
                            in_app_revenue=in_app_revenue,
                            ads_revenue=ads_revenue,
                            ua_cost=ua_cost,
                        ).as_dict()
                    )
        current += dt.timedelta(days=1)
    return rows


def write_csv(path: Path) -> None:
    rows = build_seed_rows()
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def chunked(rows: Iterable[dict[str, object]], size: int) -> Iterable[list[dict[str, object]]]:
    chunk: list[dict[str, object]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
