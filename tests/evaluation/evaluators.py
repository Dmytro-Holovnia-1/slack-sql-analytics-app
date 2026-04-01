"""Metrics for evaluating graph quality."""

import os
import re

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith.schemas import Example, Run

from app.db.schema import DB_SCHEMA

# Load .env for LLM judge settings
load_dotenv()


def _get_judge_llm():
    """Use Gemini as the judge."""
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_STANDARD_MODEL"),
        temperature=0.0,
    )


def evaluate_intent_accuracy(run: Run, example: Example) -> dict:
    """Check if intent_router_node worked correctly."""
    expected = example.outputs.get("expected_intent")
    actual = (run.outputs or {}).get("intent")

    score = 1.0 if expected == actual else 0.0
    return {
        "key": "intent_accuracy",
        "score": score,
        "comment": f"Expected: {expected}, Got: {actual}",
    }


def evaluate_sql_execution_success(run: Run, example: Example) -> dict:
    """Check if SQL executed without errors."""
    sql_error = (run.outputs or {}).get("sql_error")
    score = 1.0 if sql_error is None else 0.0
    return {
        "key": "sql_execution_success",
        "score": score,
        "comment": str(sql_error) if sql_error else "Success",
    }


def evaluate_sql_relevance(run: Run, example: Example) -> dict:
    """LLM-as-a-Judge: Does the generated SQL answer the user's question?"""
    question = example.inputs.get("question", "")
    sql = (run.outputs or {}).get("sql_candidate", "")

    if not sql:
        return {"key": "sql_relevance", "score": 0.0, "comment": "No SQL generated"}

    prompt = ChatPromptTemplate.from_template("""
    You are an expert PostgreSQL database architect.
    Evaluate if the generated SQL correctly answers the user's question based on the schema.

    Schema:
    {schema}

    Question: {question}
    Generated SQL: {sql}

    Does this SQL correctly answer the question?
    Respond with ONLY a number:
    1.0 = Perfectly correct
    0.5 = Partially correct (e.g., missing a minor filter or wrong sort order)
    0.0 = Incorrect or irrelevant

    Score:""")

    judge = _get_judge_llm()
    chain = prompt | judge

    try:
        # Use synchronous .invoke() instead of .ainvoke()
        result = chain.invoke({"schema": DB_SCHEMA, "question": question, "sql": sql})
        content = str(result.content).strip()
        match = re.search(r"(\d+\.?\d*)", content)
        score = float(match.group(1)) if match else 0.0
        return {"key": "sql_relevance", "score": score, "comment": f"Judge response: {content}"}
    except Exception as e:
        return {"key": "sql_relevance", "score": 0.0, "comment": f"Judge error: {e}"}


def master_evaluator(run: Run, example: Example) -> list[dict]:
    """Main evaluator (synchronous) that decides which metrics to apply."""
    results = []
    outputs = run.outputs or {}
    intent = outputs.get("intent")

    # 1. Always check intent accuracy
    results.append(evaluate_intent_accuracy(run, example))

    # 2. Add SQL metrics only if intent is 'query_database_for_new_analytics_data'
    if intent == "query_database_for_new_analytics_data":
        # Check for successful execution
        results.append(evaluate_sql_execution_success(run, example))

        # Check for relevance (only if SQL was generated)
        if outputs.get("sql_candidate"):
            relevance_result = evaluate_sql_relevance(run, example)
            results.append(relevance_result)

    return results


# List of evaluators for LangSmith
EVALUATORS = [master_evaluator]
