#!/bin/bash
# FounderOS Startup Script
# Starts all services in the correct order

set -e

echo "========================================"
echo "  FounderOS - Starting All Services"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Docker is running
echo -e "\n${YELLOW}[1/4]${NC} Checking Docker..."
if ! docker ps >/dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi
echo -e "${GREEN}Docker is running${NC}"

# Start Docker containers if not running
echo -e "\n${YELLOW}[2/4]${NC} Starting Docker containers..."
if ! docker ps --format '{{.Names}}' | grep -q "founderos-postgres"; then
    echo "Starting PostgreSQL and Redis..."
    docker-compose up -d
    echo "Waiting for database to be ready..."
    sleep 3
else
    echo -e "${GREEN}Containers already running${NC}"
fi

# Start AI Service
echo -e "\n${YELLOW}[3/4]${NC} Starting AI Service (Python/FastAPI)..."
cd /home/aparna/Desktop/founder_os/ai-service

# Check if already running
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "${GREEN}AI Service already running on port 8000${NC}"
else
    echo "Starting AI Service..."
    export PYTHONPATH=/home/aparna/Desktop/founder_os/ai-service/src
    nohup .venv/bin/uvicorn ai_service.main:app --host 0.0.0.0 --port 8000 > /tmp/ai-service.log 2>&1 &
    AI_PID=$!
    echo "AI Service PID: $AI_PID"

    # Wait for it to be ready
    echo "Waiting for AI Service..."
    for i in {1..10}; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            echo -e "${GREEN}AI Service ready!${NC}"
            break
        fi
        sleep 1
    done
fi

# Start Frontend
echo -e "\n${YELLOW}[4/4]${NC} Starting Frontend (Next.js)..."
cd /home/aparna/Desktop/founder_os/fullstack

# Check if already running
if curl -s http://localhost:3000 >/dev/null 2>&1; then
    echo -e "${GREEN}Frontend already running on port 3000${NC}"
else
    echo "Starting Frontend..."
    nohup pnpm dev > /tmp/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "Frontend PID: $FRONTEND_PID"
fi

echo -e "\n========================================"
echo -e "${GREEN}  All services started!${NC}"
echo "========================================"
echo ""
echo "Services:"
echo "  - Frontend:  http://localhost:3000"
echo "  - AI API:    http://localhost:8000"
echo "  - Database:  localhost:5432 (PostgreSQL)"
echo "  - Redis:     localhost:6379"
echo ""
echo "Health Checks:"
echo "  - Frontend:  curl http://localhost:3000"
echo "  - AI API:    curl http://localhost:8000/health"
echo ""
echo "Test Endpoints:"
echo "  - List SOPs: curl http://localhost:8000/sops"
echo "  - Decisions: curl http://localhost:3000/api/ai/decide"
echo ""
echo "Logs:"
echo "  - AI Service: tail -f /tmp/ai-service.log"
echo "  - Frontend:   tail -f /tmp/frontend.log"
echo ""
