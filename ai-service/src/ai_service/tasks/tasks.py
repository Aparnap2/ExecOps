"""Celery tasks for ExecOps.

These tasks handle async processing:
- process_event_task: Process an event through the vertical agent graph
- execute_proposal_task: Execute an approved proposal
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from celery import Celery, shared_task

logger = logging.getLogger(__name__)


# =============================================================================
# Celery Configuration
# =============================================================================

# Configure Celery with Redis as broker and result backend
celery_app = Celery(
    "execops",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["ai_service.tasks.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
)


# =============================================================================
# Async Helper
# =============================================================================

async def _run_async(coro):
    """Run async code in sync Celery context."""
    return await coro


# =============================================================================
# Task: Process Event
# =============================================================================

@shared_task(
    bind=True,
    name="execops.process_event",
    max_retries=3,
    default_retry_delay=60,
    exponential_backoff=True,
)
def process_event_task(self, event_id: str) -> dict[str, Any]:
    """Process an event through the vertical agent graph.

    This is the main Celery task that:
    1. Fetches the event from the database
    2. Routes it to the appropriate vertical agent
    3. Runs the LangGraph to generate a proposal
    4. Persists the proposal to the database

    Args:
        event_id: The event ID to process

    Returns:
        Dict with proposal_id and status
    """
    logger.info(f"Processing event: {event_id}")

    try:
        from prisma import Prisma
        from ai_service.graphs import (
            route_to_vertical,
            create_vertical_agent_graph,
            ActionProposalState,
        )

        prisma = Prisma()

        async def _fetch_event():
            return await prisma.event.find_unique(where={"id": event_id})

        async def _create_proposal(result, vertical):
            return await prisma.actionproposal.create(
                data={
                    "id": result.get("event_id") or f"prop_{event_id}",
                    "status": result.get("status", "pending"),
                    "urgency": result.get("urgency", "medium"),
                    "vertical": vertical,
                    "action_type": result.get("draft_action", {}).get("action_type", "unknown"),
                    "payload": result.get("draft_action", {}).get("payload", {}),
                    "reasoning": result.get("analysis", {}).get("reasoning", ""),
                    "context_summary": result.get("analysis", {}).get("context_summary", ""),
                    "event_id": event_id,
                    "confidence": result.get("confidence", 0.8),
                    "created_at": datetime.utcnow(),
                }
            )

        async def _mark_processed():
            await prisma.event.update(
                where={"id": event_id},
                data={"processed": True},
            )

        async def _log_audit(proposal_id, vertical):
            await prisma.auditlog.create(
                data={
                    "action": "proposal_created",
                    "entity_type": "action_proposal",
                    "entity_id": proposal_id,
                    "payload": {
                        "event_id": event_id,
                        "vertical": vertical,
                        "urgency": result.get("urgency", "medium"),
                    },
                }
            )

        # Run async operations
        event = asyncio.run(_fetch_event())

        if not event:
            logger.error(f"Event not found: {event_id}")
            return {"error": "Event not found", "event_id": event_id}

        # Route to vertical
        event_type = event.source_type or "generic"
        vertical = route_to_vertical(event_type)

        logger.info(f"Routing event {event_id} to vertical: {vertical}")

        # Create initial state
        state = ActionProposalState(
            event_id=event.id,
            event_type=event_type,
            vertical=vertical,
            urgency="medium",
            status="pending",
            confidence=0.0,
            event_context=event.payload or {},
        )

        # Get and compile graph
        graph = create_vertical_agent_graph(vertical)

        # Execute graph with checkpointer
        config = {"configurable": {"thread_id": event.id}}
        result = graph.invoke(state, config=config)

        # Create proposal in database
        proposal = asyncio.run(_create_proposal(result, vertical))

        # Mark event as processed
        asyncio.run(_mark_processed())

        # Log to audit
        asyncio.run(_log_audit(proposal.id, vertical))

        logger.info(f"Created proposal: {proposal.id}")

        return {
            "proposal_id": proposal.id,
            "status": proposal.status,
            "vertical": vertical,
        }

    except Exception as e:
        logger.error(f"Error processing event {event_id}: {e}")
        raise self.retry(exc=e)


# =============================================================================
# Task: Execute Proposal
# =============================================================================

@shared_task(
    bind=True,
    name="execops.execute_proposal",
    max_retries=3,
    default_retry_delay=30,
    exponential_backoff=True,
)
def execute_proposal_task(
    self,
    proposal_id: str,
    actor: str = "system",
) -> dict[str, Any]:
    """Execute an approved action proposal.

    This task:
    1. Fetches the approved proposal
    2. Creates an Execution record
    3. Calls the appropriate executor (Slack, Email, Webhook, etc.)
    4. Updates the execution status

    Args:
        proposal_id: The proposal ID to execute
        actor: Who triggered the execution (user:xxx or system)

    Returns:
        Dict with execution result
    """
    logger.info(f"Executing proposal: {proposal_id}")

    try:
        from prisma import Prisma
        from ai_service.integrations.executor import execute_proposal

        prisma = Prisma()

        async def _fetch_proposal():
            return await prisma.actionproposal.find_unique(where={"id": proposal_id})

        async def _create_execution():
            return await prisma.execution.create(
                data={
                    "id": str(uuid.uuid4()),
                    "proposal_id": proposal_id,
                    "status": "running",
                    "started_at": datetime.utcnow(),
                }
            )

        async def _update_execution(exec_id, success, result, error):
            await prisma.execution.update(
                where={"id": exec_id},
                data={
                    "status": "succeeded" if success else "failed",
                    "finished_at": datetime.utcnow(),
                    "result": result,
                    "error": error,
                }
            )

        async def _update_proposal(status, executed_at=None):
            data = {"status": status}
            if executed_at:
                data["executed_at"] = executed_at
            await prisma.actionproposal.update(
                where={"id": proposal_id},
                data=data,
            )

        async def _log_audit(exec_id, success, error):
            await prisma.auditlog.create(
                data={
                    "action": "execution_completed",
                    "entity_type": "execution",
                    "entity_id": exec_id,
                    "payload": {
                        "proposal_id": proposal_id,
                        "success": success,
                        "error": error,
                        "actor": actor,
                    },
                }
            )

        # Fetch proposal
        proposal = asyncio.run(_fetch_proposal())

        if not proposal:
            logger.error(f"Proposal not found: {proposal_id}")
            return {"error": "Proposal not found", "proposal_id": proposal_id}

        if proposal.status != "approved":
            logger.error(f"Proposal not approved: {proposal_id}, status={proposal.status}")
            return {"error": "Proposal not approved", "proposal_id": proposal_id}

        # Create execution record
        execution = asyncio.run(_create_execution())

        # Execute the action
        result = asyncio.run(
            execute_proposal(
                proposal_id=proposal_id,
                action_type=proposal.action_type,
                payload=proposal.payload or {},
            )
        )

        # Update execution and proposal
        asyncio.run(_update_execution(execution.id, result.success, result.result, result.error))
        asyncio.run(_update_proposal("executed" if result.success else "failed", datetime.utcnow()))

        # Log to audit
        asyncio.run(_log_audit(execution.id, result.success, result.error))

        logger.info(
            f"Execution completed: proposal={proposal_id}, "
            f"success={result.success}"
        )

        return {
            "execution_id": execution.id,
            "proposal_id": proposal_id,
            "success": result.success,
            "error": result.error,
        }

    except Exception as e:
        logger.error(f"Error executing proposal {proposal_id}: {e}")
        raise self.retry(exc=e)


# =============================================================================
# Health Check Task
# =============================================================================

@shared_task(name="execops.health")
def health_check_task() -> dict[str, str]:
    """Simple health check task."""
    return {"status": "healthy", "service": "execops-tasks"}
