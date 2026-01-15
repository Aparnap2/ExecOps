"""GitHub webhook handler for the Sentinel agent.

This module provides the FastAPI router for handling GitHub webhook
events and processing them through the Sentinel agent.
"""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, Request, HTTPException

from .github import GitHubClient
from ..agent.nodes import create_sentinel_agent, format_block_message, format_warning_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Configuration - should come from environment in production
GITHUB_WEBHOOK_SECRET: str | None = None  # Set via environment
GITHUB_TOKEN: str = ""  # Set via environment
GITHUB_OWNER: str = ""  # Set via environment
GITHUB_REPO: str = ""  # Set via environment


def verify_signature(payload: bytes, signature: str | None) -> bool:
    """Verify GitHub webhook signature.

    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value

    Returns:
        True if signature is valid
    """
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("Webhook secret not configured, skipping verification")
        return True

    if not signature:
        logger.warning("No signature provided")
        return False

    expected = f"sha256={hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()}"

    if not hmac.compare_digest(signature, expected):
        logger.warning("Signature mismatch")
        return False

    return True


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(None, alias="X-GitHub-Delivery"),
) -> dict[str, Any]:
    """Handle GitHub webhook events.

    This endpoint receives GitHub webhook events and processes them
    through the Sentinel agent for policy enforcement.

    Args:
        request: FastAPI request object
        x_hub_signature_256: Webhook signature
        x_github_event: Event type
        x_github_delivery: Event delivery ID

    Returns:
        Response dict with status and action taken
    """
    # Get raw body for signature verification
    payload = await request.body()

    # Verify signature (skip if no secret configured)
    if not verify_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    import json
    event = json.loads(payload)

    delivery_id = x_github_delivery or "unknown"
    event_type = x_github_event or "unknown"

    logger.info(f"Received webhook event: {event_type} (delivery: {delivery_id})")

    # Process only pull_request events
    if event_type != "pull_request":
        logger.info(f"Ignoring event type: {event_type}")
        return {
            "status": "ignored",
            "event": event_type,
            "delivery_id": delivery_id,
        }

    action = event.get("action")

    # Only process opened and synchronize events
    if action not in ("opened", "synchronize", "reopened"):
        logger.info(f"Ignoring action: {action}")
        return {
            "status": "ignored",
            "action": action,
            "event": event_type,
            "delivery_id": delivery_id,
        }

    logger.info(f"Processing PR action: {action}")

    try:
        # Create the Sentinel agent
        agent = create_sentinel_agent()

        # Create initial state
        from ..agent.state import create_initial_state
        initial_state = create_initial_state(event, action)

        # Run the agent
        result = agent.invoke(initial_state)

        # Get decision info
        decision = result.get("decision", "approve")
        should_block = result.get("should_block", False)
        should_warn = result.get("should_warn", False)
        violations = result.get("violations", [])

        action_taken = None

        # Comment on PR if blocked or warning
        if (should_block or should_warn) and GITHUB_TOKEN:
            pr_info = result.get("pr_info", {})
            pr_number = pr_info.get("number", 0)

            if pr_number > 0 and GITHUB_OWNER and GITHUB_REPO:
                github_client = GitHubClient(
                    token=GITHUB_TOKEN,
                    owner=GITHUB_OWNER,
                    repo=GITHUB_REPO,
                )

                if should_block:
                    message = format_block_message(violations)
                    await github_client.comment_on_pr(pr_number, message)
                    action_taken = "blocked"
                    logger.info(f"Blocked PR #{pr_number}")
                elif should_warn:
                    message = format_warning_message(violations)
                    await github_client.comment_on_pr(pr_number, message)
                    action_taken = "warned"
                    logger.info(f"Warned on PR #{pr_number}")

        return {
            "status": "processed",
            "event": event_type,
            "action": action,
            "decision": decision,
            "violations": len(violations),
            "action_taken": action_taken,
            "confidence": result.get("confidence", 1.0),
            "delivery_id": delivery_id,
        }

    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
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
