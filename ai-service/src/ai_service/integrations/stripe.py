"""Stripe integration for GitHub Sentinel CFO Agent.

This module provides:
- Stripe webhook handling
- Invoice parsing and vendor detection
- Duplicate vendor spend detection
- CFO invoice analysis
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Try to import stripe, handle if not installed
try:
    import stripe
    from stripe.error import SignatureVerificationError, StripeError
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    SignatureVerificationError = Exception
    StripeError = Exception


@dataclass
class InvoiceContext:
    """Stripe invoice context for CFO analysis."""

    invoice_id: str
    customer_id: str
    amount: int  # Amount in cents
    currency: str
    vendor: str
    status: str = "pending"
    description: str = ""
    created_at: datetime | None = None
    line_items: list[dict] | None = None

    @property
    def amount_dollars(self) -> float:
        """Convert cents to dollars."""
        return self.amount / 100.0


class VendorMatcher:
    """Match vendor names from invoice descriptions."""

    # Known vendor patterns
    VENDOR_PATTERNS = {
        "Vercel": [r"vercel", r"zeit"],
        "AWS": [r"aws", r"amazon", r"amazon web"],
        "OpenAI": [r"openai", r"chatgpt"],
        "Stripe": [r"stripe"],
        "GitHub": [r"github"],
        "DigitalOcean": [r"digitalocean", r"digital ocean"],
        "Cloudflare": [r"cloudflare"],
        "Supabase": [r"supabase"],
        "MongoDB": [r"mongodb", r"mongo db"],
        "PostgreSQL": [r"postgresql", r"postgres"],
        "Redis": [r"redis"],
        "SendGrid": [r"sendgrid"],
        "Twilio": [r"twilio"],
        "Datadog": [r"datadog"],
        "New Relic": [r"new relic", r"newrelic"],
        "PagerDuty": [r"pagerduty", r"pager duty"],
        "Slack": [r"slack"],
        "Notion": [r"notion"],
        "Figma": [r"figma"],
        "Zoom": [r"zoom"],
        "Airtable": [r"airtable"],
        "Webflow": [r"webflow"],
        "Contentful": [r"contentful"],
        "Algolia": [r"algolia"],
        "Sentry": [r"sentry"],
        "Rollbar": [r"rollbar"],
    }

    @classmethod
    def match(cls, description: str) -> str:
        """Match vendor from description.

        Args:
            description: Invoice description

        Returns:
            Matched vendor name or "Unknown"
        """
        if not description:
            return "Unknown"

        description_lower = description.lower()

        for vendor, patterns in cls.VENDOR_PATTERNS.items():
            for pattern in patterns:
                if pattern in description_lower:
                    return vendor

        # Try to extract from common patterns
        # e.g., "Service - December 2024" -> "Service"
        import re
        match = re.match(r"^([A-Za-z]+)", description)
        if match:
            return match.group(1).title()

        return "Unknown"


class StripeWebhookHandler:
    """Handle Stripe webhook events."""

    def __init__(
        self,
        webhook_secret: str,
        api_key: str,
    ) -> None:
        """Initialize webhook handler.

        Args:
            webhook_secret: Stripe webhook secret (whsec_...)
            api_key: Stripe API key (sk_test_...)
        """
        self.webhook_secret = webhook_secret
        self.api_key = api_key

        if STRIPE_AVAILABLE:
            stripe.api_key = api_key
            self._stripe = stripe
        else:
            self._stripe = None

    def verify_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> Any | None:
        """Verify Stripe webhook signature.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header

        Returns:
            Stripe event or None if invalid
        """
        if not STRIPE_AVAILABLE or not self._stripe:
            logger.warning("Stripe library not available, skipping verification")
            return MagicMock()

        try:
            event = self._stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            return event
        except SignatureVerificationError as e:
            logger.error(f"Invalid Stripe signature: {e}")
            return None

    def parse_invoice_event(self, payload: bytes, signature: str) -> InvoiceContext | None:
        """Parse Stripe invoice event.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header

        Returns:
            InvoiceContext or None if not an invoice event
        """
        event = self.verify_signature(payload, signature)
        if event is None:
            return None

        # Only handle invoice events
        if event.type not in [
            "invoice.payment_succeeded",
            "invoice.created",
            "invoice.updated",
            "invoice.finalized",
        ]:
            logger.debug(f"Ignoring non-invoice event: {event.type}")
            return None

        invoice_data = event.data.object

        # Extract vendor from description
        description = invoice_data.get("description", "")
        vendor = VendorMatcher.match(description)

        # Handle line items if present
        line_items = []
        if "lines" in invoice_data and "data" in invoice_data["lines"]:
            for line in invoice_data["lines"]["data"]:
                line_items.append({
                    "description": line.get("description", ""),
                    "amount": line.get("amount", 0),
                })
                # Update vendor from line items if not found in main description
                if vendor == "Unknown":
                    vendor = VendorMatcher.match(line.get("description", ""))

        created_at = None
        if "created" in invoice_data:
            created_at = datetime.fromtimestamp(invoice_data["created"])

        return InvoiceContext(
            invoice_id=invoice_data.get("id", ""),
            customer_id=invoice_data.get("customer", ""),
            amount=invoice_data.get("amount_paid", invoice_data.get("amount_due", 0)),
            currency=invoice_data.get("currency", "usd"),
            vendor=vendor,
            status=invoice_data.get("status", "unknown"),
            description=description,
            created_at=created_at,
            line_items=line_items,
        )

    def _extract_vendor(self, description: str) -> str:
        """Extract vendor name from description.

        Args:
            description: Invoice description

        Returns:
            Vendor name
        """
        return VendorMatcher.match(description)


class StripeClient:
    """Async Stripe API client for CFO operations."""

    BASE_URL = "https://api.stripe.com/v1"

    def __init__(self, api_key: str) -> None:
        """Initialize Stripe client.

        Args:
            api_key: Stripe API key
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
        return self._client

    async def fetch_invoice(self, invoice_id: str) -> InvoiceContext:
        """Fetch invoice by ID.

        Args:
            invoice_id: Stripe invoice ID

        Returns:
            InvoiceContext
        """
        client = await self._get_client()
        response = await client.get(f"/invoices/{invoice_id}")
        response.raise_for_status()

        data = response.json()

        return InvoiceContext(
            invoice_id=data["id"],
            customer_id=data["customer"],
            amount=data.get("amount_paid", data.get("amount_due", 0)),
            currency=data.get("currency", "usd"),
            vendor=VendorMatcher.match(data.get("description", "")),
            status=data.get("status", "unknown"),
            description=data.get("description", ""),
        )

    async def list_customer_invoices(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> list[InvoiceContext]:
        """List invoices for a customer.

        Args:
            customer_id: Stripe customer ID
            limit: Maximum number of invoices to return

        Returns:
            List of InvoiceContext
        """
        client = await self._get_client()
        response = await client.get(
            "/invoices",
            params={"customer": customer_id, "limit": limit},
        )
        response.raise_for_status()

        invoices = []
        for item in response.json().get("data", []):
            invoices.append(InvoiceContext(
                invoice_id=item["id"],
                customer_id=item["customer"],
                amount=item.get("amount_paid", item.get("amount_due", 0)),
                currency=item.get("currency", "usd"),
                vendor=VendorMatcher.match(item.get("description", "")),
                status=item.get("status", "unknown"),
                description=item.get("description", ""),
            ))

        return invoices

    async def check_duplicate_vendor(
        self,
        invoice: InvoiceContext,
    ) -> bool:
        """Check if vendor already has spending.

        Args:
            invoice: InvoiceContext to check

        Returns:
            True if vendor already has invoices
        """
        # Get customer's recent invoices
        invoices = await self.list_customer_invoices(
            invoice.customer_id,
            limit=20,
        )

        # Check if any invoice has the same vendor
        for inv in invoices:
            if inv.vendor == invoice.vendor and inv.invoice_id != invoice.invoice_id:
                return True

        return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# CFO Agent Integration

# Budget constants
DEFAULT_MONTHLY_BUDGET = 500.0  # $500 default
WARN_THRESHOLD = 0.8  # Warn at 80% of budget
BLOCK_THRESHOLD = 1.0  # Block at 100% of budget


def cfo_analyze_invoice_node(state: dict) -> dict:
    """Analyze Stripe invoice for budget impact.

    Args:
        state: Agent state with invoice_context

    Returns:
        Updated state with budget analysis
    """
    from ai_service.agent.nodes import enforce_budget_policy

    invoice = state.get("invoice_context")
    if not invoice:
        logger.warning("No invoice context in state")
        return {
            **state,
            "decision": "error",
            "reason": "No invoice context provided",
        }

    monthly_budget = state.get("monthly_budget", DEFAULT_MONTHLY_BUDGET)
    known_vendors = state.get("known_vendors", [])
    duplicate_vendors = state.get("duplicate_vendors", [])

    # Check for duplicate vendor
    is_duplicate = invoice.vendor in duplicate_vendors or (
        invoice.vendor in known_vendors and
        invoice.vendor in duplicate_vendors
    )

    # Calculate budget impact
    invoice_amount = invoice.amount_dollars
    total_monthly = invoice_amount

    # Estimate monthly spend (simplified: assume this is monthly)
    overage_percentage = max(0, (total_monthly / monthly_budget) - 1) * 100
    exceeds_budget = total_monthly > monthly_budget

    # Determine decision
    if is_duplicate:
        decision = "block"
        reason = f"Duplicate vendor '{invoice.vendor}' - already have spending with this vendor"
    elif exceeds_budget and total_monthly > monthly_budget * 2:
        decision = "block"
        reason = f"Invoice of ${invoice_amount:.2f} exceeds monthly budget of ${monthly_budget:.2f}"
    elif exceeds_budget:
        decision = "warn"
        reason = f"Invoice of ${invoice_amount:.2f} exceeds monthly budget of ${monthly_budget:.2f}"
    else:
        decision = "approve"
        reason = f"Invoice of ${invoice_amount:.2f} is within budget"

    budget_impact = {
        "vendor": invoice.vendor,
        "invoice_id": invoice.invoice_id,
        "estimated_monthly_cost": total_monthly,
        "monthly_budget": monthly_budget,
        "exceeds_budget": exceeds_budget,
        "overage_percentage": overage_percentage,
        "is_duplicate_vendor": is_duplicate,
        "currency": invoice.currency.upper(),
    }

    # Apply budget policy for final decision
    policy = {
        "monthly_budget": monthly_budget,
        "warn_threshold": WARN_THRESHOLD,
        "block_threshold": BLOCK_THRESHOLD,
    }

    policy_result = enforce_budget_policy(total_monthly, policy)

    logger.info(
        f"CFO Invoice Analysis: {invoice.vendor} - ${invoice_amount:.2f}, "
        f"decision: {decision}, budget: ${monthly_budget:.2f}"
    )

    return {
        **state,
        "budget_impact": budget_impact,
        "decision": decision,
        "confidence": 0.95 if decision == "approve" else 0.85,
        "reason": reason,
        "policy_decision": policy_result["decision"],
    }


def create_stripe_webhook_handler(webhook_secret: str, api_key: str) -> StripeWebhookHandler:
    """Create Stripe webhook handler.

    Args:
        webhook_secret: Stripe webhook secret
        api_key: Stripe API key

    Returns:
        Configured StripeWebhookHandler
    """
    return StripeWebhookHandler(webhook_secret=webhook_secret, api_key=api_key)


def create_stripe_client(api_key: str) -> StripeClient:
    """Create Stripe API client.

    Args:
        api_key: Stripe API key

    Returns:
        Configured StripeClient
    """
    return StripeClient(api_key=api_key)
