# ExecOps AI Service

Active agent automation for SaaS founders. Four vertical agents handle domain-specific workflows with human-in-the-loop approval.

## Quick Start

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv pip install pytest pytest-asyncio

# Run tests
PYTHONPATH=src uv run pytest tests/ -v

# Start service
PYTHONPATH=src .venv/bin/activate && uvicorn ai_service.main:app --host 0.0.0.0 --port 8000
```

## Environment

```env
# .env
OPENAI_API_KEY=sk-...
AI_SERVICE_URL=http://localhost:8000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### Process Event (Main ExecOps Endpoint)
```bash
curl -X POST http://localhost:8000/process_event \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "stripe.payment_failed",
    "event_context": {
      "amount": 5000,
      "customer_tier": "enterprise",
      "vendor": "Acme Corp"
    },
    "urgency": "high"
  }'
```

### List Action Proposals
```bash
curl http://localhost:8000/proposals?status=pending_approval
```

### Approve/Reject Proposal
```bash
curl -X POST http://localhost:8000/proposals/{id}/approve
curl -X POST http://localhost:8000/proposals/{id}/reject -d '{"reason": "..."}'
```

## Vertical Agents

| Vertical | Trigger Events | Actions |
|----------|----------------|---------|
| **Release Hygiene** | `sentry.error`, `github.deploy` | rollback, alert_dev |
| **Customer Fire** | `intercom.ticket`, `zendesk.ticket` | senior_assign, apology_email |
| **Runway/Money** | `stripe.invoice`, `stripe.payment_failed` | card_update_email, investigate |
| **Team Pulse** | `github.commit`, `github.activity` | calendar_invite, sentiment_check |

## Architecture

```
Webhooks → /process_event → Vertical Router → LangGraph StateGraph
                                              ↓
                              ┌────────────────┼────────────────┐
                              ↓                ↓                ↓
                       gather_context   draft_action   human_approval
                              ↓                ↓                ↓
                         [analyzed]      [drafted]       [pending_approval]
```

## Test Results

```
26 passed in 0.13s - Vertical Agent Integration Tests
```

## Project Structure

```
ai-service/
├── src/
│   ├── main.py                    # FastAPI app + ExecOps endpoints
│   ├── schemas/
│   │   └── sop.py                 # Legacy schemas (deprecated)
│   └── graphs/
│       ├── vertical_agents.py     # Router + shared workflows
│       ├── release_hygiene.py     # Release agent
│       ├── customer_fire.py       # VIP customer agent
│       ├── runway_money.py        # Financial agent
│       └── team_pulse.py          # Team activity agent
├── tests/
│   └── integration/
│       └── test_vertical_agents.py # 26 TDD tests
├── pyproject.toml
└── README.md
```

## Deprecation Notice

The following endpoints are deprecated and will be removed in v1.0:

- `POST /decide` - Use `/process_event` instead
- `GET /sops` - SOPs replaced by vertical agents
