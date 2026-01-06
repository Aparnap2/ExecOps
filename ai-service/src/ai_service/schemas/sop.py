"""
Pydantic schemas for SOP AI Service.

Defines the request/response contracts between the JS frontend
and the Python LangGraph-based decision engine.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DecisionState(str, Enum):
    """Decision state enum for SOP outcomes."""

    CONFIDENT = "CONFIDENT"
    UNCERTAIN = "UNCERTAIN"
    ESCALATE = "ESCALATE"


class EventSource(str, Enum):
    """Supported event sources for ingestion."""

    SLACK = "slack"
    GMAIL = "gmail"
    STRIPE = "stripe"
    HUBSPOT = "hubspot"
    CUSTOM = "custom"


class EventPayload(BaseModel):
    """Normalized event payload from any source."""

    source: EventSource
    occurred_at: datetime
    external_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "source": "hubspot",
                    "occurred_at": "2025-01-06T10:00:00Z",
                    "external_id": "hs_12345",
                    "data": {"contact_id": "abc", "status": None, "last_contacted": None},
                }
            ]
        }
    }


class ConfidenceBreakdown(BaseModel):
    """Confidence score breakdown for explainability."""

    data_completeness: float = Field(..., ge=0, le=1, description="0-1 score for data quality")
    ambiguity: float = Field(..., ge=0, le=1, description="0-1 score for ambiguity in rules")
    rule_violations: float = Field(..., ge=0, le=1, description="0-1 score for rule violations")

    @property
    def overall(self) -> float:
        """Calculate overall confidence as weighted average."""
        return (self.data_completeness * 0.4) + (self.ambiguity * 0.3) + (self.rule_violations * 0.3)


class ActionRecommendation(BaseModel):
    """Recommended action from SOP execution."""

    type: str = Field(..., description="e.g., 'email', 'crm_update', 'slack_message'")
    target: str | None = Field(None, description="Target identifier (email, contact_id, etc.)")
    payload: dict[str, Any] = Field(default_factory=dict, description="Action payload")
    reason: str = Field(..., description="Why this action is recommended")


class EscalationItem(BaseModel):
    """Escalation item for human review."""

    reason: str = Field(..., description="Why this requires escalation")
    severity: str = Field(..., description="e.g., 'high', 'medium', 'low'")
    context: dict[str, Any] = Field(default_factory=dict, description="Supporting context")
    suggested_actions: list[ActionRecommendation] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    """Request to the decision engine."""

    request_id: str = Field(..., description="Unique request identifier")
    objective: str = Field(..., description="SOP objective, e.g., 'lead_hygiene'")
    events: list[EventPayload] = Field(default_factory=list, description="Normalized events")
    constraints: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "request_id": "req_123",
                    "objective": "lead_hygiene",
                    "events": [
                        {
                            "source": "hubspot",
                            "occurred_at": "2025-01-06T10:00:00Z",
                            "data": {"contact_id": "abc", "status": None, "last_contacted": None},
                        }
                    ],
                    "constraints": {"stale_threshold_hours": 48},
                }
            ]
        }
    }


class DecisionResponse(BaseModel):
    """Response from the decision engine."""

    request_id: str
    state: DecisionState
    summary: str
    confidence: float = Field(..., ge=0, le=1)
    confidence_breakdown: ConfidenceBreakdown | None = None
    recommendations: list[ActionRecommendation] = Field(default_factory=list)
    escalations: list[EscalationItem] = Field(default_factory=list)
    executed_sops: list[str] = Field(default_factory=list, description="SOPs that were executed")

    @classmethod
    def from_state(cls, request_id: str, state: dict[str, Any]) -> "DecisionResponse":
        """Construct response from graph state."""
        return cls(
            request_id=request_id,
            state=DecisionState(state.get("decision_state", "CONFIDENT")),
            summary=state.get("summary", ""),
            confidence=state.get("confidence", 0.0),
            confidence_breakdown=ConfidenceBreakdown(
                data_completeness=state.get("data_completeness", 1.0),
                ambiguity=state.get("ambiguity", 0.0),
                rule_violations=state.get("rule_violations", 0.0),
            ),
            recommendations=state.get("recommendations", []),
            escalations=state.get("escalations", []),
            executed_sops=state.get("executed_sops", []),
        )
