# LAD-A2A Interactive Demo

A fully working demonstration of the LAD-A2A discovery protocol with two AI agents communicating via Google's A2A (Agent-to-Agent) protocol.

## What This Demo Shows

1. **Real mDNS Discovery** - The user agent scans for `_a2a._tcp.local` services
2. **LAD-A2A Protocol** - Discovery via `/.well-known/lad/agents` endpoint
3. **A2A Protocol** - JSON-RPC 2.0 communication between agents
4. **LLM-Based Routing** - AI decides when to query the remote agent

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Device                           │
│  ┌─────────────┐      WebSocket      ┌───────────────────────┐  │
│  │  Browser UI │◄───────────────────►│   User Agent (Aria)   │  │
│  │ index.html  │                     │   - OpenAI GPT-4o     │  │
│  └─────────────┘                     │   - LAD-A2A Client    │  │
│                                      │   - A2A Client        │  │
│                                      └───────────┬───────────┘  │
└──────────────────────────────────────────────────┼──────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────┐
                    │          Local Network       │              │
                    │                              │              │
                    │  1. mDNS Discovery           │              │
                    │     _a2a._tcp.local ─────────┤              │
                    │                              │              │
                    │  2. LAD-A2A                  │              │
                    │     /.well-known/lad/agents  │              │
                    │                              │              │
                    │  3. A2A JSON-RPC 2.0         │              │
                    │     SendMessage ─────────────┤              │
                    │                              ▼              │
                    │                    ┌─────────────────────┐  │
                    │                    │    Hotel Agent      │  │
                    │                    │  (Grand Azure)      │  │
                    │                    │   - OpenAI GPT-4o   │  │
                    │                    │   - LAD-A2A Server  │  │
                    │                    │   - A2A Server      │  │
                    │                    └─────────────────────┘  │
                    └─────────────────────────────────────────────┘
```

## Protocol Compliance

### LAD-A2A (Local Agent Discovery)

| Feature | Implementation |
|---------|----------------|
| mDNS Service Type | `_a2a._tcp.local` |
| TXT Records | `path`, `v`, `org` |
| Discovery Endpoint | `/.well-known/lad/agents` |
| Response Format | JSON with `version`, `network`, `agents[]` |
| Agent Card Reference | Points to A2A `/.well-known/agent.json` |

### A2A Protocol (Google)

| Feature | Implementation |
|---------|----------------|
| Transport | JSON-RPC 2.0 over HTTP |
| Agent Card | `/.well-known/agent.json` with `skills`, `capabilities` |
| SendMessage | ✅ Implemented |
| GetTask | ✅ Implemented |
| CancelTask | ✅ Implemented |
| Task Model | Returns `Task` with `status`, `history` |
| Message Format | `role` + `parts[]` with `TextPart` |

## Prerequisites

- Python 3.9+
- OpenAI API key

## Quick Start

1. **Configure your API key:**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

2. **Run the demo:**
   ```bash
   ./run_demo.sh
   ```

3. **Open in browser:**
   Navigate to http://localhost:8000

## Manual Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Terminal 1: Start Hotel Agent
python hotel_agent.py

# Terminal 2: Start User Agent
python user_agent.py

# Open http://localhost:8000
```

## How It Works

### 1. Discovery Phase

When you open the browser, Aria (user agent) performs real mDNS discovery:

```
📡 Starting mDNS discovery for _a2a._tcp.local...
🔍 mDNS: Found service Grand Azure Hotel at http://127.0.0.1:8001
```

### 2. LAD-A2A Endpoint

Aria fetches the discovery endpoint to get agent metadata:

```http
GET http://localhost:8001/.well-known/lad/agents

{
  "version": "1.0",
  "network": {"ssid": "GrandAzure-Guest", "realm": "grandazurehotel.local"},
  "agents": [{
    "name": "Grand Azure Hotel",
    "agent_card_url": "http://localhost:8001/.well-known/agent.json",
    "capabilities_preview": ["room-service", "spa-booking", "dining"]
  }]
}
```

### 3. A2A AgentCard

Aria fetches the full A2A AgentCard:

```http
GET http://localhost:8001/.well-known/agent.json

{
  "name": "Grand Azure Hotel",
  "url": "http://localhost:8001",
  "protocolVersions": ["1.0"],
  "capabilities": {"streaming": false, "pushNotifications": false},
  "skills": [
    {"id": "spa-wellness", "name": "Spa & Wellness", "tags": ["spa", "massage"]},
    {"id": "dining", "name": "Dining & Restaurants", "tags": ["food", "breakfast"]}
  ]
}
```

### 4. User Consent

The UI prompts the user to connect to the discovered agent.

### 5. LLM-Based Routing

When you send a message, the LLM decides if it should query the hotel agent:

```
User: "What time does the spa open?"
🧠 Routing decision: Query Grand Azure Hotel
```

### 6. A2A Communication

Aria sends a JSON-RPC 2.0 request to the hotel agent:

```http
POST http://localhost:8001/
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "What time does the spa open?"}]
    }
  },
  "id": "uuid"
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "id": "task-uuid",
    "status": {
      "state": "completed",
      "message": {
        "role": "agent",
        "parts": [{"type": "text", "text": "The spa opens at 7:00 AM..."}]
      }
    }
  }
}
```

## File Structure

```
demo/
├── hotel_agent.py      # Hotel concierge (LAD-A2A server + A2A server)
├── user_agent.py       # Personal assistant (LAD-A2A client + A2A client)
├── index.html          # Web interface
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .env                # Your API key (gitignored)
└── run_demo.sh         # Startup script
```

## API Endpoints

### Hotel Agent (port 8001)

| Endpoint | Method | Protocol | Description |
|----------|--------|----------|-------------|
| `/.well-known/lad/agents` | GET | LAD-A2A | Discovery endpoint |
| `/.well-known/agent.json` | GET | A2A | Agent card |
| `/` | POST | A2A | JSON-RPC 2.0 endpoint |
| `/health` | GET | - | Health check |

### User Agent (port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web interface |
| `/ws` | WebSocket | Real-time chat |
| `/health` | GET | Health check |

## Try These Questions

**Routed to Hotel Agent:**
- "What time does the spa open?"
- "What's for breakfast?"
- "Can I get a late checkout?"
- "Any restaurant recommendations nearby?"
- "Is there a gym?"

**Handled by Aria (not routed):**
- "What's the weather like?"
- "Tell me a joke"
- "What's 2 + 2?"
- "Who won the World Cup?"

## Troubleshooting

### "No agents found"

1. Make sure the hotel agent is running on port 8001
2. Check if mDNS is working: `dns-sd -B _a2a._tcp local`
3. Check the hotel agent logs for mDNS registration

### "Connection error"

1. Verify your OpenAI API key in `.env`
2. Check both agents are running
3. Look at terminal output for errors

### mDNS not working

On some systems, mDNS may be blocked. The demo will fall back to direct HTTP discovery if mDNS fails.

## References

- [LAD-A2A Specification](https://lad-a2a.org)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A GitHub Repository](https://github.com/a2aproject/A2A)
