"""
LAD-A2A Reference Server

Provides:
- mDNS/DNS-SD advertisement via _a2a._tcp
- /.well-known/lad/agents discovery endpoint
- Mock A2A AgentCard at /.well-known/agent.json
"""

import socket
import argparse
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from zeroconf import ServiceInfo, Zeroconf


class AgentConfig(BaseModel):
    """Configuration for an agent to advertise."""
    name: str
    description: str
    role: str
    capabilities_preview: list[str]
    version: str = "1.0.0"


class LADServer:
    """LAD-A2A Discovery Server."""

    def __init__(
        self,
        agent_config: AgentConfig,
        host: str = "0.0.0.0",
        port: int = 8080,
        network_ssid: Optional[str] = None,
        network_realm: Optional[str] = None,
        enable_mdns: bool = True,
    ):
        self.agent_config = agent_config
        self.host = host
        self.port = port
        self.network_ssid = network_ssid
        self.network_realm = network_realm or socket.gethostname() or "local"
        self.enable_mdns = enable_mdns
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None

    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start_mdns(self) -> None:
        """Start mDNS advertisement."""
        if not self.enable_mdns:
            print("[mDNS] Disabled - using well-known endpoint only")
            return

        self.zeroconf = Zeroconf()

        local_ip = self._get_local_ip()

        # TXT record per LAD-A2A spec
        txt_records = {
            "path": "/.well-known/agent.json",
            "v": "1",
            "org": self.network_realm,
        }

        self.service_info = ServiceInfo(
            "_a2a._tcp.local.",
            f"{self.agent_config.name}._a2a._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=txt_records,
            server=f"{socket.gethostname()}.local.",
        )

        self.zeroconf.register_service(self.service_info)
        print(f"[mDNS] Advertising: {self.agent_config.name}._a2a._tcp.local on {local_ip}:{self.port}")

    def stop_mdns(self) -> None:
        """Stop mDNS advertisement."""
        if not self.enable_mdns:
            return
        if self.zeroconf and self.service_info:
            self.zeroconf.unregister_service(self.service_info)
            self.zeroconf.close()
            print("[mDNS] Service unregistered")

    def get_discovery_response(self) -> dict:
        """Generate LAD-A2A discovery response."""
        base_url = f"http://{self._get_local_ip()}:{self.port}"

        response = {
            "version": "1.0",
            "agents": [
                {
                    "name": self.agent_config.name,
                    "description": self.agent_config.description,
                    "role": self.agent_config.role,
                    "agent_card_url": f"{base_url}/.well-known/agent.json",
                    "capabilities_preview": self.agent_config.capabilities_preview,
                }
            ]
        }

        # Add network info if available
        network = {}
        if self.network_ssid:
            network["ssid"] = self.network_ssid
        if self.network_realm:
            network["realm"] = self.network_realm
        if network:
            response["network"] = network

        return response

    def get_agent_card(self) -> dict:
        """Generate A2A AgentCard."""
        base_url = f"http://{self._get_local_ip()}:{self.port}"

        return {
            "name": self.agent_config.name,
            "description": self.agent_config.description,
            "version": self.agent_config.version,
            "url": f"{base_url}/a2a",
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
            },
            "skills": [
                {
                    "id": skill,
                    "name": skill.replace("-", " ").title(),
                    "description": f"Provides {skill} functionality",
                }
                for skill in self.agent_config.capabilities_preview
            ],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
        }


def create_app(server: LADServer) -> FastAPI:
    """Create FastAPI application with LAD-A2A endpoints."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Start mDNS on startup
        server.start_mdns()
        yield
        # Stop mDNS on shutdown
        server.stop_mdns()

    app = FastAPI(
        title="LAD-A2A Reference Server",
        description="Local Agent Discovery for A2A - Reference Implementation",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware per LAD-A2A spec
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/.well-known/lad/agents")
    async def discovery_endpoint():
        """LAD-A2A discovery endpoint."""
        response = JSONResponse(
            content=server.get_discovery_response(),
            headers={
                "Cache-Control": "max-age=300, must-revalidate",
            }
        )
        return response

    @app.get("/.well-known/agent.json")
    async def agent_card():
        """A2A AgentCard endpoint."""
        return server.get_agent_card()

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok", "agent": server.agent_config.name}

    return app


def main():
    """Run the LAD-A2A server."""
    parser = argparse.ArgumentParser(description="LAD-A2A Reference Server")
    parser.add_argument("--name", default="Demo Agent", help="Agent name")
    parser.add_argument("--description", default="LAD-A2A demo agent", help="Agent description")
    parser.add_argument("--role", default="demo", help="Agent role")
    parser.add_argument("--capabilities", nargs="+", default=["info", "demo"], help="Capabilities")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument("--ssid", help="Network SSID")
    parser.add_argument("--realm", help="Network realm/domain")
    parser.add_argument("--no-mdns", action="store_true", help="Disable mDNS advertisement")

    args = parser.parse_args()

    config = AgentConfig(
        name=args.name,
        description=args.description,
        role=args.role,
        capabilities_preview=args.capabilities,
    )

    server = LADServer(
        agent_config=config,
        host=args.host,
        port=args.port,
        network_ssid=args.ssid,
        network_realm=args.realm,
        enable_mdns=not args.no_mdns,
    )

    app = create_app(server)

    import uvicorn
    print(f"\n[LAD-A2A Server] Starting on http://{args.host}:{args.port}")
    print(f"[LAD-A2A Server] Discovery: http://localhost:{args.port}/.well-known/lad/agents")
    print(f"[LAD-A2A Server] AgentCard: http://localhost:{args.port}/.well-known/agent.json\n")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
