"""Human Approval Workflow for LangGraph.

This module provides:
- Approval state management with Redis persistence
- Human-in-the-loop pause/resume using LangGraph interrupts
- Slack integration for approval requests
- Timeout management for pending approvals
"""

import logging
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# Default timeout for approvals (24 hours)
DEFAULT_APPROVAL_TIMEOUT_HOURS = 24


@dataclass
class ApprovalState:
    """State of a human approval request."""

    workflow_id: str
    agent_name: str
    trigger_event: str
    status: str  # "pending", "approved", "rejected", "expired", "cancelled"
    context: dict
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=DEFAULT_APPROVAL_TIMEOUT_HOURS))
    approval_id: str = field(default_factory=lambda: f"approval_{uuid.uuid4().hex[:12]}")
    requester: str = "system"
    decision: str | None = None
    approver: str | None = None
    resume_value: dict | None = None
    slack_message_ts: str | None = None
    slack_channel: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "workflow_id": self.workflow_id,
            "agent_name": self.agent_name,
            "trigger_event": self.trigger_event,
            "status": self.status,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "approval_id": self.approval_id,
            "requester": self.requester,
            "decision": self.decision,
            "approver": self.approver,
            "resume_value": self.resume_value,
            "slack_message_ts": self.slack_message_ts,
            "slack_channel": self.slack_channel,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalState":
        """Create from dictionary."""
        return cls(
            workflow_id=data["workflow_id"],
            agent_name=data["agent_name"],
            trigger_event=data["trigger_event"],
            status=data["status"],
            context=data.get("context", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if "expires_at" in data else datetime.utcnow() + timedelta(hours=DEFAULT_APPROVAL_TIMEOUT_HOURS),
            approval_id=data.get("approval_id", f"approval_{uuid.uuid4().hex[:12]}"),
            requester=data.get("requester", "system"),
            decision=data.get("decision"),
            approver=data.get("approver"),
            resume_value=data.get("resume_value"),
            slack_message_ts=data.get("slack_message_ts"),
            slack_channel=data.get("slack_channel"),
        )


class SlackApprovalClient:
    """Slack client for approval messages."""

    def __init__(self, webhook_url: str | None = None, bot_token: str | None = None) -> None:
        """Initialize Slack client.

        Args:
            webhook_url: Slack incoming webhook URL
            bot_token: Slack bot token (xoxb-...)
        """
        self.webhook_url = webhook_url
        self.bot_token = bot_token

    async def send_approval_request(
        self,
        channel: str,
        blocks: list[dict],
        text: str,
    ) -> dict:
        """Send approval request to Slack channel.

        Args:
            channel: Slack channel ID
            blocks: Slack blocks for the message
            text: Fallback text

        Returns:
            API response with channel and timestamp
        """
        import httpx

        if self.bot_token:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": channel,
                        "blocks": blocks,
                        "text": text,
                    },
                )
                return response.json()
        elif self.webhook_url:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={
                        "channel": channel,
                        "blocks": blocks,
                        "text": text,
                    },
                )
                return {"ok": True, "channel": channel, "ts": str(datetime.utcnow().timestamp())}
        else:
            logger.warning("No Slack credentials configured")
            return {"ok": False, "error": "No credentials"}

    async def update_message(
        self,
        channel: str,
        ts: str,
        blocks: list[dict],
        text: str,
    ) -> dict:
        """Update Slack message with approval result.

        Args:
            channel: Slack channel ID
            ts: Message timestamp
            blocks: Updated blocks
            text: Updated fallback text

        Returns:
            API response
        """
        import httpx

        if self.bot_token:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.update",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": channel,
                        "ts": ts,
                        "blocks": blocks,
                        "text": text,
                    },
                )
                return response.json()
        else:
            return {"ok": True}


