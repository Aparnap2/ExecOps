"""
Main FastAPI application for AI Service.

Exposes ExecOps vertical agents and GitHub Sentinel via REST API.

New Endpoints:
- POST /process_event - Process event through vertical agent
- POST /generate_analytics - LLM-powered streaming analytics
- GET /generate_analytics/stream - Streaming analytics via SSE
- GET /proposals - List action proposals
- POST /proposals/[id]/approve - Approve proposal
- POST /proposals/[id]/reject - Reject proposal

Legacy Endpoints (Deprecated):
- POST /decide - Legacy SOP decision endpoint
- GET /sops - List available SOPs
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

# Import new vertical agents
from .graphs import (
    route_to_vertical,
    create_vertical_agent_graph,
    ActionProposalState,
)

# Import legacy schemas for backward compatibility
from .schemas.sop import DecisionRequest, DecisionResponse

# Import GitHub Sentinel endpoints (legacy)
from .integrations.webhook import router as webhook_router

# Import new Sentinel webhook endpoints
from .webhooks.github import router as sentinel_webhook_router

# Import Generative Analytics
from .analytics.generator import generate_analytics_stream, generate_analytics
from .analytics.llm_router import generate_true_generative_ui_stream

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("Starting AI Service...")
    logger.info("ExecOps vertical agents loaded and ready")
    logger.info("GitHub Sentinel webhook endpoint ready")
    yield
    logger.info("Shutting down AI Service...")


app = FastAPI(
    title="FounderOS AI Service",
    description="ExecOps automation and GitHub Sentinel for SaaS founders",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include GitHub Sentinel webhook router
app.include_router(webhook_router, prefix="/api/v1")

# Include new Sentinel webhook handler for PR review
app.include_router(sentinel_webhook_router, prefix="/api/v1")


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-service"}


# =============================================================================
# Generative Analytics Endpoints (New)
# =============================================================================

@app.post("/generate_analytics")
async def generate_analytics_endpoint(req: dict[str, Any]) -> dict[str, Any]:
    """
    Generate analytics using LLM-powered reasoning.

    Request body:
    {
        "query": "What is our runway?" | "Show me revenue metrics" | etc.
    }

    Returns complete analytics result with metrics, trends, and insights.
    """
    query = req.get("query")

    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    logger.info(f"Generating analytics for query: {query}")

    try:
        result = await generate_analytics(query)
        return {
            "query": result.query,
            "query_type": result.query_type.value,
            "generated_at": result.generated_at,
            "insights": [
                {"type": i.type, "title": i.title, "value": i.value, "context": i.context}
                for i in result.insights
            ],
            "metrics": result.metrics,
            "trends": result.trends,
            "warnings": result.warnings,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
            "data_freshness": result.data_freshness,
        }
    except Exception as e:
        logger.error(f"Analytics generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/generate_analytics/stream")
async def generate_analytics_stream_endpoint(
    request: Request,
    query: str = "",
) -> StreamingResponse:
    """
    Stream analytics results using Server-Sent Events (SSE).

    Query param: ?query=What%20is%20our%20runway?

    Streams progressive updates:
    - thinking: LLM is analyzing
    - insight: New insight discovered
    - metrics: Metrics computed
    - warnings: Any warnings
    - complete: Final result
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query parameter is required")

    logger.info(f"Streaming analytics for query: {query}")

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for streaming analytics."""
        try:
            async for chunk in generate_analytics_stream(query):
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                yield {"event": chunk.get("type", "message"), "data": json.dumps(chunk)}
        except Exception as e:
            logger.error(f"Streaming analytics failed: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# =============================================================================
# v2 Generative UI Endpoints
# =============================================================================

@app.get("/generative_ui/stream")
async def generative_ui_stream_endpoint(
    request: Request,
    query: str = "",
) -> StreamingResponse:
    """
    v2 Generative UI - LLM determines which functions to call.

    Query param: ?query=How%20is%20our%20team%20velocity?

    This is true generative UI where:
    1. LLM analyzes the query
    2. Routes to appropriate analytics functions
    3. Streams results with UI component hints
    4. Frontend renders dynamic components based on data shape

    Stream events:
    - thinking: LLM analyzing query
    - routing: Function routing decision
    - function_call: Executing a function
    - data: Function result with component hints
    - complete: Final composed result with UI instructions
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query parameter is required")

    logger.info(f"v2 Generative UI for query: {query}")

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for TRUE generative UI."""
        try:
            async for chunk in generate_true_generative_ui_stream(query):
                if await request.is_disconnected():
                    break
                event_type = chunk.get("type", "message")
                data = json.dumps(chunk)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.error(f"v2 Generative UI failed: {e}")
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# ExecOps Endpoints (New)
# =============================================================================

@app.post("/process_event")
async def process_event(req: dict[str, Any]) -> dict[str, Any]:
    """
    Process an event through the appropriate vertical agent.

    Request body:
    {
        "event_type": "sentry.error|intercom.ticket|stripe.invoice|github.activity",
        "event_context": {...},
        "urgency": "low|medium|high|critical"
    }

    Returns:
    {
        "proposal_id": "uuid",
        "vertical": "release_hygiene|customer_fire|runway_money|team_pulse",
        "action_type": "...",
        "payload": {...},
        "reasoning": "...",
        "confidence": 0.92,
        "status": "pending_approval"
    }
    """
    event_type = req.get("event_type")
    event_context = req.get("event_context", {})
    urgency = req.get("urgency", "low")

    if not event_type:
        raise HTTPException(status_code=400, detail="event_type is required")

    # Route to vertical
    vertical = route_to_vertical(event_type)

    # Create initial state
    state = ActionProposalState(
        event_id=f"evt_{hash(str(req))}",
        event_type=event_type,
        vertical=vertical,
        urgency=urgency,
        status="pending",
        confidence=0.0,
        event_context=event_context,
    )

    # Get and compile graph (create_vertical_agent_graph returns compiled graph)
    graph = create_vertical_agent_graph(vertical)

    # Execute graph with thread_id for checkpointer
    config = {"configurable": {"thread_id": state["event_id"]}}
    result = graph.invoke(state, config=config)

    return {
        "proposal_id": result.get("event_id"),
        "vertical": vertical,
        "action_type": result.get("draft_action", {}).get("action_type"),
        "payload": result.get("draft_action", {}).get("payload"),
        "reasoning": result.get("analysis", {}).get("reasoning"),
        "confidence": result.get("confidence", 0.8),
        "status": result.get("status", "pending"),
    }


@app.get("/proposals")
async def list_proposals(
    status: str | None = None,
    vertical: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List action proposals with optional filtering.

    Query params:
    - status: Filter by status (pending, approved, rejected, executed)
    - vertical: Filter by vertical (release, customer_fire, runway, team_pulse)
    - limit: Maximum number of results (default 50)
    """
    # This would query the database in production
    # For now, return a placeholder response
    return {
        "proposals": [],
        "pagination": {
            "total": 0,
            "limit": limit,
            "offset": 0,
        },
    }


