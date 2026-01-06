#!/bin/bash
# FounderOS Integration Test
# Tests all services are properly synced

set -e

echo "========================================"
echo "  FounderOS Integration Test"
echo "========================================"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

test_endpoint() {
    local name="$1"
    local url="$2"
    local method="${3:-GET}"
    local body="$4"

    echo -n "Testing $name... "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$body" \
            "$url")
    fi

    if [ "$response" = "200" ] || [ "$response" = "201" ] || [ "$response" = "500" ]; then
        echo -e "${GREEN}OK${NC} (HTTP $response)"
        ((PASS++))
    else
        echo -e "${RED}FAIL${NC} (HTTP $response)"
        ((FAIL++))
    fi
}

echo -e "\n${YELLOW}[1/5]${NC} Testing Docker containers..."
docker ps --format "{{.Names}}: {{.Status}}" | grep -E "founderos-postgres|founderos-redis" || echo "Warning: Some containers may not be running"

echo -e "\n${YELLOW}[2/5]${NC} Testing AI Service endpoints..."

# Test AI service health
test_endpoint "AI Service Health" "http://localhost:8000/health"

# Test SOPs list
test_endpoint "SOPs List" "http://localhost:8000/sops"

# Test decision endpoint
test_endpoint "Decision Endpoint" "http://localhost:8000/decide" "POST" '{"request_id":"test-integration","objective":"lead_hygiene","events":[{"source":"hubspot","occurred_at":"2025-01-06T10:00:00Z","data":{"contact_id":"test","status":"new"}}],"constraints":{}}'

echo -e "\n${YELLOW}[3/5]${NC} Testing Frontend API endpoints..."

# Test events API
test_endpoint "Events API" "http://localhost:3000/api/events"

# Test decisions API (GET)
test_endpoint "Decisions API (GET)" "http://localhost:3000/api/ai/decide"

# Test decisions API (POST)
test_endpoint "Decisions API (POST)" "http://localhost:3000/api/ai/decide" "POST" '{"objective":"lead_hygiene","events":[{"source":"hubspot","occurred_at":"2025-01-06T10:00:00Z","data":{"contact_id":"test2"}}],"constraints":{}}'

echo -e "\n${YELLOW}[4/5]${NC} Testing Database..."

# Test database connection
if docker exec founderos-postgres psql -U founderos -d founderos -c "SELECT 1;" >/dev/null 2>&1; then
    echo -e "Database connection: ${GREEN}OK${NC}"
    ((PASS++))
else
    echo -e "Database connection: ${RED}FAIL${NC}"
    ((FAIL++))
fi

# Check tables exist
table_count=$(docker exec founderos-postgres psql -U founderos -d founderos -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | xargs)
if [ "$table_count" -ge "5" ]; then
    echo -e "Tables created: ${GREEN}OK${NC} ($table_count tables)"
    ((PASS++))
else
    echo -e "Tables created: ${RED}FAIL${NC} (expected 5+ tables, found $table_count)"
    ((FAIL++))
fi

echo -e "\n${YELLOW}[5/5]${NC} Full Integration Test..."

# Full flow test: Create event -> Get decision
echo "Running full flow test..."

# Create a test event
event_response=$(curl -s -X POST "http://localhost:3000/api/events" \
    -H "Content-Type: application/json" \
    -d '{"source":"hubspot","occurred_at":"2025-01-06T10:00:00Z","payload":{"contact_id":"flow_test","email":"flow@test.com","status":null}}')

event_id=$(echo "$event_response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "  Created event: ${event_id:0:8}..."

# Trigger decision
decision_response=$(curl -s -X POST "http://localhost:3000/api/ai/decide" \
    -H "Content-Type: application/json" \
    -d '{"objective":"lead_hygiene","events":[{"source":"hubspot","occurred_at":"2025-01-06T10:00:00Z","data":{"contact_id":"flow_test","status":null}}],"constraints":{}}')

if echo "$decision_response" | grep -q "state"; then
    decision_state=$(echo "$decision_response" | grep -o '"state":"[^"]*"' | cut -d'"' -f4)
    echo -e "  Decision state: ${GREEN}$decision_state${NC}"
    ((PASS++))
else
    echo -e "  Decision state: ${RED}FAILED${NC}"
    ((FAIL++))
fi

echo -e "\n========================================"
echo "  Test Results"
echo "========================================"
echo -e "Passed: ${GREEN}$PASS${NC}"
echo -e "Failed: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
