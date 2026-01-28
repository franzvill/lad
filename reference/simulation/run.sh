#!/bin/bash
# LAD-A2A Network Simulation

set -e

echo "=============================================="
echo "LAD-A2A Hotel Network Simulation"
echo "=============================================="
echo ""

cd "$(dirname "$0")"

# Clean up any previous runs
echo "[1] Cleaning up previous containers..."
docker-compose down 2>/dev/null || true

# Build images
echo ""
echo "[2] Building Docker images..."
docker-compose build

# Run simulation
echo ""
echo "[3] Starting hotel network simulation..."
echo "    - Hotel Agent: http://localhost:8080"
echo "    - Guest Device: Joining network..."
echo ""

# Run and show logs
docker-compose up --abort-on-container-exit

# Cleanup
echo ""
echo "[4] Cleaning up..."
docker-compose down

echo ""
echo "=============================================="
echo "Simulation complete!"
echo "=============================================="
