"""
Run LangSmith evaluation on the Text-to-SQL Slack bot.

Usage:
    python -m tests.evaluation.run_evaluation
"""

import asyncio

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langsmith import evaluate

from app.config import load_settings
from app.graph.graph import build_graph
from app.llm.gemini_client import GeminiClient
from app.services.query_service import DatabaseQueryService
from tests.evaluation.evaluators import EVALUATORS

load_dotenv()
settings = load_settings()


async def run_graph_async(inputs: dict) -> dict:
    """
    Async target function for LangSmith evaluate.

    Supports two input shapes:

    1. Standalone (no history):
       {"question": "Show me top 5 apps by revenue"}

    2. Multi-turn (with history):
       {
           "question": "export this as csv",
           "chat_history": [
               {"role": "user",      "content": "Show me top 5 apps by revenue"},
               {"role": "assistant", "content": "Here are the top 5 apps..."},
           ]
       }

    When chat_history is present the prior USER turns are replayed through
    the graph first (preserving full state — sql_candidate, query_results, etc.)
    so follow-up intents like csv_export / sql_request resolve correctly.
    """
    question: str = inputs["question"]
    chat_history: list[dict] = inputs.get("chat_history") or []

    # Unique thread per example — include history hash so multi-turn examples
    # each get a fresh isolated thread and don't bleed into each other.
    thread_id = f"eval-{hash(question)}-{hash(str(chat_history))}"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    llm_client = GeminiClient(settings)
    query_service = DatabaseQueryService.from_settings(settings)
    checkpointer = MemorySaver()
    graph = build_graph(llm_client, query_service, checkpointer)

    # ── 1. Replay prior user turns to seed the checkpointer state ──────────
    # We only replay user turns — the graph generates assistant responses
    # automatically, producing real sql_candidate / query_results in state.
    # This ensures follow-up questions have genuine context to resolve against.
    for turn in chat_history:
        if turn.get("role") == "user":
            await graph.ainvoke(
                {"messages": [HumanMessage(content=turn["content"])]},
                config=config,
            )

    # ── 2. Run the actual evaluation question ──────────────────────────────
    final_state = await graph.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config=config,
    )

    return {
        "intent": final_state.get("intent"),
        "sql_candidate": final_state.get("sql_candidate"),
        "sql_error": final_state.get("sql_error"),
        "formatted_response": final_state.get("formatted_response"),
    }


def run_graph_wrapper(inputs: dict) -> dict:
    """Synchronous wrapper required by langsmith.evaluate."""
    return asyncio.run(run_graph_async(inputs))


def main() -> None:
    print("Running Text-to-SQL bot evaluation...")
    evaluate(
        run_graph_wrapper,
        data="rounds-slack-bot-eval",
        evaluators=EVALUATORS,
        experiment_prefix="gemini-sql-eval",
        metadata={
            "model": settings.gemini_standard_model,
            "timeout_ms": settings.db_statement_timeout_ms,
        },
        max_concurrency=2,
    )
    print("Evaluation complete! Results available in LangSmith Studio.")


if __name__ == "__main__":
    main()
