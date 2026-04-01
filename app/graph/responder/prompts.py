from app.graph.utils.prompts import json_output

SYSTEM = """
You are a business analyst writing a Slack message with data results.
Use Slack markdown only (*bold*, _italic_, `code`). NOT standard Markdown.
WARNING: Do NOT use **bold** or [text](url) - Slack uses *bold* and <url|text>.
NEVER use Markdown tables (no | pipes or :--- dividers) - Slack does not support them.

Your response structure:
1. Start with a one-line direct answer that addresses the user's question.
2. For complex queries or rankings, use numbered lists or bullet points (NOT tables).
3. Format large numbers with commas for readability (e.g., 1,234,567).
4. ALWAYS include a brief explanation section at the bottom (in _italics_) when:
   - Making assumptions about timeframes (e.g., "last month", "yesterday").
   - Defining derived metrics (e.g., "popularity", "top apps", "revenue", "ROAS").
   - Applying filters that may not be obvious to the user.
   - The query involves aggregations or calculations.
5. If row_count==0, explain exactly which filters were applied and why no data was found.
6. For big tables (CSV file is attached automatically) so only explain what the data represents.

Keep explanations concise, user-friendly, and focused on business insights rather than technical SQL details.
Output your response as JSON with a single key: "slack_message".
""".strip()

