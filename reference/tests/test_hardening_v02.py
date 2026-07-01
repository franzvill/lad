"""
LAD-A2A v0.2 hardening tests.

Locks in the fixes from the hostile-network audit: channel encryption is kept
strictly separate from identity verification, a failed signature is fatal,
signed cards must be fresh, plaintext is refused under TLS policy, and discovery
aggregates + dedups across mechanisms.
"""

import time

import pytest
from httpx import AsyncClient, ASGITransport

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from fastapi import FastAPI

from server.lad_server import LADServer, AgentConfig
from client.lad_client import LADClient, DiscoveredAgent, ConsentRequest

try:
    import jwt
    from common.signing import SigningConfig, generate_signing_keys, sign_agent_card, verify_agent_card
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False


# ---- Channel vs identity separation -------------------------------------------------


def _patch_transport(client: LADClient, app: FastAPI):
    """Route the client's HTTP calls to an in-process ASGI app."""
    def _factory():
        return AsyncClient(transport=ASGITransport(app=app), base_url="https://hotel.test", verify=False)
    client._get_http_client = _factory  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_wellknown_over_tls_sets_channel_not_verified():
    """A TLS discovery fetch encrypts the channel but verifies no identity."""
    server = LADServer(
        agent_config=AgentConfig(
            name="Hotel Concierge", description="d", role="hotel",
            capabilities_preview=["info"],
        ),
        network_realm="grandhotel.com",
        enable_mdns=False,
    )
    app = FastAPI()

    @app.get("/.well-known/lad/agents")
    async def discovery():
        return server.get_discovery_response()

    client = LADClient(verify_tls=True)
    _patch_transport(client, app)

    agents = await client.discover_wellknown("https://hotel.test")
    assert len(agents) == 1
    a = agents[0]
    assert a.channel_encrypted is True   # transport authenticated
    assert a.verified is False           # identity NOT established
    assert a.verification_method is None


@pytest.mark.asyncio
async def test_unsigned_card_over_https_is_not_identity_verified_without_domain():
    """An unsigned card over HTTPS whose org does not match the host stays unverified."""
    app = FastAPI()

    @app.get("/.well-known/agent.json")
    async def card():
        # Host we connect to is hotel.test; claimed org is a different domain.
        return {"name": "X", "provider": {"organization": "someone-else.com"}}

    client = LADClient(verify_tls=True)
    _patch_transport(client, app)

    agent = DiscoveredAgent(
        name="X", description="", role="r",
        agent_card_url="https://hotel.test/.well-known/agent.json",
    )
    await client.fetch_agent_card(agent)

    assert agent.channel_encrypted is True
    assert agent.verified is False  # https alone never verifies identity


@pytest.mark.asyncio
async def test_fetch_refuses_plaintext_under_tls_policy():
    """A non-https card URL is a discovery failure when TLS is enforced."""
    client = LADClient(verify_tls=True)
    agent = DiscoveredAgent(
        name="X", description="", role="r",
        agent_card_url="http://hotel.test/.well-known/agent.json",
    )
    with pytest.raises(ValueError):
        await client.fetch_agent_card(agent)
    assert agent.verified is False
    assert agent.verification_error is not None


# ---- Failed signature is fatal ------------------------------------------------------


@pytest.mark.skipif(not SIGNING_AVAILABLE, reason="signing not available")
@pytest.mark.asyncio
async def test_failed_signature_is_not_trusted_and_not_rescued(tmp_path):
    """A card that fails JWS verification is not stored as trusted or domain-rescued."""
    priv_a, _ = generate_signing_keys(str(tmp_path / "a"))
    _, pub_b = generate_signing_keys(str(tmp_path / "b"))

    card = {"name": "Impostor", "provider": {"organization": "hotel.test"}}
    token = sign_agent_card(card, SigningConfig(enabled=True, private_key_path=priv_a))

    # Client trusts key B, but the card was signed with key A -> verification fails.
    client = LADClient(verify_tls=True, signing_public_key=pub_b)
    agent = DiscoveredAgent(
        name="Impostor", description="", role="r",
        agent_card_url="https://hotel.test/.well-known/agent.json",
    )
    await client._verify_signed_agent_card(agent, token)

    assert agent.verified is False
    assert agent.agent_card is None            # not trusted
    assert agent.unverified_card is not None   # kept only for diagnostics
    assert agent.verification_error is not None

    # Domain verification must NOT rescue it, even though org would match the host.
    agent.agent_card = agent.unverified_card
    await client._verify_domain(agent)
    assert agent.verified is False


