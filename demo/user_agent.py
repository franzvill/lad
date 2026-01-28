"""
User Agent (Aria) - Personal AI Assistant with LAD-A2A Discovery
Discovers local agents and routes queries via A2A.
"""

import os
import json
import asyncio
import httpx
import socket
from datetime import datetime
from dotenv import load_dotenv
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
from typing import Optional, Dict, List
from threading import Event

# Load environment variables from .env file
load_dotenv()

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

# Configuration
AGENT_NAME = "Aria"
PORT = 8000
MDNS_DISCOVERY_TIMEOUT = 3.0  # seconds to scan for mDNS services

# OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Connected agents store
connected_agents: Dict[str, dict] = {}

# Aria's system prompt
ARIA_SYSTEM_PROMPT = """You are Aria, a helpful personal AI assistant. You're friendly, concise, and knowledgeable.

You have the ability to connect to local service agents via A2A (Agent-to-Agent) protocol. When connected to local agents, you can query them for specific information.

Currently connected agents:
{connected_agents}

When the user asks about topics that a connected agent specializes in, you should indicate that you'll check with that agent. The actual query will be handled by the system.

Keep your responses concise and helpful. When relaying information from another agent, present it naturally as if you're sharing what you learned.
"""


class DiscoveredAgent(BaseModel):
    """Information about a discovered agent"""
    name: str
    description: str
    url: str
    agent_card_url: str
    capabilities: List[str]
    a2a_endpoint: Optional[str] = None


class A2AServiceListener(ServiceListener):
    """Listener for mDNS _a2a._tcp services"""

    def __init__(self):
        self.services: List[Dict] = []
        self.found_event = Event()

    def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        info = zc.get_service_info(service_type, name)
        if info:
            # Extract address and port
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            if addresses:
                host = addresses[0]
                port = info.port

                # Extract TXT record properties
                properties = {}
                if info.properties:
                    for key, value in info.properties.items():
                        if isinstance(key, bytes):
                            key = key.decode('utf-8')
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        properties[key] = value

                # Build AgentCard URL from TXT record 'path' (per LAD-A2A spec)
                agent_card_path = properties.get("path", "/.well-known/agent.json")
                base_url = f"http://{host}:{port}"

                service_info = {
                    "name": name.replace(f".{service_type}", ""),
                    "host": host,
                    "port": port,
                    "url": base_url,
                    "agent_card_url": f"{base_url}{agent_card_path}",  # From TXT record
                    "properties": properties
                }
                print(f"🔍 mDNS: Found service {service_info['name']} at {service_info['url']}")
                print(f"   TXT records: path={agent_card_path}, v={properties.get('v')}, org={properties.get('org')}")
                self.services.append(service_info)
                self.found_event.set()

    def remove_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        pass

    def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        pass


async def discover_via_mdns(timeout: float = MDNS_DISCOVERY_TIMEOUT) -> List[Dict]:
    """Discover A2A agents via mDNS/DNS-SD"""
    print(f"📡 Starting mDNS discovery for _a2a._tcp.local (timeout: {timeout}s)...")

    def _discover():
        zeroconf = Zeroconf()
        listener = A2AServiceListener()

        try:
            browser = ServiceBrowser(zeroconf, "_a2a._tcp.local.", listener)
            # Wait for services or timeout
            listener.found_event.wait(timeout=timeout)
            # Give a bit more time to find additional services
            Event().wait(timeout=0.5)
            return listener.services
        finally:
            zeroconf.close()

    # Run in thread pool to not block async
    loop = asyncio.get_event_loop()
    services = await loop.run_in_executor(None, _discover)

    print(f"📊 mDNS discovery found {len(services)} service(s)")
    return services


