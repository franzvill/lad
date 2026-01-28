#!/usr/bin/env python3
"""
LAD-A2A Demo Script

Runs a server and client together to demonstrate the discovery flow.
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

# Add reference directory to path
sys.path.insert(0, str(Path(__file__).parent))

from client.lad_client import LADClient


async def run_demo():
    """Run the LAD-A2A demo."""
    print("=" * 60)
    print("LAD-A2A Reference Implementation Demo")
    print("=" * 60)

    # Start the server in background
    print("\n[1] Starting LAD-A2A server...")
    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m", "server.lad_server",
            "--name", "Demo Hotel Concierge",
            "--description", "Your AI concierge for hotel services",
            "--role", "hotel-concierge",
            "--capabilities", "info", "dining", "spa", "reservations",
            "--port", "8080",
            "--ssid", "DemoHotel-Guest",
            "--realm", "demohotel.com",
        ],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    print("[1] Waiting for server to start...")
    await asyncio.sleep(2)

    if server_process.poll() is not None:
        print("[!] Server failed to start!")
        stdout, stderr = server_process.communicate()
        print(f"stdout: {stdout.decode()}")
        print(f"stderr: {stderr.decode()}")
        return

    print("[1] Server running on http://localhost:8080")

    try:
        # Run client discovery
        print("\n[2] Running LAD-A2A client discovery...")
        print("-" * 40)

        client = LADClient(mdns_timeout=2.0)

        # Test 1: Well-known discovery
        print("\n[Test A] Well-known endpoint discovery:")
        result = await client.discover(
            fallback_url="http://localhost:8080",
            try_mdns=False,
            fetch_cards=True,
        )

        print(f"  Discovery method: {result.discovery_method}")
        print(f"  Agents found: {len(result.agents)}")

        for agent in result.agents:
            print(f"\n  Agent: {agent.name}")
            print(f"    Role: {agent.role}")
            print(f"    Description: {agent.description}")
            print(f"    AgentCard URL: {agent.agent_card_url}")
            print(f"    Capabilities Preview: {agent.capabilities_preview}")

            if agent.agent_card:
                print(f"    AgentCard fetched: ✓")
                skills = [s["id"] for s in agent.agent_card.get("skills", [])]
                print(f"    Skills: {skills}")

        # Test 2: mDNS discovery (if available)
        print("\n[Test B] mDNS discovery (3 second scan):")
        result_mdns = await client.discover(
            try_mdns=True,
            fetch_cards=True,
        )

        if result_mdns.agents:
            print(f"  mDNS agents found: {len(result_mdns.agents)}")
            for agent in result_mdns.agents:
                print(f"    - {agent.name} ({agent.agent_card_url})")
        else:
            print("  No agents found via mDNS (may be blocked on this network)")

        if result_mdns.errors:
            for err in result_mdns.errors:
                print(f"  Note: {err}")

        print("\n" + "=" * 60)
        print("Demo complete!")
        print("=" * 60)

    finally:
        # Stop server
        print("\n[3] Stopping server...")
        server_process.terminate()
        server_process.wait()
        print("[3] Server stopped")


def main():
    """Entry point."""
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\n[!] Demo interrupted")


if __name__ == "__main__":
    main()
