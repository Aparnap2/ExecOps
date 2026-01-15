"""Tests for Stripe Integration.

Tests for:
- Stripe webhook handling (mocked)
- Invoice parsing
- Vendor duplicate detection
- CFO agent Stripe integration
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestVendorMatcher:
    """Tests for vendor matching from descriptions."""

    def test_match_vercel(self):
        """Match Vercel from description."""
        from ai_service.integrations.stripe import VendorMatcher

        assert VendorMatcher.match("Vercel Pro subscription") == "Vercel"
        assert VendorMatcher.match("ZEIT Now Invoice") == "Vercel"

    def test_match_aws(self):
        """Match AWS from description."""
        from ai_service.integrations.stripe import VendorMatcher

        assert VendorMatcher.match("AWS December 2024 Invoice") == "AWS"
        assert VendorMatcher.match("Amazon Web Services") == "AWS"

    def test_match_openai(self):
        """Match OpenAI from description."""
        from ai_service.integrations.stripe import VendorMatcher

        assert VendorMatcher.match("OpenAI API Usage - December 2024") == "OpenAI"
        assert VendorMatcher.match("ChatGPT Plus Subscription") == "OpenAI"

    def test_match_unknown(self):
        """Handle unknown vendor."""
        from ai_service.integrations.stripe import VendorMatcher

        assert VendorMatcher.match("Random Service Invoice #12345") == "Random"
        assert VendorMatcher.match("") == "Unknown"
        assert VendorMatcher.match(None) == "Unknown"

    def test_match_case_insensitive(self):
        """Match is case insensitive."""
        from ai_service.integrations.stripe import VendorMatcher

        assert VendorMatcher.match("VERCEL PRO") == "Vercel"
        assert VendorMatcher.match("aws bill") == "AWS"


class TestInvoiceContext:
    """Tests for InvoiceContext dataclass."""

    def test_create_invoice_context(self):
        """Create InvoiceContext with required fields."""
        from ai_service.integrations.stripe import InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_123",
            customer_id="cus_abc",
            amount=10000,
            currency="usd",
            vendor="TestVendor",
        )

        assert invoice.invoice_id == "in_123"
        assert invoice.customer_id == "cus_abc"
        assert invoice.amount == 10000
        assert invoice.vendor == "TestVendor"

    def test_amount_dollars(self):
        """Convert cents to dollars."""
        from ai_service.integrations.stripe import InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_123",
            customer_id="cus_abc",
            amount=150000,  # $1500
            currency="usd",
            vendor="Test",
        )

        assert invoice.amount_dollars == 1500.0

    def test_defaults(self):
        """InvoiceContext has sensible defaults."""
        from ai_service.integrations.stripe import InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_123",
            customer_id="cus_abc",
            amount=1000,
            currency="usd",
            vendor="Test",
        )

        assert invoice.status == "pending"
        assert invoice.description == ""
        assert invoice.created_at is None


class TestStripeWebhookHandler:
    """Tests for Stripe webhook handling (without actual Stripe calls)."""

    def test_parse_invoice_event_with_mock(self):
        """Parse invoice event using mocked Stripe."""
        from ai_service.integrations.stripe import StripeWebhookHandler

        handler = StripeWebhookHandler(
            webhook_secret="whsec_test",
            api_key="sk_test_123"
        )

        # Create mock event
        mock_event = MagicMock()
        mock_event.type = "invoice.payment_succeeded"
        mock_event.data.object = {
            "id": "in_123456",
            "customer": "cus_abc",
            "amount_paid": 5000,
            "currency": "usd",
            "status": "paid",
            "description": "Vercel Pro subscription",
            "lines": {
                "data": [
                    {"description": "Vercel Pro", "amount": 5000}
                ]
            },
            "created": 1704067200,
        }

        # Mock the verify_signature to return our event
        with patch.object(handler, 'verify_signature', return_value=mock_event):
            result = handler.parse_invoice_event(b'test', 't=1,v1=sig')

        assert result is not None
        assert result.invoice_id == "in_123456"
        assert result.customer_id == "cus_abc"
        assert result.amount == 5000
        assert result.currency == "usd"
        assert result.vendor == "Vercel"
        assert result.status == "paid"

    def test_ignore_non_invoice_events(self):
        """Ignore non-invoice event types."""
        from ai_service.integrations.stripe import StripeWebhookHandler

        handler = StripeWebhookHandler(
            webhook_secret="whsec_test",
            api_key="sk_test_123"
        )

        mock_event = MagicMock()
        mock_event.type = "payment_intent.succeeded"

        with patch.object(handler, 'verify_signature', return_value=mock_event):
            result = handler.parse_invoice_event(b'test', 't=1,v1=sig')

        assert result is None

    def test_signature_verification_fails_gracefully(self):
        """Handle signature verification failure."""
        from ai_service.integrations.stripe import StripeWebhookHandler

        handler = StripeWebhookHandler(
            webhook_secret="whsec_test",
            api_key="sk_test_123"
        )

        # Mock verify_signature to return None (invalid)
        with patch.object(handler, 'verify_signature', return_value=None):
            result = handler.parse_invoice_event(b'test', 't=1,v1=sig')

        assert result is None

    def test_extract_vendor_from_description(self):
        """Extract vendor name from description."""
        from ai_service.integrations.stripe import StripeWebhookHandler

        handler = StripeWebhookHandler(webhook_secret="", api_key="")

        assert handler._extract_vendor("Vercel Pro subscription") == "Vercel"
        assert handler._extract_vendor("AWS Bill") == "AWS"
        assert handler._extract_vendor("OpenAI API") == "OpenAI"


class TestStripeClient:
    """Tests for Stripe API client."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Stripe client initializes with API key."""
        from ai_service.integrations.stripe import StripeClient

        client = StripeClient(api_key="sk_test_123")
        assert client.api_key == "sk_test_123"

    @pytest.mark.asyncio
    async def test_fetch_invoice(self):
        """Client can fetch invoice by ID."""
        from ai_service.integrations.stripe import StripeClient

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "in_123",
                "amount_paid": 5000,  # Use amount_paid like Stripe API
                "currency": "usd",
                "customer": "cus_123",
                "description": "Test Service",
                "status": "paid",
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = StripeClient(api_key="sk_test_123")
            invoice = await client.fetch_invoice("in_123")

            assert invoice.invoice_id == "in_123"
            assert invoice.amount == 5000
            assert invoice.vendor == "Test"

    @pytest.mark.asyncio
    async def test_list_customer_invoices(self):
        """Client can list customer invoices."""
        from ai_service.integrations.stripe import StripeClient

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": "in_1", "amount": 1000, "currency": "usd",
                     "customer": "cus_123", "description": "Vercel", "status": "paid"},
                    {"id": "in_2", "amount": 2000, "currency": "usd",
                     "customer": "cus_123", "description": "AWS", "status": "paid"},
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = StripeClient(api_key="sk_test_123")
            invoices = await client.list_customer_invoices("cus_123")

            assert len(invoices) == 2
            assert invoices[0].invoice_id == "in_1"
            assert invoices[1].invoice_id == "in_2"

    @pytest.mark.asyncio
    async def test_check_duplicate_vendor(self):
        """Check for duplicate vendor spending."""
        from ai_service.integrations.stripe import StripeClient, InvoiceContext

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": "in_1", "amount": 1000, "currency": "usd",
                     "customer": "cus_123", "description": "Vercel", "status": "paid"},
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = StripeClient(api_key="sk_test_123")

            # Check for duplicate Vercel
            invoice = InvoiceContext(
                invoice_id="in_new",
                customer_id="cus_123",
                amount=1000,
                currency="usd",
                vendor="Vercel",
            )

            is_duplicate = await client.check_duplicate_vendor(invoice)
            assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_new_vendor_not_duplicate(self):
        """New vendor is not flagged as duplicate."""
        from ai_service.integrations.stripe import StripeClient, InvoiceContext

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": "in_1", "amount": 1000, "currency": "usd",
                     "customer": "cus_123", "description": "Vercel", "status": "paid"},
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = StripeClient(api_key="sk_test_123")

            # Check for new vendor (not in existing invoices)
            invoice = InvoiceContext(
                invoice_id="in_new",
                customer_id="cus_123",
                amount=1000,
                currency="usd",
                vendor="NewService",
            )

            is_duplicate = await client.check_duplicate_vendor(invoice)
            assert is_duplicate is False


