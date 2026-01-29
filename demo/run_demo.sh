#!/bin/bash

# LAD-A2A Demo Runner
# Starts both the Hotel Agent and User Agent (Aria)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════╗"
echo "║           LAD-A2A Demo Runner             ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# Check for .env file or OPENAI_API_KEY
if [ ! -f ".env" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  No .env file found and OPENAI_API_KEY not set${NC}"
    echo ""
    echo "Create a .env file with your OpenAI API key:"
    echo "  cp .env.example .env"
    echo "  # Then edit .env and add your key"
    echo ""
    exit 1
fi

if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} Loading configuration from .env"
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

echo ""
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down agents..."
    kill $HOTEL_PID 2>/dev/null || true
    kill $USER_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start Hotel Agent
echo "🏨 Starting Hotel Agent (port 8001)..."
python hotel_agent.py &
HOTEL_PID=$!
sleep 2

# Start User Agent (Aria)
echo "✨ Starting User Agent - Aria (port 8000)..."
python user_agent.py &
USER_PID=$!
sleep 2

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}✓${NC} Hotel Agent running on http://localhost:8001"
echo -e "  ${GREEN}✓${NC} User Agent running on http://localhost:8000"
echo ""
echo -e "  ${BLUE}→ Open http://localhost:8000 in your browser${NC}"
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
echo -e "${YELLOW}  ⚠️  DEMO MODE: Agents shown as UNVERIFIED${NC}"
echo -e "${YELLOW}  ⚠️  Production requires HTTPS + TLS certs${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
echo ""
echo "Press Ctrl+C to stop both agents"
echo ""

# Wait for processes
wait
