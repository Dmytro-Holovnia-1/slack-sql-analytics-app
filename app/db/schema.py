DB_SCHEMA = """
CREATE TABLE app_metrics (
    id SERIAL PRIMARY KEY,
    app_name TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('iOS', 'Android')),
    date DATE NOT NULL,
    country TEXT NOT NULL CHECK (country IN ('US', 'GB', 'DE', 'FR', 'CA', 'JP')),
    installs INTEGER NOT NULL DEFAULT 0,
    in_app_revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
    ads_revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
    ua_cost NUMERIC(12, 2) NOT NULL DEFAULT 0
);
""".strip()
