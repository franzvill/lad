# Reference Implementation

Python reference implementation of the LAD-A2A protocol.

## Components

| Component | Description |
|-----------|-------------|
| [Server](server.md) | Discovery server with mDNS + well-known endpoint |
| [Client](client.md) | Discovery client library |
| [Simulation](simulation.md) | Docker-based network testing |

## Quick Start

### Installation

```bash
cd reference
pip install -e .
```

### Run Server

```bash
python -m server.lad_server \
  --name "Hotel Concierge" \
  --description "Your AI concierge" \
  --role "hotel-concierge" \
  --capabilities info dining reservations \
  --port 8080
```

### Run Client

```bash
# Discover via well-known endpoint
python -m client.lad_client --url http://localhost:8080

# Discover via mDNS
python -m client.lad_client
```

!!! warning "TLS Required in Production"
    Examples use HTTP for local development. In production, **all endpoints MUST use TLS 1.2+**.

### Run Tests

```bash
pytest tests/ -v
```

All 12 conformance tests validate spec compliance.

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/.well-known/lad/agents` | LAD-A2A discovery |
| `/.well-known/agent.json` | A2A AgentCard |
| `/health` | Health check |

## Project Structure

```
reference/
├── server/
│   └── lad_server.py      # Discovery server
├── client/
│   └── lad_client.py      # Discovery client
├── tests/
│   └── test_lad.py        # Conformance tests
├── simulation/
│   └── docker-compose.yml # Network simulation
└── pyproject.toml
```
