from __future__ import annotations

from collections.abc import AsyncGenerator
from enum import StrEnum
from functools import partial
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from app.graph.artifact_retrieval.node import artifact_retrieval_node
from app.graph.intent_router.node import intent_router_node, route_intent
from app.graph.meta_analysis.node import meta_analyst_node
from app.graph.responder.formatter_node import result_formatter_node
from app.graph.responder.response_node import response_node
from app.graph.sql_generation.executor_node import route_sql_executor, sql_executor_node
from app.graph.sql_generation.expert_node import route_sql_expert, sql_expert_node
from app.graph.sql_generation.repair_node import sql_repair_node
from app.graph.state import GraphState


class NodeName(StrEnum):
    INTENT_ROUTER = "intent_router_node"
    SQL_EXPERT = "sql_expert_node"
    SQL_EXECUTOR = "sql_executor_node"
    SQL_REPAIR = "sql_repair_node"
    RESULT_FORMATTER = "result_formatter_node"
    RESPONSE = "response_node"
    ARTIFACT_RETRIEVAL = "artifact_retrieval_node"
    META_ANALYST = "meta_analyst_node"


def _register_nodes(
    builder: StateGraph,
    llm_client: Any,
    query_service: Any,
    fetch_history,
) -> None:
    builder.add_node(NodeName.INTENT_ROUTER, partial(intent_router_node, llm_client=llm_client))
    builder.add_node(NodeName.SQL_EXPERT, partial(sql_expert_node, llm_client=llm_client))
    builder.add_node(NodeName.SQL_EXECUTOR, partial(sql_executor_node, query_service=query_service))
    builder.add_node(NodeName.SQL_REPAIR, partial(sql_repair_node, llm_client=llm_client))
    builder.add_node(NodeName.RESULT_FORMATTER, partial(result_formatter_node, llm_client=llm_client))
    builder.add_node(NodeName.RESPONSE, response_node)
    builder.add_node(NodeName.META_ANALYST, partial(meta_analyst_node, llm_client=llm_client))
    # artifact_retrieval_node gets a live fetch_history closure bound via _Ref
    builder.add_node(
        NodeName.ARTIFACT_RETRIEVAL,
        partial(artifact_retrieval_node, fetch_history=fetch_history, llm_client=llm_client),
    )


def _register_edges(builder: StateGraph) -> None:
    builder.add_edge(START, NodeName.INTENT_ROUTER)

    builder.add_conditional_edges(NodeName.INTENT_ROUTER, route_intent)
    builder.add_conditional_edges(NodeName.SQL_EXPERT, route_sql_expert)
    builder.add_conditional_edges(NodeName.SQL_EXECUTOR, route_sql_executor)

    builder.add_edge(NodeName.SQL_REPAIR, NodeName.SQL_EXECUTOR)
    builder.add_edge(NodeName.RESULT_FORMATTER, END)
    builder.add_edge(NodeName.ARTIFACT_RETRIEVAL, END)
    builder.add_edge(NodeName.META_ANALYST, END)
    builder.add_edge(NodeName.RESPONSE, END)


def build_graph(
    llm_client: Any,
    query_service: Any,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """
    Compile and return the analytics LangGraph state machine.

    ``fetch_history`` is a closure over ``_graph`` to break a circular init:
    artifact_retrieval needs ``aget_state_history`` → which needs a compiled
    graph → which needs nodes already registered. Assigning ``_graph`` after
    ``builder.compile()`` works because Python closures capture variables by
    reference, not by value.
    """
    _graph: CompiledStateGraph | None = None

    async def fetch_history(config: Any) -> AsyncGenerator[Any]:
        if _graph is None:
            raise RuntimeError(
                "fetch_history called before build_graph completed — " "this is a bug in graph initialization order."
            )
        async for snapshot in _graph.aget_state_history(config):
            yield snapshot

    builder = StateGraph(GraphState)
    _register_nodes(builder, llm_client, query_service, fetch_history)
    _register_edges(builder)

    _graph = builder.compile(checkpointer=checkpointer)
    return _graph


def create_graph() -> CompiledStateGraph:
    """
    Factory for LangGraph Studio — resolves dependencies from environment variables.

    Deferred imports prevent circular dependency issues at module load time.
    """
    from app.config import load_settings
    from app.llm.gemini_client import GeminiClient
    from app.services.query_service import DatabaseQueryService

    logger.info("Creating graph for LangGraph Studio")
    settings = load_settings()

    return build_graph(
        llm_client=GeminiClient(settings),
        query_service=DatabaseQueryService.from_settings(settings),
        checkpointer=MemorySaver(),
    )
