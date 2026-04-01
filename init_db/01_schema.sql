CREATE TABLE IF NOT EXISTS app_metrics (
    id BIGSERIAL PRIMARY KEY,
    app_name VARCHAR(100) NOT NULL,
    platform VARCHAR(10) NOT NULL CHECK (platform IN ('iOS', 'Android')),
    date DATE NOT NULL,
    country CHAR(2) NOT NULL CHECK (country IN ('US', 'GB', 'DE', 'FR', 'CA', 'JP')),
    installs INTEGER NOT NULL CHECK (installs >= 0),
    in_app_revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
    ads_revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
    ua_cost NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_app_metrics UNIQUE (app_name, platform, date, country)
);

CREATE INDEX IF NOT EXISTS idx_app_metrics_date_desc ON app_metrics (date DESC);
CREATE INDEX IF NOT EXISTS idx_app_metrics_platform ON app_metrics (platform);
CREATE INDEX IF NOT EXISTS idx_app_metrics_country_date_desc ON app_metrics (country, date DESC);
CREATE INDEX IF NOT EXISTS idx_app_metrics_app_platform ON app_metrics (app_name, platform);