# ---- Signed-card freshness ----------------------------------------------------------


@pytest.mark.skipif(not SIGNING_AVAILABLE, reason="signing not available")
def test_signed_card_includes_exp(tmp_path):
    priv, pub = generate_signing_keys(str(tmp_path))
    token = sign_agent_card({"name": "A"}, SigningConfig(enabled=True, private_key_path=priv))
    payload = jwt.decode(token, options={"verify_signature": False})
    assert "exp" in payload and "iat" in payload
    assert payload["exp"] > payload["iat"]
    assert verify_agent_card(token, public_key_path=pub).valid is True


@pytest.mark.skipif(not SIGNING_AVAILABLE, reason="signing not available")
def test_expired_signed_card_is_rejected(tmp_path):
    priv, pub = generate_signing_keys(str(tmp_path))
    priv_pem = open(priv, "rb").read()
    now = int(time.time())
    token = jwt.encode(
        {"agent_card": {"name": "Stale"}, "iat": now - 100000, "exp": now - 10},
        priv_pem, algorithm="ES256",
    )
    result = verify_agent_card(token, public_key_path=pub)
    assert result.valid is False


@pytest.mark.skipif(not SIGNING_AVAILABLE, reason="signing not available")
def test_card_without_exp_is_rejected(tmp_path):
    priv, pub = generate_signing_keys(str(tmp_path))
    priv_pem = open(priv, "rb").read()
    token = jwt.encode(
        {"agent_card": {"name": "NoExp"}, "iat": int(time.time())},
        priv_pem, algorithm="ES256",
    )
    result = verify_agent_card(token, public_key_path=pub)
    assert result.valid is False  # missing required exp claim


# ---- IP-host is not an organizational identity --------------------------------------


@pytest.mark.asyncio
async def test_ip_host_is_never_domain_verified():
    client = LADClient(verify_tls=True)
    agent = DiscoveredAgent(
        name="IP Agent", description="", role="r",
        agent_card_url="https://93.184.216.34/.well-known/agent.json",
    )
    agent.agent_card = {"provider": {"organization": "93.184.216.34"}}
    await client._verify_domain(agent)
    assert agent.verified is False


# ---- Dedup + identity key -----------------------------------------------------------


def test_identity_key_prefers_advertised_id():
    a = DiscoveredAgent(
        name="A", description="", role="r",
        agent_card_url="https://a.example.com/.well-known/agent.json",
        id="did:web:example.com#concierge",
    )
    assert a.identity_key() == "did:web:example.com#concierge"


def test_dedup_prefers_verified_record():
    unverified = DiscoveredAgent(
        name="Concierge", description="", role="r",
        agent_card_url="http://10.0.0.4:443/.well-known/agent.json",
        id="did:web:grandhotel.com#c", source="mdns",
    )
    verified = DiscoveredAgent(
        name="Concierge", description="", role="r",
        agent_card_url="https://ai.grandhotel.com/.well-known/agent.json",
        id="did:web:grandhotel.com#c", source="wellknown",
        verified=True, verification_method="domain", channel_encrypted=True,
    )
    out = LADClient._dedup_agents([unverified, verified])
    assert len(out) == 1
    assert out[0].verified is True
    assert out[0].source == "wellknown"


# ---- Consent renders capabilities from the verified card ----------------------------


def test_consent_capabilities_come_from_verified_card():
    client = LADClient(verify_tls=False)
    agent = DiscoveredAgent(
        name="Concierge", description="", role="r",
        agent_card_url="https://ai.grandhotel.com/.well-known/agent.json",
        capabilities_preview=["info"],  # benign preview from the network
        verified=True,
        agent_card={"skills": [{"id": "payments"}, {"id": "door-unlock"}]},
    )
    req: ConsentRequest = client.create_consent_request(agent)
    assert req.capabilities_source == "agent_card"
    assert set(req.capabilities) == {"payments", "door-unlock"}
    assert req.channel_encrypted is False
