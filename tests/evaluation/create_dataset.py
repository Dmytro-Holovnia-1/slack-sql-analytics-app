"""
Create a dataset for evaluating the Text-to-SQL Slack bot.

Usage:
    python -m tests.evaluation.create_dataset
"""

from typing import Any

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()


def main() -> None:
    client = Client()
    dataset_name = "rounds-slack-bot-eval"

    print(f"Creating dataset {dataset_name!r}...")
    dataset: Any = None
    try:
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Evaluation dataset for Text-to-SQL Slack bot — intent routing & SQL generation",
        )
    except Exception as e:
        if "already exists" in str(e):
            print(f"Dataset {dataset_name!r} already exists. Retrieving it...")
            dataset = client.read_dataset(dataset_name=dataset_name)
        else:
            raise e

    # ── Schema ──────────────────────────────────────────────────────────────
    # inputs:
    #   question     str           — the user's latest message
    #   chat_history list[dict]    — optional prior turns: [{"role": "user"|"assistant", "content": str}]
    #                                omit (or empty list) for standalone (no-history) questions
    # outputs:
    #   expected_intent str        — one of: query_database_for_new_analytics_data | retrieve_sql_code_from_previous_conversation_turn | export_previous_query_results_to_csv_file | explain_sql_or_database_schema_without_querying | decline_off_topic_request_unrelated_to_analytics
    # ────────────────────────────────────────────────────────────────────────

    examples: list[dict[str, Any]] = [
        # ── Analytical — no history ──────────────────────────────────────
        {
            "inputs": {
                "question": "Show me top 5 apps by revenue this month",
            },
            "outputs": {"expected_intent": "query_database_for_new_analytics_data"},
            "metadata": {"category": "analytical", "difficulty": "easy"},
        },
        {
            "inputs": {
                "question": "How many installs did we get in Canada yesterday?",
            },
            "outputs": {"expected_intent": "query_database_for_new_analytics_data"},
            "metadata": {"category": "analytical", "difficulty": "medium"},
        },
        {
            "inputs": {
                "question": "Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?",
            },
            "outputs": {"expected_intent": "query_database_for_new_analytics_data"},
            "metadata": {"category": "analytical", "difficulty": "hard"},
        },
        {
            "inputs": {
                "question": "Show me revenue breakdown by country for iOS apps",
            },
            "outputs": {"expected_intent": "query_database_for_new_analytics_data"},
            "metadata": {"category": "analytical", "difficulty": "medium"},
        },
        # ── CSV Export — WITH chat history ───────────────────────────────
        # These follow-up questions are ambiguous without context.
        # chat_history seeds the prior analytical turn so the router
        # can correctly classify "export this" as export_previous_query_results_to_csv_file.
        {
            "inputs": {
                "question": "export this as csv",
                "chat_history": [
                    {"role": "user", "content": "Show me top 5 apps by revenue this month"},
                    {
                        "role": "assistant",
                        "content": "Here are the top 5 apps by revenue this month:\n1. Atlas iOS — $42,000\n2. Orbit Android — $38,500\n...",
                    },
                ],
            },
            "outputs": {"expected_intent": "export_previous_query_results_to_csv_file"},
            "metadata": {"category": "followup", "followup_type": "csv_export"},
        },
        {
            "inputs": {
                "question": "can I download that data?",
                "chat_history": [
                    {"role": "user", "content": "How many installs did we get in Canada yesterday?"},
                    {
                        "role": "assistant",
                        "content": "Canada had 1,842 installs yesterday across all apps and platforms.",
                    },
                ],
            },
            "outputs": {"expected_intent": "export_previous_query_results_to_csv_file"},
            "metadata": {"category": "followup", "followup_type": "csv_export"},
        },
        # ── SQL Request — WITH chat history ──────────────────────────────
        {
            "inputs": {
                "question": "show me the sql for that last query",
                "chat_history": [
                    {"role": "user", "content": "How many installs did we get in Canada yesterday?"},
                    {"role": "assistant", "content": "Canada had 1,842 installs yesterday."},
                ],
            },
            "outputs": {"expected_intent": "retrieve_sql_code_from_previous_conversation_turn"},
            "metadata": {"category": "followup", "followup_type": "sql_request"},
        },
        {
            "inputs": {
                "question": "what query did you run?",
                "chat_history": [
                    {
                        "role": "user",
                        "content": "Which apps had the biggest change in UA spend comparing Jan 2025 to Dec 2024?",
                    },
                    {
                        "role": "assistant",
                        "content": "The biggest UA spend changes were: Paint Android +$12,400, Countdown iOS -$8,200...",
                    },
                ],
            },
            "outputs": {"expected_intent": "retrieve_sql_code_from_previous_conversation_turn"},
            "metadata": {"category": "followup", "followup_type": "sql_request"},
        },
        # ── Off-topic — no history ────────────────────────────────────────
        {
            "inputs": {
                "question": "Write a python script to scrape a website",
            },
            "outputs": {"expected_intent": "decline_off_topic_request_unrelated_to_analytics"},
            "metadata": {"category": "off_topic"},
        },
        {
            "inputs": {
                "question": "What is the capital of France?",
            },
            "outputs": {"expected_intent": "decline_off_topic_request_unrelated_to_analytics"},
            "metadata": {"category": "off_topic"},
        },
    ]

    for i, example in enumerate(examples, 1):
        client.create_example(
            inputs=example["inputs"],
            outputs=example["outputs"],
            dataset_id=dataset.id,  # type: ignore[union-attr]
            metadata=example.get("metadata", {}),
        )
        print(f"  {i}/{len(examples)} Added: {example['inputs']['question']!r}")

    print(f"\nDataset created! ID: {dataset.id}")  # type: ignore[union-attr]
    print(f"Link: https://smith.langchain.com/datasets/{dataset.id}")  # type: ignore[union-attr]


if __name__ == "__main__":
    main()
