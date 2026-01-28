# JSON Schemas

LAD-A2A defines JSON schemas for protocol messages.

## Discovery Response

**Endpoint:** `/.well-known/lad/agents`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lad-a2a.dev/schemas/discovery-response.json",
  "title": "LAD-A2A Discovery Response",
  "type": "object",
  "required": ["version", "agents"],
  "properties": {
    "version": {
      "type": "string",
      "description": "LAD-A2A protocol version",
      "pattern": "^\\d+\\.\\d+$"
    },
    "network": {
      "type": "object",
      "properties": {
        "ssid": { "type": "string" },
        "realm": { "type": "string" }
      }
    },
    "agents": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "agent_card_url"],
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string" },
          "role": { "type": "string" },
          "agent_card_url": { "type": "string", "format": "uri" },
          "capabilities_preview": {
            "type": "array",
            "items": { "type": "string" }
          }
        }
      }
    }
  }
}
```

### Example Response

```json
{
  "version": "1.0",
  "network": {
    "ssid": "GrandHotel-Guest",
    "realm": "grandhotel.com"
  },
  "agents": [
    {
      "name": "Hotel Concierge",
      "description": "Your AI concierge for hotel services",
      "role": "hotel-concierge",
      "agent_card_url": "https://ai.grandhotel.com/.well-known/agent.json",
      "capabilities_preview": ["info", "dining", "spa", "reservations"]
    }
  ]
}
```

## mDNS TXT Record

**Service Type:** `_a2a._tcp`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lad-a2a.dev/schemas/mdns-txt-record.json",
  "title": "LAD-A2A mDNS TXT Record",
  "type": "object",
  "required": ["path", "v"],
  "properties": {
    "path": {
      "type": "string",
      "description": "Path to AgentCard endpoint",
      "default": "/.well-known/agent.json"
    },
    "v": {
      "type": "string",
      "description": "LAD-A2A version",
      "pattern": "^\\d+$"
    },
    "org": {
      "type": "string",
      "description": "Organization name"
    },
    "id": {
      "type": "string",
      "description": "Agent DID"
    }
  }
}
```

### Example TXT Record

```
path=/.well-known/agent.json
v=1
org=GrandHotel
```

## Download

- [discovery-response.json](https://github.com/franzvill/lad/blob/main/spec/schemas/discovery-response.json)
- [mdns-txt-record.json](https://github.com/franzvill/lad/blob/main/spec/schemas/mdns-txt-record.json)
