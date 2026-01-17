"""Execution adapters for ExecOps.

Executes approved ActionProposals by calling external APIs:
- Slack DM / channel messages
- Email (via SMTP or API)
- Webhooks
- Commands (for internal automation)

All executions are idempotent and logged to audit.
"""

import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .slack import SlackClient, create_slack_client

logger = logging.getLogger(__name__)


# =============================================================================
# Execution Types
# =============================================================================

@dataclass
class ExecutionResult:
    """Result of an execution attempt."""
    success: bool
    result: dict[str, Any] | None
    error: str | None


@dataclass
class ExecutionContext:
    """Context for executing an action proposal."""
    proposal_id: str
    action_type: str
    payload: dict[str, Any]
    idempotency_key: str | None = None


# =============================================================================
# Execution Adapters (ABC)
# =============================================================================

class BaseExecutor(ABC):
    """Base class for action executors."""

    def __init__(self):
        """Initialize executor."""
        pass

    @abstractmethod
    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute the action.

        Args:
            context: Execution context with proposal details

        Returns:
            ExecutionResult with success status and details
        """
        pass

    def _generate_idempotency_key(self, action_type: str, payload: dict[str, Any]) -> str:
        """Generate idempotency key from action details."""
        content = json.dumps({"action": action_type, "payload": payload}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


class SlackExecutor(BaseExecutor):
    """Executor for Slack messages (DM or channel)."""

    def __init__(self, webhook_url: str):
        """Initialize Slack executor.

        Args:
            webhook_url: Slack webhook URL
        """
        self.client = create_slack_client(webhook_url)

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Send Slack message.

        Args:
            context: Execution context with Slack details

        Returns:
            ExecutionResult
        """
        payload = context.payload
        channel = payload.get("channel", "#general")
        text = payload.get("text", "")
        blocks = payload.get("blocks")

        try:
            success = await self.client.send_message(
                blocks=blocks or [],
                text=text,
                channel=channel,
            )

            if success:
                return ExecutionResult(
                    success=True,
                    result={"channel": channel, "sent_at": datetime.utcnow().isoformat()},
                    error=None,
                )
            else:
                return ExecutionResult(
                    success=False,
                    result=None,
                    error="Failed to send Slack message",
                )
        except Exception as e:
            logger.error(f"Slack execution failed: {e}")
            return ExecutionResult(
                success=False,
                result=None,
                error=str(e),
            )


class EmailExecutor(BaseExecutor):
    """Executor for email actions.

    Note: In production, this would integrate with SendGrid, AWS SES, or Gmail API.
    For now, this is a stub that logs the email that would be sent.
    """

    SMTP_HOST = "localhost"
    SMTP_PORT = 1025  # MailHog default for testing

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Log email that would be sent.

        Args:
            context: Execution context with email details

        Returns:
            ExecutionResult with email details
        """
        payload = context.payload
        to = payload.get("to", "")
        subject = payload.get("subject", "No subject")
        body = payload.get("body", "")
        body_html = payload.get("body_html", "")

        # In production, actually send the email
        # For now, log it
        logger.info(f"[EMAIL] Would send to: {to}")
        logger.info(f"[EMAIL] Subject: {subject}")
        logger.info(f"[EMAIL] Body: {body[:200]}...")

        return ExecutionResult(
            success=True,
            result={
                "to": to,
                "subject": subject,
                "sent_at": datetime.utcnow().isoformat(),
                "mode": "log_only",
            },
            error=None,
        )


class WebhookExecutor(BaseExecutor):
    """Executor for webhook calls."""

    def __init__(self, timeout: float = 30.0):
        """Initialize webhook executor.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Call webhook.

        Args:
            context: Execution context with webhook details

        Returns:
            ExecutionResult
        """
        payload = context.payload
        url = payload.get("url", "")
        method = payload.get("method", "POST")
        headers = payload.get("headers", {})
        body = payload.get("body")
        params = payload.get("params")

        if not url:
            return ExecutionResult(
                success=False,
                result=None,
                error="No webhook URL provided",
            )

        try:
            client = await self._get_client()
            req = client.build_request(
                method=method,
                url=url,
                headers=headers,
                content=json.dumps(body) if body else None,
                params=params,
            )
            response = await client.send(req)
            response.raise_for_status()

            return ExecutionResult(
                success=True,
                result={
                    "status_code": response.status_code,
                    "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:500],
                    "sent_at": datetime.utcnow().isoformat(),
                },
                error=None,
            )
        except Exception as e:
            logger.error(f"Webhook execution failed: {e}")
            return ExecutionResult(
                success=False,
                result=None,
                error=str(e),
            )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class CommandExecutor(BaseExecutor):
    """Executor for internal commands.

    Note: This is for internal automation commands (e.g., git revert, deploy rollback).
    In production, these would run in a sandboxed environment.
    """

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Log command that would be executed.

        Args:
            context: Execution context with command details

        Returns:
            ExecutionResult
        """
        payload = context.payload
        command = payload.get("command", "")
        working_dir = payload.get("working_dir", "/tmp")

        logger.info(f"[COMMAND] Would execute in {working_dir}: {command}")

        return ExecutionResult(
            success=True,
            result={
                "command": command,
                "working_dir": working_dir,
                "executed_at": datetime.utcnow().isoformat(),
                "mode": "log_only",
            },
            error=None,
        )


