# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LAD-A2A (Local Agent Discovery for A2A) is an open protocol specification and reference implementation for discovering A2A-capable AI agents on local networks. It enables AI agents to find and connect to service agents when joining networks (hotels, offices, hospitals, etc.).

**Key concepts:**
- Discovery layer between physical networks and A2A protocol (MCP handles tools, A2A handles communication, LAD-A2A handles discovery)
- Zero-configuration discovery via mDNS/DNS-SD (`_a2a._tcp.local`), well-known endpoints (`/.well-known/lad/agents`), and DHCP
- Security model assumes local networks are hostile by default

## Common Commands

### Reference Implementation
```bash
cd reference
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (35 tests for conformance and security)
pytest tests/ -v

# Run single test
pytest tests/test_lad.py::TestDiscoveryEndpoint::test_discovery_required_fields -v

# Start server (development only - no TLS)
python -m server.lad_server --name "My Agent" --port 8080

# Start server with TLS (production)
python -m server.lad_server --name "My Agent" --port 443 \
  --ssl-certfile /path/to/cert.pem --ssl-keyfile /path/to/key.pem

# Start server with AgentCard signing
python -m server.lad_server --name "My Agent" --signing-key keys/private.pem

# Run client
python -m client.lad_client --url http://localhost:8080

# Run client with verification
python -m client.lad_client --url https://agent.example.com \
  --signing-public-key keys/public.pem --require-verified

# Run client with interactive consent
python -m client.lad_client --url http://localhost:8080 --with-consent

# Generate signing keys
python -c "from common.signing import generate_signing_keys; generate_signing_keys('keys/')"
```

### Demo Application
```bash
cd demo
cp .env.example .env  # Add OPENAI_API_KEY
./run_demo.sh         # Opens http://localhost:8000
```

### Documentation
```bash
pip install mkdocs-material
mkdocs serve          # Local preview
mkdocs build          # Build static site
```

## Architecture

### Reference Implementation (`reference/`)

**Server (`server/lad_server.py`):**
- `LADServer` class handles mDNS advertisement and well-known endpoints
- Advertises via `_a2a._tcp.local` with TXT records (path, v, org)
- FastAPI endpoints: `/.well-known/lad/agents` (discovery), `/.well-known/agent.json` (A2A AgentCard)
- TLS support via `--ssl-certfile` and `--ssl-keyfile`
- AgentCard signing via `--signing-key` (returns JWS when client requests `application/jose`)

**Client (`client/lad_client.py`):**
- `LADClient` implements layered discovery: mDNS → well-known fallback → fetch AgentCards
- `MDNSListener` handles `_a2a._tcp.local` service discovery with proper update/remove handling
- Returns `DiscoveryResult` with agents list, verification status, and errors
- `DiscoveredAgent` includes `verified`, `verification_method`, `verification_error` fields
- Consent flow via `discover_with_consent()` with callback interface
- TLS verification enabled by default, signature verification optional

**Common (`common/signing.py`):**
- `SigningConfig` for JWS signing configuration
- `generate_signing_keys()` - Generate ECDSA P-256 key pairs
- `sign_agent_card()` - Sign AgentCards as JWS tokens
- `verify_agent_card()` - Verify JWS signatures

### Demo (`demo/`)

Two-agent system demonstrating LAD-A2A + A2A integration:

1. **Hotel Agent** (port 8001): LAD-A2A server + A2A JSON-RPC server, GPT-4o backend
2. **User Agent "Aria"** (port 8000): LAD-A2A client + A2A client + web UI, routes queries to discovered agents

A2A transport: JSON-RPC 2.0 over HTTP with SendMessage/GetTask/CancelTask methods.

### Protocol Specification (`spec/spec.md`)

Version 0.1.0-draft defining:
- Discovery mechanisms (mDNS, well-known, DHCP, QR/NFC)
- Trust bootstrap and security requirements (TLS 1.2+ mandatory, signed AgentCards, DIDs)
- Response schemas and field requirements

## Key Dependencies

- `zeroconf` - mDNS/DNS-SD implementation
- `fastapi` + `uvicorn` - Web framework and ASGI server
- `httpx` - Async HTTP client
- `pydantic` - Data validation
- `pyjwt` - JWT/JWS token handling for AgentCard signing
- `cryptography` - Cryptographic primitives for signing
- `openai` - Demo only (GPT-4o)

Python 3.10+ required.

## Security Notes

- TLS is mandatory for production (use `--ssl-certfile` and `--ssl-keyfile`)
- AgentCards must be cryptographically signed (use `--signing-key`)
- User consent required before agent communication (use `--with-consent` or `discover_with_consent()`)
- Verification methods: TLS, domain matching, JWS signature
- See PRODUCTION-CHECKLIST.md for deployment guidance
- See SECURITY.md for vulnerability reporting