@app.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str) -> dict[str, Any]:
    """Approve an action proposal."""
    # This would update the database in production
    return {
        "id": proposal_id,
        "status": "approved",
        "approved_at": "2026-01-15T11:00:00Z",
    }


@app.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, reason: str | None = None) -> dict[str, Any]:
    """Reject an action proposal."""
    # This would update the database in production
    return {
        "id": proposal_id,
        "status": "rejected",
        "rejection_reason": reason,
    }


# =============================================================================
# Legacy Endpoints (Deprecated - for backward compatibility)
# =============================================================================

@app.post("/decide", response_model=DecisionResponse, deprecated=True)
async def decide(req: DecisionRequest) -> DecisionResponse:
    """
    DEPRECATED: Use /process_event instead.

    Main decision endpoint for legacy SOP execution.
    Accepts a DecisionRequest with events and context,
    runs the appropriate SOP graph, and returns a DecisionResponse.
    """
    logger.warning(
        f"Legacy /decide endpoint called: request_id={req.request_id}, objective={req.objective}"
    )

    # Return a mock response for backward compatibility
    # In production, this would still work with the legacy SOP graph
    return DecisionResponse(
        request_id=req.request_id,
        state="CONFIDENT",
        summary="Legacy endpoint - migrate to /process_event for ExecOps",
        confidence=0.75,
        confidence_breakdown={
            "data_completeness": 0.9,
            "ambiguity": 0.1,
            "rule_violations": 0.05,
        },
        recommendations=[],
        escalations=[],
        executed_sops=["legacy_mode"],
    )


@app.get("/sops", deprecated=True)
async def list_sops() -> dict[str, Any]:
    """
    DEPRECATED: SOPs are replaced by vertical agents.

    List available SOPs (for legacy compatibility).
    """
    return {
        "sops": [],
        "message": "SOPs are replaced by vertical agents. Use /process_event instead.",
        " verticals": [
            {"id": "release", "name": "Release Hygiene", "triggers": ["sentry.error", "github.deploy"]},
            {"id": "customer_fire", "name": "Customer Fire", "triggers": ["intercom.ticket", "zendesk.ticket"]},
            {"id": "runway", "name": "Runway/Money", "triggers": ["stripe.invoice", "stripe.payment_failed"]},
            {"id": "team_pulse", "name": "Team Pulse", "triggers": ["github.activity", "github.commit"]},
        ],
    }


@app.get("/sentinel/status")
async def sentinel_status() -> dict[str, Any]:
    """Get GitHub Sentinel status."""
    return {
        "status": "ready",
        "features": [
            "temporal_memory",
            "semantic_search",
            "policy_enforcement",
        ],
        "supported_events": ["pull_request"],
        "actions": ["block", "warn", "approve"],
    }


def create_app() -> FastAPI:
    """Factory for creating the FastAPI app."""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
