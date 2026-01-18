"""GitHub Webhook Handler for Sentinel Agent.

This module provides the FastAPI route for handling GitHub webhook
events and processing them through the Sentinel agent for PR review.

Extends patterns from `ai_service.integrations.webhook.py`.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from ai_service.agents.sentinel.graph import get_sentinel_graph
from ai_service.infrastructure.checkpointer import GraphCheckpointerConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Configuration - should come from environment in production
GITHUB_WEBHOOK_SECRET: str | None = None  # Set via GITHUB_WEBHOOK_SECRET env


def verify_signature(payload: bytes, signature: str | None) -> bool:
    """Verify GitHub webhook signature.

    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value

    Returns:
        True if signature is valid
    """
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("Webhook secret not configured, skipping signature verification")
        return True

    if not signature:
        logger.warning("No signature provided in webhook request")
        return False

    expected = f"sha256={hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()}"

    if not hmac.compare_digest(signature, expected):
        logger.warning("Webhook signature mismatch")
        return False

    return True


@router.post("/github")
async def github_webhook(request: Request) -> dict[str, Any]:
    """Handle GitHub webhook events.

    This endpoint receives GitHub webhook events and triggers the Sentinel
    agent for PR review on pull_request events.

    Supported events:
        - pull_request (actions: opened, synchronize)

    Args:
        request: FastAPI request with GitHub payload

    Returns:
        Response dict with status and action taken
    """
    # Get raw body for signature verification
    payload_body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(payload_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse payload
    try:
        payload = json.loads(payload_body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Get event metadata
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "unknown")

    logger.info(f"Received GitHub webhook: event={event_type}, delivery={delivery_id}")

    # Only process pull_request events
    if event_type != "pull_request":
        logger.info(f"Ignoring event type: {event_type}")
        return {
            "status": "ignored",
            "event": event_type,
            "delivery_id": delivery_id,
        }

    action = payload.get("action")

    # Only process opened and synchronize events
    if action not in ("opened", "synchronize"):
        logger.info(f"Ignoring PR action: {action}")
        return {
            "status": "ignored",
            "action": action,
            "event": event_type,
            "delivery_id": delivery_id,
        }

    # Extract PR information
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    pr_id = str(pr.get("id"))
    pr_title = pr.get("title", "")
    pr_body = pr.get("body", "")
    pr_author = pr.get("user", {}).get("login", "unknown")
    pr_url = pr.get("html_url", "")

    logger.info(f"Processing PR #{pr_number} by {pr_author}: {pr_title[:50]}...")

    try:
        # Create initial SentinelState
        initial_state = {
            "event_id": f"gh-pr-{pr_id}",
            "event_type": "github.pr",
            "vertical": "sentinel",
            "urgency": "medium",
            # PR context
            "pr_number": pr_number,
            "pr_id": pr_id,
            "pr_title": pr_title,
            "pr_body": pr_body,
            "pr_author": pr_author,
            "pr_url": pr_url,
            # Linear context (will be populated by graph nodes)
            "linear_issue_id": None,
            "linear_issue_state": None,
            "linear_issue_labels": [],
            # Graph context
            "issue_context": None,
            "risk_score": 0.0,
            # Sentinel decision
            "violations": [],
            "sentinel_decision": None,
            # Processing state
            "status": "pending",
            "analysis": None,
            "draft_action": None,
            "confidence": 0.0,
            # Approval workflow
            "approval_required": True,
            "approval_decision": None,
            "approver_id": None,
            "rejection_reason": None,
            # Execution tracking
            "ready_to_execute": False,
            "executed_at": None,
            # Error handling
            "error": None,
        }

        # Get graph configuration
        thread_id = GraphCheckpointerConfig.get_thread_id(pr_id, "sentinel")
        config = GraphCheckpointerConfig.get_configurable(thread_id)

        # Invoke Sentinel graph
        graph = await get_sentinel_graph()
        await graph.ainvoke(initial_state, config=config)

        logger.info(f"Sentinel invoked successfully for PR #{pr_number}")

        return {
            "status": "processed",
            "pr": pr_number,
            "pr_id": pr_id,
            "action": action,
            "event": event_type,
            "delivery_id": delivery_id,
        }

    except Exception as e:
        logger.exception(f"Error processing webhook for PR #{pr_number}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing webhook: {str(e)}"
        )


@router.get("/github")
async def webhook_health() -> dict[str, str]:
    """Webhook endpoint health check.

    Returns:
        Health status
    """
    return {"status": "healthy", "service": "github-webhook"}
