# ExecOps AI Service

AI-powered internal operating system for SaaS founders that connects work (Linear/GitHub), money (Stripe), and rules (SOPs) to automate operations and enforce compliance.

## Sentinel: PR Compliance Agent

The first vertical implemented is **Sentinel** - an AI agent that enforces deployment compliance by analyzing PRs against SOP policies.

### Features

- **Linear-GitHub Integration**: Links PRs to Linear issues automatically
- **SOP Compliance**: Validates PRs against deployment policies
- **Risk Scoring**: Calculates risk based on graph context (Neo4j)
- **LLM-Powered Analysis**: Uses Qwen 2.5 Coder (Ollama) for intelligent decisions
- **Slack Notifications**: Alerts humans for block/warn decisions
- **Human-in-the-Loop**: Uses LangGraph interrupts for approval workflow

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   GitHub    │────▶│  Sentinel   │────▶│    Slack    │
│   Webhook   │     │   LangGraph │     │  Approval   │
└─────────────┘     └─────────────┘     └─────────────┘
                            │
                    ┌───────▼───────┐
                    │     Neo4j     │
                    │  Graph Brain  │
                    └───────────────┘
                            │
                    ┌───────▼───────┐
                    │    Ollama     │
                    │ Qwen 2.5 Coder│
                    └───────────────┘
```

### Compliance Rules

| Rule | Condition | Decision |
|------|-----------|----------|
| Linear Issue | No issue linked | BLOCK |
| Issue State | Not IN_PROGRESS or REVIEW | WARN |
| Needs Spec | Issue has "Needs Spec" label | WARN |
| Valid PR | All checks pass | PASS (auto-approve) |

### Project Structure

```
ai-service/
├── src/ai_service/
│   ├── agents/sentinel/     # Sentinel LangGraph workflow
│   │   ├── state.py         # SentinelState TypedDict
│   │   ├── nodes.py         # extract, compliance, execute nodes
│   │   └── graph.py         # StateGraph compilation
│   ├── integrations/        # Third-party clients
│   │   ├── github.py        # GitHub API
│   │   ├── slack.py         # Slack webhooks
│   │   └── mock_clients.py  # Test mocks
│   ├── memory/
│   │   └── graph.py         # Neo4j GraphService
│   ├── llm/
│   │   └── service.py       # Ollama LLM integration
│   ├── sop/                 # SOP loading & validation
│   │   ├── loader.py
│   │   └── validator.py
│   └── webhooks/
│       └── github.py        # PR event handler
├── tests/
│   └── test_sentinel.py     # 32 integration tests
└── pyproject.toml
```

### Getting Started

#### Prerequisites

- **Neo4j**: `bolt://localhost:7687` (neo4j/founderos_secret)
- **PostgreSQL**: For LangGraph checkpointer
- **Redis**: For Celery task queue
- **Ollama**: With `qwen2.5-coder:3b` model

#### Run with Docker

```bash
# Start infrastructure
docker run -d --name neo4j -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/founderos_secret neo4j:5.14
docker run -d --name ollama -p 11434:11434 ollama/ollama
docker exec ollama ollama pull qwen2.5-coder:3b

# Run AI service
cd /home/aparna/Desktop/founder_os/ai-service
source .venv/bin/activate
uvicorn ai_service.main:app --reload
```

#### Running Tests

```bash
cd /home/aparna/Desktop/founder_os/ai-service
source .venv/bin/activate
pytest tests/test_sentinel.py -v

# Results: 32 passed
```

#### Test Coverage

- **Mock Clients**: GitHub, Slack, Linear (14 tests)
- **Sentinel Nodes**: extract_linear_context, check_compliance, execute (9 tests)
- **LLM Integration**: Ollama health, PR analysis (4 tests)
- **E2E Workflows**: Full PR review workflow (2 tests)
- **GraphService**: Neo4j operations (3 tests)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhooks/github` | POST | Handle PR events |
| `/health` | GET | Service health check |
| `/sentinel/status/{event_id}` | GET | Get workflow status |

### Environment Variables

```bash
GITHUB_TOKEN=ghp_xxx
GITHUB_REPO_OWNER=owner
GITHUB_REPO_NAME=repo
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=founderos_secret
OLLAMA_BASE_URL=http://localhost:11434
USE_LLM_COMPLIANCE=true
```

### License

MIT
