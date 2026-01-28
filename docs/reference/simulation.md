# Network Simulation

Docker-based simulation for testing LAD-A2A in realistic network scenarios.

## Overview

The simulation creates an isolated Docker network with:

- **Hotel Agent** - A discovery server advertising hotel services
- **Guest Device** - A client that discovers and connects to the hotel agent

```
┌─────────────────────────────────────────────────────────┐
│                  Docker Network                          │
│                                                          │
│  ┌─────────────────────┐     ┌─────────────────────┐    │
│  │   Hotel Concierge   │◄────│    Guest Device     │    │
│  │                     │     │                     │    │
│  │  /.well-known/      │     │  1. Joins network   │    │
│  │    lad/agents       │     │  2. Discovers agent │    │
│  │  /.well-known/      │     │  3. Fetches card    │    │
│  │    agent.json       │     │  4. User consent    │    │
│  │                     │     │  5. Connects!       │    │
│  └─────────────────────┘     └─────────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Requirements

- Docker
- Docker Compose

## Quick Start

```bash
cd reference/simulation
./run.sh
```

## Manual Run

```bash
cd reference/simulation

# Build images
docker-compose build

# Run simulation
docker-compose up

# Cleanup
docker-compose down
```

## What Happens

1. **Hotel Agent starts** on the simulated network
    - Serves `/.well-known/lad/agents`
    - Serves `/.well-known/agent.json`

2. **Guest Device joins** the network
    - Attempts mDNS discovery
    - Falls back to well-known endpoint
    - Fetches and verifies AgentCard
    - Simulates user consent
    - Shows example interactions

## Expected Output

```
============================================================
🏨 Guest Device - Joining Hotel Network
============================================================

[1] Connected to network
[2] Starting LAD-A2A discovery...

[5] Discovery complete!
    Method: wellknown
    Agents found: 1

============================================================
📋 Available Hotel Services
============================================================

  [1] Hotel Concierge
      Description: Your AI concierge for hotel services
      Role: hotel-concierge
      Capabilities: info, dining, spa, reservations
      AgentCard: ✓ Verified

      💬 'Would you like to connect to Hotel Concierge?'
         [User selects: Connect]

      ✅ Connected! You can now ask about:
         • Info
         • Dining
         • Spa
         • Reservations

============================================================
🎉 Guest device successfully discovered hotel services!
============================================================
```

## Test Endpoints Manually

While the simulation runs, test from your host:

```bash
# Discovery endpoint
curl http://localhost:8080/.well-known/lad/agents | jq

# AgentCard
curl http://localhost:8080/.well-known/agent.json | jq

# Health check
curl http://localhost:8080/health
```

## Customization

### Modify Hotel Agent

Edit `Dockerfile.server`:

```dockerfile
CMD ["python", "-m", "server.lad_server", \
     "--name", "My Custom Agent", \
     "--capabilities", "custom1", "custom2", \
     ...]
```

### Add More Agents

Extend `docker-compose.yml`:

```yaml
services:
  hotel-agent:
    # ... existing ...

  spa-agent:
    build:
      context: ..
      dockerfile: simulation/Dockerfile.server
    environment:
      - AGENT_NAME=Spa Services
    networks:
      - hotel-network
```
