import pytest

from app.services.query_service import DatabaseQueryService, UnsafeSQL


@pytest.mark.asyncio
async def test_query_service_blocks_unsafe_sql():
    # Initialize service without real DB engine
    service = DatabaseQueryService(engine=None, statement_timeout_ms=5000)

    unsafe_queries = [
        "DROP TABLE app_metrics;",
        "UPDATE app_metrics SET installs = 0;",
        "DELETE FROM app_metrics WHERE country = 'US';",
        "INSERT INTO app_metrics (app_name) VALUES ('Test');",
        "ALTER TABLE app_metrics DROP COLUMN installs;",
        "TRUNCATE TABLE app_metrics;",
    ]

    for query in unsafe_queries:
        with pytest.raises(UnsafeSQL, match="Only SELECT queries are allowed"):
            await service.execute_readonly_sql(query)


@pytest.mark.asyncio
async def test_query_service_allows_select():
    service = DatabaseQueryService(engine=None, statement_timeout_ms=5000)

    with pytest.raises(AttributeError):
        await service.execute_readonly_sql("SELECT * FROM app_metrics LIMIT 10;")

    with pytest.raises(AttributeError):
        await service.execute_readonly_sql("WITH cte AS (SELECT 1) SELECT * FROM cte;")
