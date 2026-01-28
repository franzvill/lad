# LAD-A2A Reference Implementation

Reference implementation of the LAD-A2A (Local Agent Discovery for A2A) protocol.

## Scope

This reference implementation covers **LAD-A2A discovery only**:
- mDNS/DNS-SD advertisement (`_a2a._tcp`)
- Well-known discovery endpoint (`/.well-known/lad/agents`)
- A2A AgentCard serving (`/.well-known/agent.json`)

**Not included:** A2A JSON-RPC communication (SendMessage, GetTask, etc.). For a full working demo with A2A communication, see the [interactive demo](../demo/).

## Components

- **Server** (`server/lad_server.py`): Discovery server with mDNS + well-known endpoint
- **Client** (`client/lad_client.py`): Discovery client library
- **Tests** (`tests/test_lad.py`): Conformance test suite

## Quick Start

### Install

```bash
cd reference
pip install -e ".[dev]"
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

The server will:
- Advertise via mDNS as `Hotel Concierge._a2a._tcp.local`
- Serve `/.well-known/lad/agents` discovery endpoint
- Serve `/.well-known/agent.json` A2A AgentCard

### Run Client

```bash
# Discover via mDNS (default)
python -m client.lad_client

# Discover via well-known endpoint
python -m client.lad_client --url http://localhost:8080 --no-mdns
```

### Run Tests

```bash
pytest tests/ -v
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/.well-known/lad/agents` | LAD-A2A discovery endpoint |
| `/.well-known/agent.json` | A2A AgentCard |
| `/health` | Health check |

## mDNS Advertisement

The server advertises via DNS-SD:
- Service type: `_a2a._tcp`
- TXT records: `path`, `v`, `org`

## Example Discovery Response

```json
{
  "version": "1.0",
  "network": {
    "ssid": "Hotel-Guest",
    "realm": "hotel.com"
  },
  "agents": [
    {
      "name": "Hotel Concierge",
      "description": "Your AI concierge",
      "role": "hotel-concierge",
      "agent_card_url": "http://192.168.1.100:8080/.well-known/agent.json",
      "capabilities_preview": ["info", "dining", "reservations"]
    }
  ]
}
```

## Project Structure

```
reference/
├── server/
│   └── lad_server.py      # LAD-A2A server implementation
├── client/
│   └── lad_client.py      # LAD-A2A client library
├── tests/
│   └── test_lad.py        # Conformance tests (13 tests)
└── pyproject.toml         # Package configuration
```

For a full working demo with A2A communication, see the [interactive demo](../demo/).
