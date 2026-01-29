# Reference Implementation

Python reference implementation of the LAD-A2A protocol.

## Components

| Component | Description |
|-----------|-------------|
| [Server](server.md) | Discovery server with mDNS + well-known endpoint |
| [Client](client.md) | Discovery client library |
| [Simulation](simulation.md) | Network simulation and testing guide |

## Features

- **TLS Support** - HTTPS endpoints with certificate verification
- **AgentCard Signing** - JWS-based cryptographic signing
- **Identity Verification** - TLS, domain, and signature verification
- **Structured Logging** - Configurable logging levels

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
    Examples use HTTP for local development. In production, **all endpoints MUST use TLS 1.2+**. See [PRODUCTION-CHECKLIST.md](../../PRODUCTION-CHECKLIST.md) for deployment guidance.

### Run Tests

```bash
pytest tests/ -v
```

68 tests validate spec compliance and security features.

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
├── common/
│   ├── __init__.py
│   ├── signing.py         # AgentCard signing utilities
│   └── config.py          # Configuration file support
├── tests/
│   ├── test_lad.py        # Conformance tests
│   ├── test_security.py   # Security feature tests
│   └── test_config.py     # Configuration tests
└── pyproject.toml
```

## Security Features

### TLS Configuration

```bash
# Server with TLS
python -m server.lad_server \
  --ssl-certfile /path/to/cert.pem \
  --ssl-keyfile /path/to/key.pem

# Client with TLS verification
python -m client.lad_client \
  --url https://secure-agent.example.com
```

### AgentCard Signing

```bash
# Generate signing keys
python -c "from common.signing import generate_signing_keys; generate_signing_keys('keys/')"

# Server with signing
python -m server.lad_server --signing-key keys/private.pem

# Client with signature verification
python -m client.lad_client --signing-public-key keys/public.pem --require-verified
```