class TestCFOStripeIntegration:
    """Tests for CFO agent with Stripe integration."""

    def test_cfo_analyzes_invoice(self):
        """CFO agent can analyze Stripe invoice."""
        from ai_service.integrations.stripe import cfo_analyze_invoice_node, InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_123",
            customer_id="cus_abc",
            amount=15000,  # $150
            currency="usd",
            vendor="Vercel",
        )

        state = {
            "invoice_context": invoice,
            "monthly_budget": 500.0,
            "known_vendors": ["Vercel", "AWS", "OpenAI"],
        }

        result = cfo_analyze_invoice_node(state)

        assert "budget_impact" in result
        assert result["budget_impact"]["vendor"] == "Vercel"
        assert result["decision"] in ["approve", "warn", "block"]

    def test_cfo_blocks_duplicate_spend(self):
        """CFO agent blocks duplicate vendor spend."""
        from ai_service.integrations.stripe import cfo_analyze_invoice_node, InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_new",
            customer_id="cus_123",
            amount=5000,
            currency="usd",
            vendor="Vercel",
        )

        state = {
            "invoice_context": invoice,
            "monthly_budget": 500.0,
            "known_vendors": ["Vercel", "AWS"],
            "duplicate_vendors": ["Vercel"],
        }

        result = cfo_analyze_invoice_node(state)

        assert result["decision"] == "block"
        assert "duplicate" in result["reason"].lower()

    def test_cfo_approves_under_budget(self):
        """CFO agent approves invoice under budget."""
        from ai_service.integrations.stripe import cfo_analyze_invoice_node, InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_test",
            customer_id="cus_123",
            amount=1000,  # $10
            currency="usd",
            vendor="NewService",
        )

        state = {
            "invoice_context": invoice,
            "monthly_budget": 500.0,
            "known_vendors": [],
            "duplicate_vendors": [],
        }

        result = cfo_analyze_invoice_node(state)

        assert result["decision"] == "approve"

    def test_cfo_warns_near_budget(self):
        """CFO agent warns when near budget limit."""
        from ai_service.integrations.stripe import cfo_analyze_invoice_node, InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_large",
            customer_id="cus_123",
            amount=400000,  # $4000
            currency="usd",
            vendor="AWS",
        )

        state = {
            "invoice_context": invoice,
            "monthly_budget": 500.0,
            "known_vendors": ["AWS"],
            "duplicate_vendors": [],
        }

        result = cfo_analyze_invoice_node(state)

        assert result["decision"] in ["warn", "block"]
        assert result["budget_impact"]["exceeds_budget"] is True

    def test_cfo_handles_missing_context(self):
        """CFO handles missing invoice context gracefully."""
        from ai_service.integrations.stripe import cfo_analyze_invoice_node

        state = {
            "monthly_budget": 500.0,
        }

        result = cfo_analyze_invoice_node(state)

        assert result["decision"] == "error"
        assert "No invoice context" in result["reason"]


class TestConvenienceFunctions:
    """Tests for module convenience functions."""

    def test_create_webhook_handler(self):
        """Create Stripe webhook handler."""
        from ai_service.integrations.stripe import create_stripe_webhook_handler

        handler = create_stripe_webhook_handler(
            webhook_secret="whsec_test",
            api_key="sk_test_123"
        )

        assert handler.webhook_secret == "whsec_test"
        assert handler.api_key == "sk_test_123"

    def test_create_stripe_client(self):
        """Create Stripe API client."""
        from ai_service.integrations.stripe import create_stripe_client

        client = create_stripe_client(api_key="sk_test_123")

        assert client.api_key == "sk_test_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
