# LAD-A2A Examples

Real-world integration scenarios for LAD-A2A.

## Hotel Concierge

A hotel deploys an AI concierge that guests can discover automatically when they connect to the hotel Wi-Fi.

### Server Setup

```python
from server.lad_server import LADServer, AgentConfig, create_app

config = AgentConfig(
    name="Grand Hotel Concierge",
    description="Your AI concierge for hotel services",
    role="hotel-concierge",
    capabilities_preview=["info", "dining", "spa", "reservations", "housekeeping"]
)

server = LADServer(
    agent_config=config,
    port=443,
    network_ssid="GrandHotel-Guest",
    network_realm="grandhotel.com"
)

app = create_app(server)
```

### Discovery Response

```json
{
  "version": "1.0",
  "network": {
    "ssid": "GrandHotel-Guest",
    "realm": "grandhotel.com"
  },
  "agents": [
    {
      "name": "Grand Hotel Concierge",
      "description": "Your AI concierge for hotel services",
      "role": "hotel-concierge",
      "agent_card_url": "https://ai.grandhotel.com/.well-known/agent.json",
      "capabilities_preview": ["info", "dining", "spa", "reservations", "housekeeping"]
    }
  ]
}
```

### Guest Experience

1. Guest connects phone to "GrandHotel-Guest" Wi-Fi
2. Guest's AI assistant discovers the hotel concierge
3. Notification: "Hotel Concierge available - Connect?"
4. Guest approves, can now ask:
   - "What time is breakfast?"
   - "Book a spa appointment for 3 PM"
   - "Request late checkout"

---

## Enterprise Campus

A corporate campus with multiple AI agents for different services.

### Discovery Response

```json
{
  "version": "1.0",
  "network": {
    "realm": "corp.acme.com"
  },
  "agents": [
    {
      "name": "IT Helpdesk",
      "description": "Technical support and IT services",
      "role": "it-support",
      "agent_card_url": "https://helpdesk.corp.acme.com/.well-known/agent.json",
      "capabilities_preview": ["tickets", "password-reset", "software-requests"]
    },
    {
      "name": "Facilities",
      "description": "Building and workspace services",
      "role": "facilities",
      "agent_card_url": "https://facilities.corp.acme.com/.well-known/agent.json",
      "capabilities_preview": ["room-booking", "maintenance", "parking"]
    },
    {
      "name": "HR Assistant",
      "description": "Human resources inquiries",
      "role": "hr",
      "agent_card_url": "https://hr.corp.acme.com/.well-known/agent.json",
      "capabilities_preview": ["benefits", "policies", "time-off"]
    }
  ]
}
```

### Employee Experience

Employee connects to corporate Wi-Fi and can:
- "Book conference room 4B for tomorrow at 2 PM"
- "I forgot my password"
- "How many PTO days do I have?"

---

## Cruise Ship

A cruise ship with entertainment, dining, and services agents.

### Discovery Response

```json
{
  "version": "1.0",
  "network": {
    "ssid": "OceanLiner-Guest",
    "realm": "oceanliner.cruise"
  },
  "agents": [
    {
      "name": "Ship Concierge",
      "description": "Your onboard assistant",
      "role": "concierge",
      "agent_card_url": "https://services.oceanliner.cruise/.well-known/agent.json",
      "capabilities_preview": ["schedule", "dining", "excursions", "spa", "entertainment"]
    }
  ]
}
```

### Passenger Experience

- "What shows are on tonight?"
- "Book dinner at the Italian restaurant for 7 PM"
- "What time does the ship dock tomorrow?"

---

## Hospital Wayfinding

A hospital with navigation and services.

### Discovery Response

```json
{
  "version": "1.0",
  "network": {
    "ssid": "CityHospital-Guest",
    "realm": "cityhospital.org"
  },
  "agents": [
    {
      "name": "Hospital Guide",
      "description": "Navigation and visitor services",
      "role": "wayfinding",
      "agent_card_url": "https://guide.cityhospital.org/.well-known/agent.json",
      "capabilities_preview": ["navigation", "visiting-hours", "cafeteria", "parking"]
    }
  ]
}
```

### Visitor Experience

- "How do I get to radiology?"
- "What are the visiting hours for ICU?"
- "Where's the nearest coffee shop?"

---

## Client Integration

### Basic Discovery

```python
import asyncio
from client.lad_client import LADClient

async def discover_agents():
    client = LADClient()

    # Discover via mDNS with well-known fallback
    result = await client.discover(
        fallback_url="http://network-gateway.local",
        try_mdns=True,
        fetch_cards=True
    )

    for agent in result.agents:
        print(f"Found: {agent.name}")
        print(f"  Capabilities: {agent.capabilities_preview}")

        if agent.agent_card:
            # Agent verified, ready to connect
            print(f"  Skills: {[s['id'] for s in agent.agent_card['skills']]}")

asyncio.run(discover_agents())
```

### With User Consent Flow

```python
async def discover_with_consent():
    client = LADClient()
    result = await client.discover(fallback_url="http://hotel.local:8080")

    for agent in result.agents:
        # Show consent UI
        print(f"\nFound: {agent.name}")
        print(f"Verified for: {agent.agent_card.get('url', 'unknown')}")
        print(f"Capabilities: {', '.join(agent.capabilities_preview)}")

        consent = input("\nConnect? [y/N]: ")
        if consent.lower() == 'y':
            # Proceed with A2A connection
            print(f"Connecting to {agent.name}...")
            # ... initiate A2A session
```

---

## mDNS Advertisement

For environments where mDNS is supported:

```
Service: Hotel Concierge._a2a._tcp.local
Target: concierge.grandhotel.local
Port: 443
TXT:
  path=/.well-known/agent.json
  v=1
  org=GrandHotel
```

Clients browse for `_a2a._tcp` services and extract the AgentCard path from TXT records.