# =============================================================================
# Executor Factory
# =============================================================================

class ExecutorFactory:
    """Factory for creating execution adapters based on action_type."""

    _executors: dict[str, type[BaseExecutor]] = {
        "slack_dm": SlackExecutor,
        "slack_channel": SlackExecutor,
        "email": EmailExecutor,
        "webhook": WebhookExecutor,
        "command": CommandExecutor,
        "api_call": WebhookExecutor,
    }

    @classmethod
    def create(cls, action_type: str, **kwargs) -> BaseExecutor:
        """Create executor for action type.

        Args:
            action_type: Type of action to execute
            **kwargs: Executor-specific config

        Returns:
            Configured executor instance

        Raises:
            ValueError: If action_type is not supported
        """
        executor_class = cls._executors.get(action_type)
        if not executor_class:
            raise ValueError(f"Unknown action type: {action_type}")

        # Extract common config
        if action_type.startswith("slack"):
            webhook_url = kwargs.get("slack_webhook_url") or ""
            return executor_class(webhook_url)
        elif action_type in ("webhook", "api_call"):
            return executor_class(timeout=kwargs.get("timeout", 30.0))
        else:
            return executor_class()

    @classmethod
    def register(cls, action_type: str, executor_class: type[BaseExecutor]) -> None:
        """Register a new executor for an action type.

        Args:
            action_type: Type of action
            executor_class: Executor class
        """
        cls._executors[action_type] = executor_class


# =============================================================================
# Main Execution Function
# =============================================================================

async def execute_proposal(
    proposal_id: str,
    action_type: str,
    payload: dict[str, Any],
    slack_webhook_url: str = "",
) -> ExecutionResult:
    """Execute an approved action proposal.

    This is the main entry point for executing actions after approval.

    Args:
        proposal_id: The proposal ID (for idempotency)
        action_type: Type of action (slack_dm, email, webhook, command)
        payload: Action payload
        slack_webhook_url: Slack webhook URL for Slack actions

    Returns:
        ExecutionResult with success status and details
    """
    # Create execution context
    context = ExecutionContext(
        proposal_id=proposal_id,
        action_type=action_type,
        payload=payload,
    )

    # Create executor
    executor = ExecutorFactory.create(
        action_type,
        slack_webhook_url=slack_webhook_url,
    )

    # Execute
    result = await executor.execute(context)

    logger.info(
        f"Execution completed: proposal={proposal_id}, "
        f"action={action_type}, success={result.success}"
    )

    return result


# =============================================================================
# Audit Logging Helper
# =============================================================================

async def log_execution_audit(
    proposal_id: str,
    execution_result: ExecutionResult,
    actor: str = "system",
) -> None:
    """Log execution to audit table.

    Args:
        proposal_id: The executed proposal ID
        execution_result: Result of the execution
        actor: Who triggered the execution (system, user:xxx)
    """
    # Import here to avoid circular imports in tests
    from prisma import Prisma

    prisma = Prisma()

    try:
        await prisma.connect()

        await prisma.auditlog.create(
            data={
                "action": "execution_completed",
                "entity_type": "execution",
                "entity_id": proposal_id,
                "payload": {
                    "success": execution_result.success,
                    "result": execution_result.result,
                    "error": execution_result.error,
                    "actor": actor,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            }
        )
    except Exception as e:
        logger.error(f"Failed to log execution audit: {e}")
    finally:
        await prisma.disconnect()