class HumanApprovalManager:
    """Manages human approval workflows with Redis persistence."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        slack_client: SlackApprovalClient | None = None,
        timeout_hours: int = DEFAULT_APPROVAL_TIMEOUT_HOURS,
    ) -> None:
        """Initialize approval manager.

        Args:
            redis_url: Redis connection URL
            slack_client: Slack client for approval messages
            timeout_hours: Approval timeout in hours
        """
        self.redis_url = redis_url
        self.slack_client = slack_client
        self.timeout_hours = timeout_hours
        self._redis = None

    async def _get_redis(self):
        """Get or create Redis client."""
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self.redis_url)
            except ImportError:
                logger.warning("redis-py not installed, using mock")
                self._redis = None
        return self._redis

    async def create_approval_request(
        self,
        state: ApprovalState,
        slack_channel: str,
        requester: str,
        message: str,
    ) -> str:
        """Create a new approval request.

        Args:
            state: ApprovalState with workflow context
            slack_channel: Slack channel for approval request
            requester: Name of the requester (agent name)
            message: Human-readable message

        Returns:
            approval_id
        """
        redis = await self._get_redis()

        # Set initial state
        state.requester = requester
        state.status = "pending"
        state.slack_channel = slack_channel

        # Send Slack message
        if self.slack_client:
            blocks = create_approval_blocks(
                approval_id=state.approval_id,
                agent_name=state.agent_name,
                trigger=state.trigger_event,
                context=state.context,
                decision_needed=message,
            )
            slack_result = await self.slack_client.send_approval_request(
                channel=slack_channel,
                blocks=blocks,
                text=f"Approval required: {message}",
            )
            if slack_result.get("ok"):
                state.slack_message_ts = slack_result.get("ts")

        # Store in Redis
        if redis:
            await redis.set(
                f"approval:{state.approval_id}",
                json.dumps(state.to_dict()),
                ex=self.timeout_hours * 3600,
            )

        logger.info(f"Created approval request {state.approval_id} for workflow {state.workflow_id}")

        return state.approval_id

    async def get_approval(self, approval_id: str) -> ApprovalState | None:
        """Get approval state by ID.

        Args:
            approval_id: The approval ID

        Returns:
            ApprovalState or None if not found
        """
        redis = await self._get_redis()

        if redis:
            data = await redis.get(f"approval:{approval_id}")
            if data:
                return ApprovalState.from_dict(json.loads(data))

        return None

    async def process_decision(
        self,
        approval_id: str,
        decision: str,
        approver: str,
    ) -> ApprovalState:
        """Process approval decision (approve/reject).

        Args:
            approval_id: The approval ID
            decision: "approve" or "reject"
            approver: User ID or email who made the decision

        Returns:
            Updated ApprovalState
        """
        state = await self.get_approval(approval_id)
        if not state:
            raise ValueError(f"Approval {approval_id} not found")

        state.decision = decision
        state.approver = approver
        state.status = "approved" if decision == "approve" else "rejected"
        state.resume_value = {"approved": decision == "approve", "decision": decision}

        # Update Slack message
        if self.slack_client and state.slack_message_ts and state.slack_channel:
            blocks = create_result_blocks(state)
            await self.slack_client.update_message(
                channel=state.slack_channel,
                ts=state.slack_message_ts,
                blocks=blocks,
                text=f"Approval {decision} by {approver}",
            )

        # Update Redis
        redis = await self._get_redis()
        if redis:
            await redis.set(
                f"approval:{approval_id}",
                json.dumps(state.to_dict()),
                ex=self.timeout_hours * 3600,
            )

        logger.info(f"Processed decision {decision} for approval {approval_id}")

        return state

    async def check_timeout(self, approval_id: str) -> bool:
        """Check if approval has timed out.

        Args:
            approval_id: The approval ID

        Returns:
            True if expired
        """
        state = await self.get_approval(approval_id)
        if not state:
            return True

        return datetime.utcnow() > state.expires_at

    async def list_pending_approvals(self) -> list[ApprovalState]:
        """List all pending approvals.

        Returns:
            List of pending ApprovalStates
        """
        redis = await self._get_redis()
        if not redis:
            return []

        keys = await redis.keys("approval:*")
        if not keys:
            return []

        values = await redis.mget(keys)
        pending = []

        for value in values:
            if value:
                state = ApprovalState.from_dict(json.loads(value))
                if state.status == "pending":
                    pending.append(state)

        return pending

    async def cancel_approval(self, approval_id: str, reason: str = "cancelled") -> ApprovalState | None:
        """Cancel an approval request.

        Args:
            approval_id: The approval ID
            reason: Cancellation reason

        Returns:
            Updated ApprovalState or None
        """
        state = await self.get_approval(approval_id)
        if not state:
            return None

        state.status = "cancelled"
        state.resume_value = {"approved": None, "reason": reason}

        redis = await self._get_redis()
        if redis:
            await redis.set(
                f"approval:{approval_id}",
                json.dumps(state.to_dict()),
                ex=self.timeout_hours * 3600,
            )

        return state


def format_approval_message(
    agent_name: str,
    trigger: str,
    context: dict,
    urgency: str = "normal",
) -> str:
    """Format approval request message.

    Args:
        agent_name: Name of the agent requesting approval
        trigger: What triggered the request
        context: Additional context
        urgency: Urgency level

    Returns:
        Formatted message
    """
    context_str = ", ".join(f"{k}: {v}" for k, v in context.items())
    urgency_emoji = {"low": "", "normal": "", "high": "🔴", "critical": "🚨"}

    return f"{urgency_emoji.get(urgency, '')} *{agent_name}* requires approval for {trigger}. {context_str}".strip()


def create_approval_blocks(
    approval_id: str,
    agent_name: str,
    trigger: str,
    context: dict,
    decision_needed: str,
) -> list[dict]:
    """Create Slack blocks for approval request.

    Args:
        approval_id: Unique approval ID
        agent_name: Agent requesting approval
        trigger: What triggered the request
        context: Additional context
        decision_needed: Description of decision needed

    Returns:
        Slack block kit
    """
    # Format context
    context_lines = []
    for k, v in context.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                context_lines.append(f"*{k}*: {v2}")
        else:
            context_lines.append(f"*{k}*: {v}")

    context_text = "\n".join(context_lines) if context_lines else "No additional context"

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Approval Required: {agent_name}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{trigger}*\n\n{decision_needed}",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Context:*\n{context_text}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Approval ID:*\n`{approval_id}`",
                },
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Approve",
                        "emoji": True,
                    },
                    "style": "primary",
                    "action_id": "approve",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Reject",
                        "emoji": True,
                    },
                    "style": "danger",
                    "action_id": "reject",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Details",
                        "emoji": True,
                    },
                    "action_id": "details",
                    "value": approval_id,
                },
            ],
        },
    ]


def create_result_blocks(state: ApprovalState) -> list[dict]:
    """Create Slack blocks for approval result.

    Args:
        state: Completed ApprovalState

    Returns:
        Slack block kit
    """
    status_emoji = {
        "approved": "✅",
        "rejected": "❌",
        "cancelled": "⚫",
        "expired": "⏰",
    }

    status_text = state.status.upper()

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{status_emoji.get(state.status, '')} *{state.agent_name}* approval: *{status_text}*\n\nDecision by: {state.approver or 'Unknown'}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Approval ID: `{state.approval_id}` | Workflow: {state.workflow_id}",
                },
            ],
        },
    ]


# LangGraph State
class WorkflowState(TypedDict):
    """Extended state for human approval workflow."""

    # Core state
    event_type: str
    pr_info: dict | None
    invoice_context: dict | None
    diff_files: list[dict] | None

    # Analysis results
    security_report: dict | None
    budget_impact: dict | None
    tech_debt_report: dict | None

    # Decision
    decision: str
    confidence: float
    reason: str

    # Human approval
    requires_approval: bool
    workflow_id: str
    approval_id: str | None
    human_approved: bool | None
    resume_value: dict | None


def human_approval_node(state: WorkflowState) -> WorkflowState:
    """Human approval node for LangGraph.

    This node handles pausing for human approval when required.

    Args:
        state: Current workflow state

    Returns:
        Updated state with approval decision
    """
    requires_approval = state.get("requires_approval", False)
    approval_id = state.get("approval_id")
    resume_value = state.get("resume_value")

    # If no approval required, pass through
    if not requires_approval:
        return {
            **state,
            "human_approved": None,
        }

    # If we have a resume value, process the decision
    if resume_value:
        approved = resume_value.get("approved")
        decision = resume_value.get("decision", "reject")

        if approved:
            return {
                **state,
                "decision": "approve",
                "human_approved": True,
                "reason": f"Human approved: {state.get('reason', 'Approved via Slack')}",
            }
        else:
            return {
                **state,
                "decision": "block",
                "human_approved": False,
                "reason": f"Human rejected: {state.get('reason', 'Rejected via Slack')}",
            }

    # First time hitting this node - need approval
    # Generate workflow_id if not present
    workflow_id = state.get("workflow_id", f"wf_{uuid.uuid4().hex[:12]}")

    return {
        **state,
        "workflow_id": workflow_id,
        "approval_id": None,  # Will be set after creating approval
        "human_approved": None,
        # Signal to the graph that we need to interrupt
        "_interrupt": {
            "type": "approval_required",
            "workflow_id": workflow_id,
            "message": f"Approval needed: {state.get('reason', 'Manual review required')}",
        },
    }


async def handle_approval_callback(
    callback_data: dict,
    approval_manager: HumanApprovalManager | None = None,
) -> dict:
    """Handle Slack interaction callback.

    Args:
        callback_data: Slack callback payload
        approval_manager: Approval manager instance

    Returns:
        Response dict
    """
    import httpx

    action = callback_data.get("actions", [{}])[0]
    action_id = action.get("action_id")
    approval_id = action.get("value")

    user = callback_data.get("user", {}).get("id", "unknown")
    channel = callback_data.get("channel", {}).get("id", "unknown")

    if action_id not in ("approve", "reject"):
        return {"ok": False, "error": "Unknown action"}

    if not approval_manager:
        # Return mock response for testing
        return {
            "ok": True,
            "approval_id": approval_id,
            "decision": action_id,
            "user": user,
        }

    try:
        state = await approval_manager.process_decision(
            approval_id=approval_id,
            decision=action_id,
            approver=user,
        )

        return {
            "ok": True,
            "approval_id": approval_id,
            "decision": action_id,
            "workflow_id": state.workflow_id,
            "status": state.status,
        }
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def create_workflow_graph():
    """Create workflow graph with human approval.

    Returns:
        Compiled StateGraph
    """
    from langgraph.graph import StateGraph
    from langgraph.constants import START, END

    graph = StateGraph(WorkflowState)

    # Add human approval node
    graph.add_node("human_approval", human_approval_node)

    # Entry point
    graph.set_entry_point("human_approval")
    graph.add_edge("human_approval", END)

    return graph.compile()


# Convenience function for creating approval manager
def create_approval_manager(
    redis_url: str | None = None,
    slack_webhook_url: str | None = None,
    slack_bot_token: str | None = None,
) -> HumanApprovalManager:
    """Create approval manager with optional Slack integration.

    Args:
        redis_url: Redis connection URL
        slack_webhook_url: Slack incoming webhook
        slack_bot_token: Slack bot token

    Returns:
        HumanApprovalManager instance
    """
    slack_client = None
    if slack_webhook_url or slack_bot_token:
        slack_client = SlackApprovalClient(
            webhook_url=slack_webhook_url,
            bot_token=slack_bot_token,
        )

    return HumanApprovalManager(
        redis_url=redis_url or "redis://localhost:6379",
        slack_client=slack_client,
    )
