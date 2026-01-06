"""
Main FastAPI application for AI Service.

Exposes LangGraph SOP workflows via REST API.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .schemas.sop import DecisionRequest, DecisionResponse
from .graphs.sop_graph import SopState, create_sop_graph, sop_router

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
    logger.info("SOP graphs loaded and ready")
    yield
    logger.info("Shutting down AI Service...")


app = FastAPI(
    title="FounderOS AI Service",
    description="Agentic SOP automation for SaaS founders",
    version="0.1.0",
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


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-service"}


@app.post("/decide", response_model=DecisionResponse)
async def decide(req: DecisionRequest) -> DecisionResponse:
    """
    Main decision endpoint for SOP execution.

    Accepts a DecisionRequest with events and context,
    runs the appropriate SOP graph, and returns a DecisionResponse.
    """
    logger.info(
        f"Received decision request: request_id={req.request_id}, objective={req.objective}"
    )

    try:
        # Validate objective
        valid_objectives = ["lead_hygiene", "support_triage", "ops_hygiene", "all"]
        if req.objective not in valid_objectives:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid objective. Must be one of: {valid_objectives}",
            )

        # Create initial state
        initial_state = SopState(
            request_id=req.request_id,
            objective=req.objective,
            events=req.events,
            constraints=req.constraints,
        )

        # Create and run graph
        graph = create_sop_graph(req.objective)
        compiled_graph = graph.compile()

        logger.info(f"Executing {sop_router(req.objective)} graph...")
        result = compiled_graph.invoke(initial_state)

        # Helper to convert Pydantic objects to dicts
        def to_dict(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            elif isinstance(obj, list):
                return [to_dict(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: to_dict(v) for k, v in obj.items()}
            return obj

        # Build response
        response = DecisionResponse(
            request_id=req.request_id,
            state=result.get("decision_state", "CONFIDENT"),
            summary=result.get("summary", ""),
            confidence=result.get("data_completeness", 1.0)
            * (1 - result.get("ambiguity", 0.0))
            * (1 - result.get("rule_violations", 0.0)),
            confidence_breakdown={
                "data_completeness": result.get("data_completeness", 1.0),
                "ambiguity": result.get("ambiguity", 0.0),
                "rule_violations": result.get("rule_violations", 0.0),
            },
            recommendations=to_dict(result.get("recommendations", [])),
            escalations=to_dict(result.get("escalations", [])),
            executed_sops=result.get("executed_sops", []),
        )

        logger.info(
            f"Decision complete: state={response.state}, confidence={response.confidence:.2f}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing decision request: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/sops")
async def list_sops() -> dict[str, Any]:
    """List available SOPs."""
    return {
        "sops": [
            {
                "id": "sop_001",
                "name": "lead_hygiene",
                "description": "Ensure leads are not stale with missing status",
                "trigger": "daily",
            },
            {
                "id": "sop_010",
                "name": "support_triage",
                "description": "Detect urgent tickets and customer sentiment issues",
                "trigger": "real-time",
            },
            {
                "id": "sop_015",
                "name": "ops_hygiene",
                "description": "Detect missing fields and sync errors",
                "trigger": "daily",
            },
        ]
    }


def create_app() -> FastAPI:
    """Factory for creating the FastAPI app."""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
