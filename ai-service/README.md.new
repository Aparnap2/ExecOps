# AI Service

Agentic SOP automation service for SaaS founders.

## Quick Start

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv pip install pytest pytest-asyncio

# Run tests
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v

# Start service
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## Environment

```env
# .env
OPENAI_API_KEY=sk-...
AI_SERVICE_URL=http://localhost:8000
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### Decision Request
```bash
curl -X POST http://localhost:8000/decide \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_123",
    "objective": "lead_hygiene",
    "events": [{
      "source": "hubspot",
      "occurred_at": "2025-01-06T10:00:00Z",
      "data": {"contact_id": "c1", "status": null}
    }],
    "constraints": {"stale_threshold_hours": 48}
  }'
```

### List SOPs
```bash
curl http://localhost:8000/sops
```

## SOPs

| SOP | Name | Trigger | Description |
|-----|------|---------|-------------|
| SOP-001 | lead_hygiene | Daily | Ensure leads are not stale with missing status |
| SOP-010 | support_triage | Real-time | Detect urgent tickets and customer sentiment issues |
| SOP-015 | ops_hygiene | Daily | Detect missing fields and sync errors |

## Confidence Thresholds

| Score | State |
|-------|-------|
| > 0.8 | CONFIDENT |
| 0.5 - 0.8 | UNCERTAIN |
| < 0.5 | ESCALATE |

## Project Structure

```
ai-service/
├── src/
│   ├── main.py           # FastAPI app
│   ├── schemas/
│   │   └── sop.py        # Pydantic schemas
│   └── graphs/
│       └── sop_graph.py  # LangGraph SOP workflows
├── tests/
│   └── test_sop_graph.py # Unit tests
├── pyproject.toml
└── README.md
```
