#!/usr/bin/env python3
"""
Guest Device Simulation

Simulates a guest device joining a hotel network and discovering
the hotel's AI concierge via LAD-A2A.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")

from client.lad_client import LADClient


async def simulate_guest_device():
    """Simulate a guest device discovering agents on the hotel network."""

    print("=" * 60)
    print("🏨 Guest Device - Joining Hotel Network")
    print("=" * 60)

    # Get server URL from environment (set by docker-compose)
    server_url = os.environ.get("LAD_SERVER_URL", "http://hotel-agent:8080")

    print(f"\n[1] Connected to network")
    print(f"[2] Starting LAD-A2A discovery...")
    print(f"    Fallback URL: {server_url}")

    client = LADClient(mdns_timeout=5.0, http_timeout=10.0)

    # Wait for server to be ready
    print("\n[3] Waiting for hotel network services...")
    await asyncio.sleep(3)

    # Try discovery with mDNS first, fall back to well-known
    print("\n[4] Attempting discovery...")

    result = await client.discover(
        fallback_url=server_url,
        try_mdns=True,
        fetch_cards=True,
    )

    print(f"\n[5] Discovery complete!")
    print(f"    Method: {result.discovery_method}")
    print(f"    Agents found: {len(result.agents)}")

    if result.agents:
        print("\n" + "=" * 60)
        print("📋 Available Hotel Services")
        print("=" * 60)

        for i, agent in enumerate(result.agents, 1):
            print(f"\n  [{i}] {agent.name}")
            print(f"      Description: {agent.description}")
            print(f"      Role: {agent.role}")
            print(f"      Capabilities: {', '.join(agent.capabilities_preview)}")

            if agent.agent_card:
                print(f"      AgentCard: ✓ Verified")
                skills = [s["name"] for s in agent.agent_card.get("skills", [])]
                print(f"      Skills: {', '.join(skills)}")

                # Simulate user consent
                print(f"\n      💬 'Would you like to connect to {agent.name}?'")
                print(f"         [User selects: Connect]")
                print(f"\n      ✅ Connected! You can now ask about:")
                for skill in skills:
                    print(f"         • {skill}")

    if result.errors:
        print("\n[Warnings]")
        for err in result.errors:
            print(f"  ⚠ {err}")

    print("\n" + "=" * 60)
    print("🎉 Guest device successfully discovered hotel services!")
    print("=" * 60)

    # Simulate some interactions
    print("\n[Demo] Simulating guest interactions...")
    await asyncio.sleep(2)

    print("\n  Guest: 'What time is breakfast?'")
    print("  Hotel Concierge: 'Breakfast is served from 7:00 AM to 10:30 AM'")
    print("                   'in the Garden Restaurant on the ground floor.'")

    await asyncio.sleep(1)

    print("\n  Guest: 'Book a spa appointment for 3 PM'")
    print("  Hotel Concierge: 'I've booked a spa appointment for you at 3:00 PM.'")
    print("                   'Please arrive 15 minutes early. Enjoy!'")

    print("\n" + "=" * 60)
    print("Simulation complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(simulate_guest_device())
