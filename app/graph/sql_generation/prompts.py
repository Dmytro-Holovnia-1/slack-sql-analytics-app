from app.graph.utils.prompts import json_output

SYSTEM_SQL_EXPERT = """
You are a PostgreSQL expert for a Slack analytics bot. Your task is to generate a SQL query based on the user's question and the conversation history. The SQL should be compatible with PostgreSQL and should query the provided database schema.

Database schema:
{schema}

Current date and time: {current_datetime}

Rules:
- Never write DML (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE).
- If the question is materially ambiguous, set needs_clarification=true and provide a short question with 2-3 concrete options.
- For optional missing filters, apply sensible defaults and disclose them.
- Use explicit column aliases.
- Return ONLY the raw SQL. No markdown, no explanation, no prefix.
- Use the current date above when interpreting relative dates like "yesterday", "last week", "today", etc.
""".strip()

FEW_SHOT_EXAMPLES_SQL_EXPERT = [
    # User explicitly states a date → INTERVAL is correct
    {
        "input": "How many active apps did we have in the last 30 days?",
        "output": json_output(
            {
                "clarification_question": None,
                "needs_clarification": False,
                "sql": (
                    "SELECT COUNT(DISTINCT app_name) AS active_apps "
                    "FROM app_metrics "
                    "WHERE date >= CURRENT_DATE - INTERVAL '30 days' "
                    "AND (installs > 0 OR in_app_revenue > 0 OR ads_revenue > 0) "
                ),
                "sql_title": "Active apps last 30 days",
            }
        ),
    },
    # No date mentioned → no WHERE date clause, query all data
    {
        "input": "List all apps sorted by total installs",
        "output": json_output(
            {
                "clarification_question": None,
                "needs_clarification": False,
                "sql": (
                    "SELECT app_name, SUM(installs) AS total_installs "
                    "FROM app_metrics "
                    "GROUP BY app_name "
                    "ORDER BY total_installs DESC "
                ),
                "sql_title": "Apps by total installs all time",
            }
        ),
    },
    # Ambiguous aggregation scope → ask for clarification
    {
        "input": "Show revenue by country",
        "output": json_output(
            {
                "clarification_question": (
                    "Which country grouping do you want: top 10 countries, one specific country, or all countries?"
                ),
                "needs_clarification": True,
                "sql": None,
                "sql_title": None,
            }
        ),
    },
    # CTE with column alias: ORDER BY must use the alias directly, not wrap it in functions
    {
        "input": "Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?",
        "output": json_output(
            {
                "clarification_question": None,
                "needs_clarification": False,
                "sql": (
                    "WITH monthly_spend AS ("
                    "SELECT app_name, "
                    "SUM(CASE WHEN date >= '2024-12-01' AND date < '2025-01-01' THEN ua_cost ELSE 0 END) AS dec_spend, "
                    "SUM(CASE WHEN date >= '2025-01-01' AND date < '2025-02-01' THEN ua_cost ELSE 0 END) AS jan_spend "
                    "FROM app_metrics GROUP BY app_name) "
                    "SELECT app_name, jan_spend - dec_spend AS spend_change "
                    "FROM monthly_spend ORDER BY spend_change DESC "
                ),
                "sql_title": "UA spend change Jan 2025 vs Dec 2024",
            }
        ),
    },
]

SYSTEM_SQL_REPAIR = """
You are a PostgreSQL expert. A SQL query failed. Diagnose the error and return a corrected query.
If the error is non-retryable, set is_fixable=false.
""".strip()

FEW_SHOT_EXAMPLES_SQL_REPAIR = [
    {
        "input": (
            "Original question: Top apps by revenue last 7 days\n"
            "Failed SQL:\n"
            "SELECT app_name, SUM(revenue) AS revenue "
            "FROM app_metrics "
            "WHERE date >= CURRENT_DATE - INTERVAL '7 days' "
            "GROUP BY app_name ORDER BY revenue DESC LIMIT 10;\n"
            "PostgreSQL error:\n"
            'column "revenue" does not exist'
        ),
        "output": json_output(
            {
                "corrected_sql": (
                    "SELECT app_name, SUM(in_app_revenue + ads_revenue) AS revenue "
                    "FROM app_metrics "
                    "WHERE date >= CURRENT_DATE - INTERVAL '7 days' "
                    "GROUP BY app_name ORDER BY revenue DESC LIMIT 10;"
                ),
                "diagnosis": "Replaced the nonexistent revenue column with in_app_revenue + ads_revenue.",
                "is_fixable": True,
            }
        ),
    },
    {
        "input": (
            "Original question: Delete inactive apps\n"
            "Failed SQL:\n"
            "DELETE FROM apps WHERE status = 'inactive';\n"
            "PostgreSQL error:\n"
            "permission denied for table apps"
        ),
        "output": json_output(
            {
                "corrected_sql": "SELECT 1;",
                "diagnosis": "The request is non-fixable because it attempts forbidden DML instead of read-only analytics SQL.",
                "is_fixable": False,
            }
        ),
    },
]

FEW_SHOT_EXAMPLES = FEW_SHOT_EXAMPLES_SQL_EXPERT
