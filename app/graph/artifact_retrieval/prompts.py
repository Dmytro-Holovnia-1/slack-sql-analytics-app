from app.graph.utils.prompts import json_output

SYSTEM_PROMPT = """
You are an assistant identifying which previous data query a user is referring to.
The list of past queries is provided in REVERSE CHRONOLOGICAL ORDER (index [0] is the most recent).

Return the zero-based index and your confidence.
""".strip()

FEW_SHOT_EXAMPLES = [
    {
        "input": (
            "Past queries (newest first):\n"
            '[0] Q: "What is the profit in Germany?" -> "Total profit Germany"\n'
            '[1] Q: "Top apps by installs" -> "App rankings by installs"\n'
            "message: show the sql used"
        ),
        "output": json_output(
            {
                "match_confidence": 1.0,
                "matched_question_index": 0,
                "reasoning": "User is asking for SQL without specifying which query; defaulting to the most recent one.",
            }
        ),
    },
    {
        "input": (
            "Past queries (newest first):\n"
            '[0] Q: "Revenue by platform" -> "Revenue split iOS Android"\n'
            '[1] Q: "Retention by country" -> "Retention rates by country"\n'
            '[2] Q: "Top campaigns yesterday" -> "Top UA campaigns yesterday"\n'
            "message: export the retention report"
        ),
        "output": json_output(
            {
                "match_confidence": 0.98,
                "matched_question_index": 1,
                "reasoning": "User explicitly mentioned 'retention', which matches index [1].",
            }
        ),
    },
    {
        "input": (
            "Past queries (newest first):\n"
            '[0] Q: "Daily revenue" -> "Revenue trend"\n'
            '[1] Q: "List of all apps" -> "App list"\n'
            "message: show sql for the first question I asked"
        ),
        "output": json_output(
            {
                "match_confidence": 0.95,
                "matched_question_index": 1,
                "reasoning": "User asked for the 'first' question, which in a list of 2 items is the oldest one (index 1).",
            }
        ),
    },
]
