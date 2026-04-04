"""
Usage:
    python -m tests.stress_test
    python -m tests.stress_test --concurrency 40
"""

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.config import load_settings
from app.graph.graph import build_graph
from app.llm.gemini_client import GeminiClient
from app.services.query_service import DatabaseQueryService

load_dotenv()

QUESTIONS = [
    "Show me top 5 apps by revenue this month",
    "How many installs did we get in Canada yesterday?",
    "Which country generates the most revenue?",
    "What is the ROI for our top 3 apps?",
    "List all Android apps by total installs",
    "Which apps had the biggest change in UA spend?",
    "Show revenue breakdown by country for iOS apps",
    "What were the top 2 apps by revenue last week?",
    "How many apps do we have?",
    "Show me daily installs for the last 7 days",
]


@dataclass
class Result:
    question: str
    success: bool
    duration_s: float
    intent: str | None = None
    error: str | None = None


async def run_one(graph, question: str, thread_id: str) -> Result:
    start = time.perf_counter()
    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": thread_id}},
        )
        return Result(
            question=question,
            success=True,
            duration_s=time.perf_counter() - start,
            intent=state.get("intent"),
        )
    except Exception as e:
        return Result(
            question=question,
            success=False,
            duration_s=time.perf_counter() - start,
            error=str(e),
        )


async def run(concurrency: int) -> None:
    settings = load_settings()
    graph = build_graph(
        llm_client=GeminiClient(settings),
        query_service=DatabaseQueryService.from_settings(settings),
        checkpointer=MemorySaver(),
    )

    questions = (QUESTIONS * ((concurrency // len(QUESTIONS)) + 1))[:concurrency]

    print(f"\n{'=' * 58}")
    print(f"  Stress test — {concurrency} concurrent requests")
    print(f"{'=' * 58}")

    wall_start = time.perf_counter()
    results = await asyncio.gather(*(run_one(graph, q, f"stress-{i}") for i, q in enumerate(questions)))
    wall = time.perf_counter() - wall_start

    ok = [r for r in results if r.success]
    fail = [r for r in results if not r.success]
    durations = sorted(r.duration_s for r in results)

    print(f"\n  ✓ Success:         {len(ok)}/{concurrency} ({100 * len(ok) // concurrency}%)")
    print(f"  ✗ Failures:        {len(fail)}")
    print(f"  ⏱  Wall time:       {wall:.1f}s\n")
    print("  Latency per request:")
    print(f"    min    {durations[0]:.2f}s")
    print(f"    p50    {statistics.median(durations):.2f}s")
    print(f"    p95    {durations[int(0.95 * len(durations))]:.2f}s")
    print(f"    p99    {durations[int(0.99 * len(durations))]:.2f}s")
    print(f"    max    {durations[-1]:.2f}s")

    if fail:
        print("\n  Failures:")
        for r in fail:
            print(f"    [{r.duration_s:.1f}s] {r.question[:45]!r} → {r.error}")

    intents: dict[str, int] = {}
    for r in ok:
        intents[r.intent or "unknown"] = intents.get(r.intent or "unknown", 0) + 1
    if intents:
        print("\n  Intent distribution:")
        for intent, n in sorted(intents.items(), key=lambda x: -x[1]):
            print(f"    {n:3d}×  {intent}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    asyncio.run(run(parser.parse_args().concurrency))
