# LAD-A2A Network Simulation

This simulation demonstrates LAD-A2A discovery in a realistic network scenario using Docker.

## Scenario

```
┌─────────────────────────────────────────────────────────┐
│                  Hotel Network (172.28.0.0/16)          │
│                                                         │
│  ┌─────────────────────┐     ┌─────────────────────┐   │
│  │   Hotel Concierge   │     │    Guest Device     │   │
│  │   (hotel-agent)     │◄────│   (guest-phone)     │   │
│  │                     │     │                     │   │
│  │  - mDNS: _a2a._tcp │     │  1. Joins network   │   │
│  │  - /.well-known/    │     │  2. Discovers agent │   │
│  │    lad/agents       │     │  3. Fetches card    │   │
│  │  - /.well-known/    │     │  4. User consent    │   │
│  │    agent.json       │     │  5. Connects!       │   │
│  └─────────────────────┘     └─────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Requirements

- Docker
- Docker Compose

## Run the Simulation

```bash
# Option 1: Use the script
chmod +x run.sh
./run.sh

# Option 2: Manual docker-compose
docker-compose build
docker-compose up
```

## What Happens

1. **Hotel Agent** starts on the simulated hotel network
   - Advertises via mDNS as `Hotel Concierge._a2a._tcp.local`
   - Serves discovery endpoint at `/.well-known/lad/agents`
   - Serves A2A AgentCard at `/.well-known/agent.json`

2. **Guest Device** joins the network
   - Attempts mDNS discovery (`_a2a._tcp`)
   - Falls back to well-known endpoint
   - Fetches and verifies the AgentCard
   - Simulates user consent flow
   - Shows example interactions

## Test Endpoints Manually

While the simulation is running, you can test the endpoints:

```bash
# Discovery endpoint
curl http://localhost:8080/.well-known/lad/agents | jq

# AgentCard
curl http://localhost:8080/.well-known/agent.json | jq

# Health check
curl http://localhost:8080/health
```

## Cleanup

```bash
docker-compose down
```
