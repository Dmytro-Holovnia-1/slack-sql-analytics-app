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
    INTENT_ROUTER    = "intent_router_node"
    SQL_EXPERT       = "sql_expert_node"
    SQL_EXECUTOR     = "sql_executor_node"
    SQL_REPAIR       = "sql_repair_node"
    RESULT_FORMATTER = "result_formatter_node"
    RESPONSE         = "response_node"
    ARTIFACT_RETRIEVAL = "artifact_retrieval_node"
    META_ANALYST     = "meta_analyst_node"


class _Ref:
    """Single-slot mutable container for a forward reference to the compiled graph."""
    __slots__ = ("app",)

    def __init__(self) -> None:
        self.app: CompiledStateGraph | None = None


def _make_fetch_history(ref: _Ref):
    """Return an async-generator that delegates to ref.app once it is populated."""
    async def fetch_history(config: Any) -> AsyncGenerator[Any, None]:
        assert ref.app is not None, "fetch_history called before graph was compiled"
        async for snapshot in ref.app.aget_state_history(config):
            yield snapshot
    return fetch_history


def _register_nodes(
    builder: StateGraph,
    llm_client: Any,
    query_service: Any,
    fetch_history,
) -> None:
    builder.add_node(NodeName.INTENT_ROUTER,    partial(intent_router_node,    llm_client=llm_client))
    builder.add_node(NodeName.SQL_EXPERT,        partial(sql_expert_node,        llm_client=llm_client))
    builder.add_node(NodeName.SQL_EXECUTOR,      partial(sql_executor_node,      query_service=query_service))
    builder.add_node(NodeName.SQL_REPAIR,        partial(sql_repair_node,        llm_client=llm_client))
    builder.add_node(NodeName.RESULT_FORMATTER,  partial(result_formatter_node,  llm_client=llm_client))
    builder.add_node(NodeName.RESPONSE,          response_node)
    builder.add_node(NodeName.META_ANALYST,      partial(meta_analyst_node,      llm_client=llm_client))
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

    builder.add_edge(NodeName.SQL_REPAIR,        NodeName.SQL_EXECUTOR)
    builder.add_edge(NodeName.RESULT_FORMATTER,  END)
    builder.add_edge(NodeName.ARTIFACT_RETRIEVAL, END)
    builder.add_edge(NodeName.META_ANALYST,      END)
    builder.add_edge(NodeName.RESPONSE,          END)


def build_graph(
    llm_client: Any,
    query_service: Any,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """
    Build and compile the LangGraph workflow.

    Uses a forward-reference (_Ref) so that artifact_retrieval_node receives a
    fetch_history closure that is valid at call time without wrapping the compiled graph.
    Returns the bare CompiledStateGraph — no wrapper, compatible with LangGraph Studio.
    """
    logger.info("Building LangGraph workflow")

    ref = _Ref()
    fetch_history = _make_fetch_history(ref)

    builder = StateGraph(GraphState)
    _register_nodes(builder, llm_client, query_service, fetch_history)
    _register_edges(builder)

    compiled = builder.compile(checkpointer=checkpointer)
    ref.app = compiled  # fill the forward reference; fetch_history is now live

    logger.info("LangGraph workflow compiled with nodes: %s", list(compiled.nodes))
    return compiled


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