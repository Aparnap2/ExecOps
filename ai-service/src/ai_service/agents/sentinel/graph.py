"""Sentinel LangGraph.

StateGraph for GitHub PR review with Linear context and SOP compliance.
Extends vertical_agents.py patterns with Sentinel-specific workflow.
"""

import logging
from typing import AsyncGenerator

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .state import SentinelState, create_initial_sentinel_state
from .nodes import (
    extract_linear_context,
    check_compliance,
    send_for_approval,
    execute,
    reject,
)
from ai_service.infrastructure.checkpointer import (
    get_async_checkpointer,
    GraphCheckpointerConfig,
)

logger = logging.getLogger(__name__)


def create_sentinel_graph() -> StateGraph:
    """Create Sentinel StateGraph with nodes and edges.

    Graph flow:
        START -> extract_linear_context -> check_compliance -> send_for_approval
                                                                    |
                                                                    v
        execute -> END                          <-<-<- reject <-<-<-<-<-<-<-

    The send_for_approval node uses interrupt() for human-in-the-loop.
    On resume, the decision determines goto target (execute or reject).

    Returns:
        StateGraph builder (not yet compiled)
    """
    builder = StateGraph(SentinelState)

    # Add nodes
    builder.add_node("extract_linear_context", extract_linear_context)
    builder.add_node("check_compliance", check_compliance)
    builder.add_node("send_for_approval", send_for_approval)
    builder.add_node("execute", execute)
    builder.add_node("reject", reject)

    # Define flow
    builder.add_edge(START, "extract_linear_context")
    builder.add_edge("extract_linear_context", "check_compliance")
    builder.add_edge("check_compliance", "send_for_approval")

    # execute and reject both end the graph
    builder.add_edge("execute", END)
    builder.add_edge("reject", END)

    logger.info("Sentinel StateGraph created")

    return builder


async def get_sentinel_graph(
    use_postgres: bool = True,
) -> StateGraph:
    """Get compiled Sentinel graph with appropriate checkpointer.

    Args:
        use_postgres: Use Postgres checkpointer (default True for production)

    Returns:
        Compiled StateGraph ready for ainvoke()
    """
    import os

    builder = create_sentinel_graph()

    if use_postgres and os.getenv("USE_POSTGRES_CHECKPOINTER", "true").lower() == "true":
        try:
            async with get_async_checkpointer() as checkpointer:
                compiled = builder.compile(checkpointer=checkpointer)
                logger.info("Sentinel graph compiled with Postgres checkpointer")
                return compiled
        except Exception as e:
            logger.warning(
                f"Failed to use Postgres checkpointer: {e}. "
                "Falling back to memory checkpointer."
            )

    # Fallback to memory checkpointer
    memory = MemorySaver()
    compiled = builder.compile(checkpointer=memory)
    logger.info("Sentinel graph compiled with memory checkpointer")

    return compiled


async def get_sentinel_graph_with_config(
    thread_id: str,
    use_postgres: bool = True,
) -> tuple[StateGraph, dict]:
    """Get compiled Sentinel graph with thread configuration.

    Convenience function combining graph creation and config generation.

    Args:
        thread_id: Unique thread ID for checkpointing (e.g., "sentinel-gh-pr-123")
        use_postgres: Use Postgres checkpointer

    Returns:
        Tuple of (compiled graph, config dict)
    """
    graph = await get_sentinel_graph(use_postgres=use_postgres)
    config = GraphCheckpointerConfig.get_configurable(thread_id)
    return graph, config


def run_sentinel_workflow(
    pr_number: int,
    pr_id: str,
    pr_title: str,
    pr_body: str,
    pr_author: str,
    pr_url: str,
    event_id: str | None = None,
    urgency: str = "medium",
) -> SentinelState:
    """Create initial SentinelState for a GitHub PR.

    Convenience function for webhook handlers to create initial state.

    Args:
        pr_number: GitHub PR number
        pr_id: GitHub PR node ID
        pr_title: PR title
        pr_body: PR description
        pr_author: PR author username
        pr_url: GitHub PR URL
        event_id: Unique event ID (auto-generated if not provided)
        urgency: Urgency level

    Returns:
        Initial SentinelState dict
    """
    if event_id is None:
        import uuid
        event_id = f"gh-pr-{pr_id}-{uuid.uuid4().hex[:8]}"

    return create_initial_sentinel_state(
        event_id=event_id,
        pr_number=pr_number,
        pr_id=pr_id,
        pr_title=pr_title,
        pr_body=pr_body,
        pr_author=pr_author,
        pr_url=pr_url,
        urgency=urgency,
    )


# =============================================================================
# Integration with vertical_agents.py
# =============================================================================

def get_vertical_graph(vertical: str):
    """Get StateGraph for any vertical (extended with sentinel).

    Can be imported and called from vertical_agents.py for integration.

    Args:
        vertical: Vertical agent name ("sentinel" or others)

    Returns:
        StateGraph builder for the requested vertical
    """
    if vertical == "sentinel":
        return create_sentinel_graph()

    # Fallback to vertical_agents.py for other verticals
    from ai_service.graphs.vertical_agents import get_vertical_graph as _get

    logger.warning(f"Unknown vertical '{vertical}' - delegating to vertical_agents")
    return _get(vertical)


async def ainvoke_sentinel(
    initial_state: SentinelState,
    thread_id: str | None = None,
    use_postgres: bool = True,
) -> SentinelState:
    """Convenience function to invoke Sentinel graph.

    Args:
        initial_state: Initial state dict from run_sentinel_workflow()
        thread_id: Thread ID for checkpointing (auto-generated if None)
        use_postgres: Use Postgres checkpointer

    Returns:
        Final state after graph execution
    """
    if thread_id is None:
        import uuid
        thread_id = f"sentinel-{initial_state.get('event_id', uuid.uuid4().hex[:8])}"

    graph, config = await get_sentinel_graph_with_config(
        thread_id=thread_id,
        use_postgres=use_postgres,
    )

    result = await graph.ainvoke(initial_state, config=config)

    logger.info(
        f"Sentinel workflow completed for PR #{initial_state.get('pr_number')}: "
        f"status={result.get('status')}"
    )

    return result


__all__ = [
    "SentinelState",
    "create_sentinel_graph",
    "get_sentinel_graph",
    "get_sentinel_graph_with_config",
    "run_sentinel_workflow",
    "get_vertical_graph",
    "ainvoke_sentinel",
]