class ChatMessage(BaseModel):
    """WebSocket message format"""
    type: str  # "message", "discover", "connect", "status"
    content: Optional[str] = None
    agent_url: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown"""
    print(f"\n✨ {AGENT_NAME} - Personal AI Assistant")
    print(f"   Web Interface: http://localhost:{PORT}")
    print(f"   Ready to discover local agents!\n")
    yield


app = FastAPI(title=f"{AGENT_NAME} - Personal Assistant", lifespan=lifespan)


async def fetch_agent_from_service(target_url: str, mdns_agent_card_url: Optional[str] = None) -> Optional[DiscoveredAgent]:
    """Discover agents at a target URL using LAD-A2A.

    Discovery flow:
    1. Try LAD-A2A discovery endpoint (/.well-known/lad/agents)
    2. If that fails, fallback to mDNS TXT record 'path' (AgentCard URL)
    3. Build DiscoveredAgent from AgentCard data

    Args:
        target_url: Base URL of the service
        mdns_agent_card_url: AgentCard URL from mDNS TXT record (if available)
    """
    print(f"🔍 Attempting discovery at {target_url}")
    agent_card_url = None
    capabilities_preview = []

    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            # Step 1: Try LAD-A2A discovery endpoint
            discovery_url = f"{target_url}/.well-known/lad/agents"
            print(f"   Trying LAD-A2A endpoint: {discovery_url}")

            try:
                response = await http.get(discovery_url)
                if response.status_code == 200:
                    data = response.json()
                    agents = data.get("agents", [])
                    if agents:
                        agent_info = agents[0]
                        agent_card_url = agent_info.get("agent_card_url")
                        capabilities_preview = agent_info.get("capabilities_preview", [])
                        print(f"   ✅ LAD-A2A discovery: found AgentCard at {agent_card_url}")
            except Exception as e:
                print(f"   ⚠️ LAD-A2A endpoint failed: {e}")

            # Step 2: Fallback to mDNS TXT record if LAD discovery didn't work
            if not agent_card_url and mdns_agent_card_url:
                print(f"   Fallback: Using mDNS TXT record path: {mdns_agent_card_url}")
                agent_card_url = mdns_agent_card_url

            if not agent_card_url:
                print(f"   ❌ No AgentCard URL found")
                return None

            # Step 3: Fetch the full AgentCard
            print(f"   Fetching AgentCard from {agent_card_url}")
            card_response = await http.get(agent_card_url)
            if card_response.status_code != 200:
                print(f"   ❌ Failed to fetch AgentCard: {card_response.status_code}")
                return None

            card = card_response.json()

            # In A2A, the agent's URL from AgentCard IS the JSON-RPC endpoint
            a2a_url = card.get("url", target_url)

            # Extract skills from AgentCard for better routing
            skills = card.get("skills", [])
            skill_tags = []
            for skill in skills:
                skill_tags.extend(skill.get("tags", []))
                skill_tags.append(skill.get("name", ""))

            return DiscoveredAgent(
                name=card.get("name", "Unknown Agent"),
                description=card.get("description", ""),
                url=a2a_url,  # This is the A2A JSON-RPC endpoint
                agent_card_url=agent_card_url,
                capabilities=capabilities_preview + skill_tags,
                a2a_endpoint=a2a_url  # Same as url in A2A spec
            )

    except Exception as e:
        print(f"❌ Discovery failed for {target_url}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def query_agent_a2a(agent: DiscoveredAgent, query: str) -> Optional[str]:
    """Send a query to an agent via A2A protocol (JSON-RPC 2.0 SendMessage)"""
    import uuid

    # A2A endpoint is the agent's URL (from AgentCard)
    a2a_url = agent.url

    # Build A2A SendMessage request per spec
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "SendMessage",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {"type": "text", "text": query}
                ],
                "messageId": str(uuid.uuid4())
            }
        },
        "id": str(uuid.uuid4())
    }

    print(f"📤 A2A SendMessage to {a2a_url}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.post(
                a2a_url,
                json=jsonrpc_request,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()

                # Check for JSON-RPC error
                if "error" in data:
                    print(f"❌ A2A error: {data['error']}")
                    return None

                # Extract response from task result
                result = data.get("result", {})
                status = result.get("status", {})
                message = status.get("message", {})
                parts = message.get("parts", [])

                # Get text from parts
                for part in parts:
                    if part.get("type") == "text":
                        return part.get("text")

            print(f"❌ A2A request failed: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ A2A query failed: {e}")
        return None


async def decide_agent_routing(message: str, agents: Dict[str, dict]) -> Optional[str]:
    """Use LLM to decide if the message should be routed to a connected agent.
    Returns the agent URL if routing is needed, None otherwise."""

    if not agents:
        return None

    # Build agent descriptions for the LLM
    agents_info = "\n".join([
        f"- Agent: {info['name']}\n  URL: {url}\n  Description: {info['description']}\n  Capabilities: {', '.join(info['capabilities'])}"
        for url, info in agents.items()
    ])

    routing_prompt = f"""You are a routing assistant. Based on the user's message, decide if it should be handled by one of the connected agents or if you should handle it yourself.

Connected agents:
{agents_info}

User message: "{message}"

Respond with ONLY one of these:
- The agent URL (e.g., "http://localhost:8001") if this message is relevant to that agent's capabilities
- "NONE" if you should handle this yourself (general knowledge, chitchat, or unrelated topics)

Decision:"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": routing_prompt}],
            max_tokens=50,
            temperature=0
        )
        decision = response.choices[0].message.content.strip()

        # Check if the decision matches any agent URL
        if decision != "NONE" and decision in agents:
            print(f"🧠 Routing decision: Query {agents[decision]['name']}")
            return decision

        print(f"🧠 Routing decision: Handle locally")
        return None

    except Exception as e:
        print(f"Routing decision error: {e}")
        return None


