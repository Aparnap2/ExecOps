# ExecOps

Active agent automation for SaaS founders. Four vertical agents handle domain-specific workflows with human-in-the-loop approval.

## Quick Start

```bash
# AI Service
cd ai-service
uv sync
uv run pytest tests/ -v
PYTHONPATH=src .venv/bin/activate && uvicorn ai_service.main:app --host 0.0.0.0 --port 8000

# Frontend
cd fullstack
pnpm install
pnpm dev
```

## Architecture

```
Webhooks → AI Service (/process_event) → Vertical Agents
                                    ↓
                         ┌──────────┴──────────┐
                         ↓         ↓         ↓         ↓
                   Release    Customer   Runway    Team
                   Hygiene      Fire      Money     Pulse
                         ↓         ↓         ↓         ↓
                    [ActionProposal] → Inbox UI → Approve/Reject
```

## Vertical Agents

| Agent | Triggers | Actions |
|-------|----------|---------|
| **Release Hygiene** | `sentry.error`, `github.deploy` | rollback, alert_dev |
| **Customer Fire** | `intercom.ticket`, `zendesk.ticket` | senior_assign, apology_email |
| **Runway/Money** | `stripe.invoice`, `stripe.payment_failed` | card_update_email, investigate |
| **Team Pulse** | `github.commit`, `github.activity` | calendar_invite, sentiment_check |

## API

```bash
# Process event through vertical agent
curl -X POST http://localhost:8000/process_event \
  -H "Content-Type: application/json" \
  -d '{"event_type": "stripe.payment_failed", "urgency": "high"}'

# List pending proposals
curl http://localhost:8000/proposals?status=pending_approval

# Approve/Reject
curl -X POST http://localhost:8000/proposals/{id}/approve
curl -X POST http://localhost:8000/proposals/{id}/reject -d '{"reason": "..."}'
```

## Tests

- **26** vertical agent tests: `uv run pytest ai-service/tests/ -v`
- **17** Inbox UI tests: `pnpm test`
