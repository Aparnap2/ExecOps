#!/bin/bash
# Quick test script to verify the setup

echo "=== FounderOS AI Service - Quick Test ==="

# Test 1: Check Docker containers
echo -e "\n[1] Docker containers:"
docker ps --format "  {{.Names}}: {{.Status}}"

# Test 2: Check Python service imports
echo -e "\n[2] Python service imports:"
cd /home/aparna/Desktop/founder_os/ai-service
PYTHONPATH=src .venv/bin/python -c "
from ai_service.schemas.sop import DecisionRequest, DecisionState
from ai_service.graphs.sop_graph import create_sop_graph
print('  - Schemas: OK')
print('  - Graph factory: OK')
print('  - All imports successful')
"

# Test 3: Run a quick graph test
echo -e "\n[3] Quick graph test:"
PYTHONPATH=src .venv/bin/python -c "
from ai_service.schemas.sop import DecisionRequest, EventPayload, EventSource
from ai_service.graphs.sop_graph import create_sop_graph
from datetime import datetime

# Create test events
events = [
    EventPayload(
        source=EventSource.HUBSPOT,
        occurred_at=datetime.utcnow(),
        data={'contact_id': 'c1', 'status': None}
    )
]

req = DecisionRequest(
    request_id='test_123',
    objective='lead_hygiene',
    events=events,
    constraints={'stale_threshold_hours': 48}
)

graph = create_sop_graph('lead_hygiene')
result = graph.compile().invoke({
    'request_id': req.request_id,
    'objective': req.objective,
    'events': req.events,
    'constraints': req.constraints,
})

print(f\"  - Decision: {result.get('decision_state')}\")
print(f\"  - Summary: {result.get('summary')}\")
print('  - Graph execution: OK')
"

# Test 4: Run unit tests
echo -e "\n[4] Unit tests:"
PYTHONPATH=src .venv/bin/python -m pytest tests/test_sop_graph.py -q --no-header 2>&1 | tail -3

echo -e "\n=== Setup Complete ==="
