"""
Hotel Agent - Grand Azure Hotel Concierge
Advertises via LAD-A2A and responds to A2A queries using OpenAI.

Implements:
- LAD-A2A discovery (mDNS + /.well-known/lad/agents)
- A2A protocol (JSON-RPC 2.0 with SendMessage)
"""

import os
import json
import asyncio
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Configuration
HOTEL_NAME = "Grand Azure Hotel"
HOTEL_DOMAIN = "grandazurehotel.local"
PORT = 8001
AGENT_URL = f"http://localhost:{PORT}"

# OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Hotel context for the AI
HOTEL_SYSTEM_PROMPT = """You are the AI concierge for the Grand Azure Hotel, a luxury 5-star beachfront resort.

Hotel Information:
- Location: Oceanfront property with private beach
- Check-in: 3:00 PM, Check-out: 11:00 AM
- Late checkout available until 2:00 PM (complimentary for suite guests)

Amenities:
- Spa & Wellness Center: Open 7:00 AM - 9:00 PM
  - Services: Swedish massage, hot stone therapy, aromatherapy facials, couples treatments
  - Booking required, same-day appointments often available
- Fitness Center: 24/7 access
- Pool: Heated infinity pool, open 6:00 AM - 10:00 PM
- Beach: Private beach with complimentary cabanas and towel service

Dining:
- Sunrise Restaurant: Breakfast 6:30 AM - 10:30 AM (included for most guests)
  - Features: Made-to-order omelettes, fresh seafood, tropical fruits, artisanal pastries
- Azure Terrace: Lunch 12:00 PM - 3:00 PM, Dinner 6:00 PM - 10:00 PM
  - Cuisine: Mediterranean-Asian fusion, locally sourced ingredients
- Pool Bar: 10:00 AM - sunset, cocktails and light fare
- Room Service: 24/7 available

Nearby Recommendations:
- Osteria del Mare (5 min walk): Upscale Italian seafood, $$$
- Sakura Garden (8 min walk): Japanese omakase, $$
- The Local Kitchen (3 min walk): Farm-to-table brunch spot, $$
- Marina District: 10 min walk, shopping and nightlife

Services:
- Concierge desk: 24/7 for reservations, transportation, local tips
- Valet parking: Complimentary
- Airport shuttle: $45 each way, book 24h in advance
- Laundry/Dry cleaning: Same-day service before 10 AM

Keep responses concise, warm, and helpful. You're knowledgeable about the local area.
"""

# Store active tasks (A2A uses task-based model)
tasks: Dict[str, dict] = {}


# ============== A2A Data Models (per spec) ==============

class TextPart(BaseModel):
    """A2A TextPart - text content in a message"""
    type: str = "text"
    text: str


class Message(BaseModel):
    """A2A Message - contains role and parts"""
    role: str  # "user" or "agent"
    parts: List[Dict[str, Any]]
    messageId: Optional[str] = None


class TaskStatus(BaseModel):
    """A2A TaskStatus"""
    state: str  # "submitted", "working", "input-required", "completed", "failed", "canceled"
    message: Optional[Message] = None
    timestamp: Optional[str] = None