async def generate_response(
    user_message: str,
    conversation_history: List[dict],
    agent_response: Optional[tuple] = None  # (agent_name, response)
) -> str:
    """Generate Aria's response using OpenAI"""

    # Build connected agents description
    agents_desc = "None" if not connected_agents else "\n".join([
        f"- {a['name']}: {a['description']} (capabilities: {', '.join(a['capabilities'])})"
        for a in connected_agents.values()
    ])

    system_prompt = ARIA_SYSTEM_PROMPT.format(connected_agents=agents_desc)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history[-10:])  # Last 10 messages for context

    # If we have an agent response, add it as context
    if agent_response:
        agent_name, response = agent_response
        messages.append({
            "role": "system",
            "content": f"You just queried {agent_name} and received this information:\n\n{response}\n\nNow relay this information to the user naturally."
        })

    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI error: {e}")
        return "I'm having trouble processing that right now. Could you try again?"


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()

    conversation_history = []

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "discover":
                # Scan for agents using real mDNS discovery
                print(f"📡 Received discover request, starting mDNS scan...")
                await websocket.send_json({
                    "type": "status",
                    "status": "scanning",
                    "message": "Scanning local network via mDNS..."
                })

                # Step 1: Discover services via mDNS
                mdns_services = await discover_via_mdns()

                # Step 2: For each discovered service, fetch agent info
                # Use agent_card_url from mDNS TXT record if available
                discovered = []
                for service in mdns_services:
                    agent = await fetch_agent_from_service(
                        service["url"],
                        mdns_agent_card_url=service.get("agent_card_url")
                    )
                    if agent:
                        print(f"✅ Found agent: {agent.name} at {agent.url}")
                        discovered.append(agent)
                    else:
                        print(f"❌ No LAD-A2A agent at {service['url']}")

                print(f"📊 Discovery complete: {len(discovered)} agents found")

                if discovered:
                    agent = discovered[0]
                    await websocket.send_json({
                        "type": "discovered",
                        "agent": {
                            "name": agent.name,
                            "description": agent.description,
                            "url": agent.url,
                            "capabilities": agent.capabilities,
                            "verified": True
                        }
                    })
                else:
                    await websocket.send_json({
                        "type": "status",
                        "status": "no_agents",
                        "message": "No agents found on local network"
                    })

            elif msg_type == "connect":
                # Connect to discovered agent
                agent_url = data.get("agent_url")
                agent = await fetch_agent_from_service(agent_url)

                if agent:
                    connected_agents[agent_url] = {
                        "name": agent.name,
                        "description": agent.description,
                        "url": agent.url,
                        "capabilities": agent.capabilities,
                        "a2a_endpoint": agent.a2a_endpoint
                    }

                    await websocket.send_json({
                        "type": "connected",
                        "agent": {
                            "name": agent.name,
                            "url": agent.url
                        }
                    })

                    # Send welcome message
                    welcome = f"I've connected to {agent.name}'s concierge service. I can now help you with {', '.join(agent.capabilities[:3])}, and more. What would you like to know?"

                    conversation_history.append({"role": "assistant", "content": welcome})

                    await websocket.send_json({
                        "type": "message",
                        "role": "assistant",
                        "content": welcome,
                        "source": None
                    })

            elif msg_type == "message":
                user_message = data.get("content", "")
                conversation_history.append({"role": "user", "content": user_message})

                # Use LLM to decide if we should query a connected agent
                agent_response = None
                queried_agent = None

                routed_url = await decide_agent_routing(user_message, connected_agents)

                if routed_url and routed_url in connected_agents:
                    agent_info = connected_agents[routed_url]
                    agent = DiscoveredAgent(
                        name=agent_info["name"],
                        description=agent_info["description"],
                        url=agent_info["url"],
                        agent_card_url="",
                        capabilities=agent_info["capabilities"],
                        a2a_endpoint=agent_info["a2a_endpoint"]
                    )

                    # Notify frontend we're querying
                    await websocket.send_json({
                        "type": "querying",
                        "agent_name": agent.name,
                        "message": f"Checking with {agent.name}..."
                    })

                    # Query the agent via A2A
                    response = await query_agent_a2a(agent, user_message)
                    if response:
                        agent_response = (agent.name, response)
                        queried_agent = agent.name

                # Generate Aria's response
                response = await generate_response(
                    user_message,
                    conversation_history,
                    agent_response
                )

                conversation_history.append({"role": "assistant", "content": response})

                await websocket.send_json({
                    "type": "message",
                    "role": "assistant",
                    "content": response,
                    "source": queried_agent
                })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


# Serve static files (the demo frontend)
demo_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=demo_dir), name="static")


@app.get("/")
async def index():
    """Serve the main page"""
    return FileResponse(demo_dir / "index.html")


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "agent": AGENT_NAME,
        "connected_agents": len(connected_agents)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
