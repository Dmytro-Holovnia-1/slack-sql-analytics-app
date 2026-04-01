import asyncio
import csv
import datetime as dt
import os
import sys
from pathlib import Path
from typing import TypedDict, cast

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CsvSeedRow(TypedDict):
    app_name: str
    platform: str
    date: str
    country: str
    installs: str
    in_app_revenue: str
    ads_revenue: str
    ua_cost: str


def _database_dsn() -> str:
    user = os.getenv("POSTGRES_USER", "rounds_admin")
    password = os.getenv("POSTGRES_PASSWORD", "rounds_admin_password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "rounds_analytics")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def read_seed_rows() -> list[CsvSeedRow]:
    csv_path = ROOT / "init_db" / "app_metrics.csv"
    if not csv_path.exists():
        from init_db.seed_data_lib import write_csv

        write_csv(csv_path)
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [cast(CsvSeedRow, row) for row in csv.DictReader(f)]


async def seed_database(dsn: str | None = None) -> int:
    rows = read_seed_rows()
    target_dsn = dsn or _database_dsn()
    # asyncpg expects postgresql:// or postgres://, not postgresql+asyncpg://
    if target_dsn.startswith("postgresql+asyncpg://"):
        target_dsn = target_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(target_dsn)
    try:
        await conn.execute("TRUNCATE TABLE app_metrics RESTART IDENTITY")
        for start in range(0, len(rows), 500):
            batch = rows[start : start + 500]
            await conn.executemany(
                """
                INSERT INTO app_metrics (
                    app_name,
                    platform,
                    date,
                    country,
                    installs,
                    in_app_revenue,
                    ads_revenue,
                    ua_cost
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        row["app_name"],
                        row["platform"],
                        dt.date.fromisoformat(row["date"]),
                        row["country"],
                        int(row["installs"]),
                        float(row["in_app_revenue"]),
                        float(row["ads_revenue"]),
                        float(row["ua_cost"]),
                    )
                    for row in batch
                ],
            )
    finally:
        await conn.close()
    return len(rows)


def write_preview_json(path: Path) -> None:
    import json

    rows = read_seed_rows()[:25]
    path.write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    inserted = asyncio.run(seed_database())
    print(f"Seeded {inserted} rows into app_metrics")