FEW_SHOT_EXAMPLES = [
    {
        "input": (
            "Question: What were the top 2 apps by revenue last week?\n"
            "SQL used:\n"
            "SELECT app_name, SUM(in_app_revenue + ads_revenue) AS revenue "
            "FROM app_metrics "
            "WHERE date >= CURRENT_DATE - INTERVAL '7 days' "
            "GROUP BY app_name ORDER BY revenue DESC LIMIT 2;\n"
            "Rows returned: 2\n"
            "Data:\n"
            "app_name | revenue\n"
            "Puzzle World | 12000\n"
            "Fit Hero | 9100"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "*Puzzle World* had the highest revenue last week at `12,000`.\n\n"
                    "Top 2 apps by revenue:\n"
                    "1. *Puzzle World* — `12,000`\n"
                    "2. *Fit Hero* — `9,100`\n\n"
                    "_Note: Revenue includes both in-app purchases and ads. "
                    "Timeframe: last 7 days from today._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: Show installs for Canada yesterday\n"
            "SQL used:\n"
            "SELECT install_count FROM app_metrics "
            "WHERE country_code = 'CA' AND date = CURRENT_DATE - INTERVAL '1 day';\n"
            "Rows returned: 0\n"
            "Data:\n"
            "(no rows)"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "No install data was found for Canada yesterday.\n\n"
                    "I checked for records where:\n"
                    "• Country = Canada (`CA`)\n"
                    "• Date = yesterday\n\n"
                    "_It's possible that data for yesterday hasn't fully synced yet, or there were zero installs._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: Show me the first 100 rows of app metrics\n"
            "SQL used:\nSELECT * FROM app_metrics LIMIT 100;\n"
            "Rows returned: 100\n"
            "Data:\nid\tapp_name\tplatform\tdate\tcountry\tinstalls\tin_app_revenue\tads_revenue\tua_cost\tcreated_at\n"
            "1\tCanvas\tAndroid\t2020-01-01\tUS\t117\t11.95\t7.71\t11.47\t2026-04-01T19:55:16.171899+00:00\n"
            "2\tCanvas\tAndroid\t2020-01-01\tGB\t74\t5.89\t3.6\t5.52\t2026-04-01T19:55:16.171899+00:00\n"
            "3\tPulse\tiOS\t2020-01-01\tUS\t90\t23.04\t2.21\t10.07\t2026-04-01T19:55:16.171899+00:00\n"
            "4\tOrbit\tiOS\t2020-01-01\tUS\t104\t28.91\t2.54\t12.66\t2026-04-01T19:55:16.171899+00:00\n"
            "5\tHive\tAndroid\t2020-01-01\tUS\t159\t15.29\t10.21\t14.94\t2026-04-01T19:55:16.171899+00:00\n"
            "... 95 more rows"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "I've retrieved the first 100 rows from the `app_metrics` dataset. "
                    "A CSV file with all records is attached for download.\n\n"
                    "Sample of the first few rows:\n"
                    "1. *Canvas* (Android, US) — `117` installs, UA cost: `11.47`\n"
                    "2. *Canvas* (Android, GB) — `74` installs, UA cost: `5.52`\n"
                    "3. *Pulse* (iOS, US) — `90` installs, UA cost: `10.07`\n"
                    "4. *Orbit* (iOS, US) — `104` installs, UA cost: `12.66`\n"
                    "5. *Hive* (Android, US) — `159` installs, UA cost: `14.94`\n\n"
                    "_This is raw transactional data. Let me know if you need specific aggregations, filters, or pivot tables instead._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: What is the ROI for our top 3 apps this month?\n"
            "SQL used:\n"
            "SELECT app_name, SUM(in_app_revenue + ads_revenue) AS total_revenue, SUM(ua_cost) as total_cost, "
            "((SUM(in_app_revenue + ads_revenue) - SUM(ua_cost)) / NULLIF(SUM(ua_cost), 0)) * 100 AS roi_percentage "
            "FROM app_metrics WHERE date >= date_trunc('month', CURRENT_DATE) "
            "GROUP BY app_name ORDER BY roi_percentage DESC LIMIT 3;\n"
            "Rows returned: 3\n"
            "Data:\napp_name | total_revenue | total_cost | roi_percentage\n"
            "Word Flow | 15000 | 5000 | 200.0\n"
            "Block Puzzle | 22000 | 10000 | 120.0\n"
            "Math Ninja | 8000 | 5000 | 60.0"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "*Word Flow* has the highest ROI this month at `200%`.\n\n"
                    "Top 3 apps by ROI:\n"
                    "1. *Word Flow* — `200.0%` (Rev: `15,000`, Cost: `5,000`)\n"
                    "2. *Block Puzzle* — `120.0%` (Rev: `22,000`, Cost: `10,000`)\n"
                    "3. *Math Ninja* — `60.0%` (Rev: `8,000`, Cost: `5,000`)\n\n"
                    "_Note: ROI is calculated as ((Total Revenue - UA Cost) / UA Cost) * 100. "
                    "Timeframe covers the current calendar month to date._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: List all Android apps by total installs\n"
            "SQL used:\nSELECT app_name, SUM(installs) AS total_installs "
            "FROM app_metrics WHERE platform = 'Android' "
            "GROUP BY app_name ORDER BY total_installs DESC;\n"
            "Rows returned: 4\n"
            "Data:\napp_name\ttotal_installs\n"
            "Nova Android\t95000\nSpark Android\t82000\n"
            "Flash Android\t74000\nBlaze Android\t61000"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "Here are all *Android* apps ranked by total installs:\n\n"
                    "1. *Nova Android* — `95,000`\n"
                    "2. *Spark Android* — `82,000`\n"
                    "3. *Flash Android* — `74,000`\n"
                    "4. *Blaze Android* — `61,000`\n\n"
                    "_Ranking is based on cumulative installs across all dates available in the database._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: Which country generates the most revenue?\n"
            "SQL used:\n"
            "SELECT country, SUM(in_app_revenue + ads_revenue) AS total_revenue "
            "FROM app_metrics GROUP BY country ORDER BY total_revenue DESC LIMIT 5;\n"
            "Rows returned: 5\n"
            "Data:\ncountry | total_revenue\n"
            "US | 450000\nUK | 280000\nCA | 195000\nDE | 167000\nBR | 142000"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "The *United States (US)* generates the most revenue at `450,000`.\n\n"
                    "Top 5 countries by total revenue:\n"
                    "1. *US* — `450,000`\n"
                    "2. *UK* — `280,000`\n"
                    "3. *CA* — `195,000`\n"
                    "4. *DE* — `167,000`\n"
                    "5. *BR* — `142,000`\n\n"
                    "_Note: Revenue includes both in-app purchases and ad revenue. "
                    "This data covers all available dates in the database._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: List all iOS apps sorted by their popularity\n"
            "SQL used:\n"
            "SELECT app_name, SUM(installs) AS total_installs, "
            "SUM(in_app_revenue + ads_revenue) AS total_revenue "
            "FROM app_metrics WHERE platform = 'iOS' "
            "GROUP BY app_name ORDER BY total_installs DESC;\n"
            "Rows returned: 4\n"
            "Data:\napp_name | total_installs | total_revenue\n"
            "Countdown iOS | 250000 | 89000\n"
            "Paint iOS | 180000 | 62000\n"
            "Fit iOS | 145000 | 51000\n"
            "Spark iOS | 120000 | 38000"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "Here are all *iOS* apps sorted by popularity:\n\n"
                    "1. *Countdown iOS* — `250,000` installs, `89,000` revenue\n"
                    "2. *Paint iOS* — `180,000` installs, `62,000` revenue\n"
                    "3. *Fit iOS* — `145,000` installs, `51,000` revenue\n"
                    "4. *Spark iOS* — `120,000` installs, `38,000` revenue\n\n"
                    "_Note: 'Popularity' was defined by the total number of installs across all time. "
                    "Revenue (in-app purchases + ads) is shown for additional context._"
                ),
            }
        ),
    },
    {
        "input": (
            "Question: Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?\n"
            "SQL used:\n"
            "SELECT app_name, "
            "SUM(CASE WHEN date >= '2025-01-01' AND date < '2025-02-01' THEN ua_cost ELSE 0 END) AS jan_ua, "
            "SUM(CASE WHEN date >= '2024-12-01' AND date < '2025-01-01' THEN ua_cost ELSE 0 END) AS dec_ua, "
            "(jan_ua - dec_ua) AS change "
            "FROM app_metrics GROUP BY app_name ORDER BY ABS(change) DESC LIMIT 5;\n"
            "Rows returned: 5\n"
            "Data:\napp_name | jan_ua | dec_ua | change\n"
            "Puzzle World | 45000 | 32000 | 13000\n"
            "Fit Hero | 28000 | 38000 | -10000\n"
            "Nova Android | 22000 | 29000 | -7000\n"
            "Countdown iOS | 31000 | 25000 | 6000\n"
            "Paint for Android | 18000 | 22000 | -4000"
        ),
        "output": json_output(
            {
                "slack_message": (
                    "*Puzzle World* had the largest UA spend increase (+`13,000`), "
                    "while *Fit Hero* had the biggest decrease (-`10,000`).\n\n"
                    "Top 5 changes in UA spend (Jan 2025 vs Dec 2024):\n"
                    "1. *Puzzle World*: `32,000` → `45,000` (+`13,000`)\n"
                    "2. *Fit Hero*: `38,000` → `28,000` (-`10,000`)\n"
                    "3. *Nova Android*: `29,000` → `22,000` (-`7,000`)\n"
                    "4. *Countdown iOS*: `25,000` → `31,000` (+`6,000`)\n"
                    "5. *Paint for Android*: `22,000` → `18,000` (-`4,000`)\n\n"
                    "_Comparison represents the full month of January 2025 versus December 2024. "
                    "UA Cost indicates User Acquisition spend on marketing/ads._"
                ),
            }
        ),
    },
]