class Task(BaseModel):
    """A2A Task - represents an ongoing interaction"""
    id: str
    status: TaskStatus
    history: Optional[List[Message]] = None


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 Request"""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[str | int] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 Response"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[str | int] = None


# mDNS advertisement
mdns_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global mdns_service

    print(f"\n🏨 {HOTEL_NAME} Agent starting...")
    print(f"   LAD-A2A Discovery: {AGENT_URL}/.well-known/lad/agents")
    print(f"   A2A AgentCard: {AGENT_URL}/.well-known/agent.json")
    print(f"   A2A Endpoint: {AGENT_URL}/ (JSON-RPC 2.0)")

    # Advertise via mDNS
    try:
        from zeroconf import Zeroconf, ServiceInfo
        import socket

        zeroconf = Zeroconf()
        service_info = ServiceInfo(
            "_a2a._tcp.local.",
            f"{HOTEL_NAME}._a2a._tcp.local.",
            addresses=[socket.inet_aton("127.0.0.1")],
            port=PORT,
            properties={
                "path": "/.well-known/agent.json",
                "v": "1",
                "org": HOTEL_NAME.replace(" ", ""),
            },
        )
        zeroconf.register_service(service_info)
        mdns_service = (zeroconf, service_info)
        print(f"   mDNS: Advertising as {HOTEL_NAME}._a2a._tcp.local")
    except Exception as e:
        print(f"   mDNS: Not available ({e})")

    print(f"\n   Ready to serve guests! ✨\n")
    yield

    if mdns_service:
        zeroconf, service_info = mdns_service
        zeroconf.unregister_service(service_info)
        zeroconf.close()


app = FastAPI(title=f"{HOTEL_NAME} Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== LAD-A2A Discovery Endpoints ==============

@app.get("/.well-known/lad/agents")
async def lad_discovery():
    """LAD-A2A discovery endpoint"""
    return JSONResponse(
        content={
            "version": "1.0",
            "network": {
                "ssid": "GrandAzure-Guest",
                "realm": HOTEL_DOMAIN
            },
            "agents": [
                {
                    "name": HOTEL_NAME,
                    "description": "Your AI concierge for hotel services, dining, spa, and local recommendations",
                    "role": "hotel-concierge",
                    "agent_card_url": f"{AGENT_URL}/.well-known/agent.json",
                    "capabilities_preview": ["room-service", "spa-booking", "dining", "concierge", "local-tips"]
                }
            ]
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=300, must-revalidate"
        }
    )


# ============== A2A AgentCard (per A2A spec) ==============

@app.get("/.well-known/agent.json")
async def agent_card():
    """A2A AgentCard endpoint - follows A2A specification"""
    return {
        "name": HOTEL_NAME,
        "description": "AI concierge for Grand Azure Hotel - a luxury beachfront resort",
        "url": AGENT_URL,
        "provider": {
            "organization": "Grand Azure Hotel & Resort",
            "url": f"https://{HOTEL_DOMAIN}"
        },
        "version": "1.0.0",
        "protocolVersions": ["1.0"],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True
        },
        "authentication": {
            "schemes": ["none"]
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "hotel-info",
                "name": "Hotel Information",
                "description": "General information about the hotel, amenities, check-in/out times, and policies",
                "tags": ["info", "amenities", "policies"],
                "examples": [
                    "What time is checkout?",
                    "What amenities do you have?",
                    "Is there WiFi?"
                ]
            },
            {
                "id": "dining",
                "name": "Dining & Restaurants",
                "description": "Restaurant hours, menus, reservations, and room service",
                "tags": ["food", "restaurant", "breakfast", "dinner"],
                "examples": [
                    "What time is breakfast?",
                    "Can I order room service?",
                    "What restaurants are on-site?"
                ]
            },
            {
                "id": "spa-wellness",
                "name": "Spa & Wellness",
                "description": "Spa services, treatments, fitness center, pool information",
                "tags": ["spa", "massage", "gym", "pool", "wellness"],
                "examples": [
                    "What spa treatments do you offer?",
                    "When does the pool open?",
                    "Is there a gym?"
                ]
            },
            {
                "id": "local-recommendations",
                "name": "Local Recommendations",
                "description": "Nearby restaurants, attractions, activities, and transportation",
                "tags": ["local", "recommendations", "nearby", "attractions"],
                "examples": [
                    "What restaurants are nearby?",
                    "How do I get to the airport?",
                    "What is there to do around here?"
                ]
            },
            {
                "id": "concierge",
                "name": "Concierge Services",
                "description": "Reservations, transportation, special requests, late checkout",
                "tags": ["concierge", "reservations", "checkout", "transportation"],
                "examples": [
                    "Can I get a late checkout?",
                    "Book me an airport shuttle",
                    "I need extra towels"
                ]
            }
        ]
    }


# ============== A2A JSON-RPC Endpoint ==============

@app.post("/")
async def a2a_jsonrpc(request: Request):
    """A2A JSON-RPC 2.0 endpoint - handles SendMessage and other methods"""

    try:
        body = await request.json()
    except:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            },
            status_code=400
        )

    req = JSONRPCRequest(**body)
    print(f"📨 A2A JSON-RPC: {req.method}")

    # Handle different A2A methods
    if req.method == "SendMessage":
        return await handle_send_message(req)
    elif req.method == "GetTask":
        return await handle_get_task(req)
    elif req.method == "CancelTask":
        return await handle_cancel_task(req)
    else:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {req.method}"},
            "id": req.id
        })


async def handle_send_message(req: JSONRPCRequest) -> JSONResponse:
    """Handle A2A SendMessage method"""

    params = req.params or {}
    message_data = params.get("message", {})

    # Extract text from message parts
    user_text = ""
    parts = message_data.get("parts", [])
    for part in parts:
        if part.get("type") == "text":
            user_text += part.get("text", "")

    if not user_text:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "error": {"code": -32602, "message": "Invalid params: message must contain text parts"},
            "id": req.id
        })

    print(f"   Query: {user_text[:100]}...")

    # Create a task for this interaction
    task_id = str(uuid.uuid4())

    try:
        # Generate response using OpenAI
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": HOTEL_SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=500,
            temperature=0.7
        )
        answer = response.choices[0].message.content
        print(f"   Response: {answer[:100]}...")

        # Create task with completed status
        task = {
            "id": task_id,
            "status": {
                "state": "completed",
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": answer}],
                    "messageId": str(uuid.uuid4())
                },
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            "history": [
                {
                    "role": "user",
                    "parts": parts,
                    "messageId": message_data.get("messageId", str(uuid.uuid4()))
                },
                {
                    "role": "agent",
                    "parts": [{"type": "text", "text": answer}],
                    "messageId": str(uuid.uuid4())
                }
            ]
        }

        tasks[task_id] = task

        return JSONResponse(content={
            "jsonrpc": "2.0",
            "result": task,
            "id": req.id
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": f"Agent error: {str(e)}"},
            "id": req.id
        })


async def handle_get_task(req: JSONRPCRequest) -> JSONResponse:
    """Handle A2A GetTask method"""
    params = req.params or {}
    task_id = params.get("taskId")

    if not task_id or task_id not in tasks:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": "Task not found"},
            "id": req.id
        })

    return JSONResponse(content={
        "jsonrpc": "2.0",
        "result": tasks[task_id],
        "id": req.id
    })


async def handle_cancel_task(req: JSONRPCRequest) -> JSONResponse:
    """Handle A2A CancelTask method"""
    params = req.params or {}
    task_id = params.get("taskId")

    if task_id and task_id in tasks:
        tasks[task_id]["status"]["state"] = "canceled"

    return JSONResponse(content={
        "jsonrpc": "2.0",
        "result": {"success": True},
        "id": req.id
    })


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": HOTEL_NAME, "protocol": "A2A/1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
