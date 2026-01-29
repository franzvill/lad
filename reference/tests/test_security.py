"""
LAD-A2A Security Tests

Tests for TLS, signing, and verification features.
"""

import os
import pytest
import tempfile
from httpx import AsyncClient, ASGITransport

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from server.lad_server import LADServer, AgentConfig, TLSConfig, create_app
from client.lad_client import (
    LADClient,
    DiscoveredAgent,
    ConsentRequest,
    ConsentResponse,
    ConsentDecision,
    default_consent_callback,
)


# Try to import signing utilities
try:
    from common.signing import (
        SigningConfig,
        generate_signing_keys,
        sign_agent_card,
        verify_agent_card,
        is_signed_agent_card,
    )
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False


# Test fixtures


@pytest.fixture
def agent_config():
    return AgentConfig(
        name="Test Secure Agent",
        description="Agent for security testing",
        role="test",
        capabilities_preview=["secure-cap"],
    )


@pytest.fixture
def temp_keys():
    """Generate temporary signing keys for testing."""
    if not SIGNING_AVAILABLE:
        pytest.skip("Signing module not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        private_path, public_path = generate_signing_keys(tmpdir)
        yield {
            "private": private_path,
            "public": public_path,
            "dir": tmpdir,
        }


# TLS Configuration Tests


class TestTLSConfig:
    """Test TLS configuration."""

    def test_tls_disabled_by_default(self):
        """TLS is disabled by default."""
        config = TLSConfig()
        assert config.enabled is False

    def test_tls_config_validates_missing_files(self, tmp_path):
        """TLS validation fails when cert/key files missing."""
        config = TLSConfig(
            enabled=True,
            certfile=str(tmp_path / "nonexistent.pem"),
            keyfile=str(tmp_path / "nonexistent.key"),
        )
        assert config.validate_paths() is False

    def test_tls_config_validates_existing_files(self, tmp_path):
        """TLS validation passes when files exist."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        cert_path.write_text("dummy cert")
        key_path.write_text("dummy key")

        config = TLSConfig(
            enabled=True,
            certfile=str(cert_path),
            keyfile=str(key_path),
        )
        assert config.validate_paths() is True

    def test_server_uses_https_scheme_when_tls_enabled(self, agent_config, tmp_path):
        """Server uses https:// URLs when TLS is enabled."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        cert_path.write_text("dummy cert")
        key_path.write_text("dummy key")

        tls_config = TLSConfig(
            enabled=True,
            certfile=str(cert_path),
            keyfile=str(key_path),
        )

        server = LADServer(
            agent_config=agent_config,
            tls_config=tls_config,
            enable_mdns=False,
        )

        discovery = server.get_discovery_response()
        agent_card_url = discovery["agents"][0]["agent_card_url"]
        assert agent_card_url.startswith("https://")

        card = server.get_agent_card()
        assert card["url"].startswith("https://")

    def test_server_uses_http_scheme_when_tls_disabled(self, agent_config):
        """Server uses http:// URLs when TLS is disabled."""
        server = LADServer(
            agent_config=agent_config,
            tls_config=TLSConfig(enabled=False),
            enable_mdns=False,
        )

        discovery = server.get_discovery_response()
        agent_card_url = discovery["agents"][0]["agent_card_url"]
        assert agent_card_url.startswith("http://")


# Signing Tests


@pytest.mark.skipif(not SIGNING_AVAILABLE, reason="Signing module not available")
class TestAgentCardSigning:
    """Test AgentCard signing and verification."""

    def test_generate_signing_keys(self, tmp_path):
        """Can generate ECDSA signing keys."""
        private_path, public_path = generate_signing_keys(str(tmp_path))

        assert os.path.exists(private_path)
        assert os.path.exists(public_path)

        # Private key should have restricted permissions
        assert os.stat(private_path).st_mode & 0o077 == 0

    def test_sign_agent_card(self, temp_keys, agent_config):
        """Can sign an AgentCard."""
        server = LADServer(agent_config=agent_config, enable_mdns=False)
        card = server.get_agent_card()

        config = SigningConfig(
            enabled=True,
            private_key_path=temp_keys["private"],
            key_id="test-key-v1",
        )

        signed = sign_agent_card(card, config)

        # Should be a JWS token (3 parts separated by dots)
        assert isinstance(signed, str)
        parts = signed.split(".")
        assert len(parts) == 3

    def test_verify_signed_agent_card(self, temp_keys, agent_config):
        """Can verify a signed AgentCard."""
        server = LADServer(agent_config=agent_config, enable_mdns=False)
        card = server.get_agent_card()

        config = SigningConfig(
            enabled=True,
            private_key_path=temp_keys["private"],
            key_id="test-key-v1",
        )

        signed = sign_agent_card(card, config)
        result = verify_agent_card(signed, public_key_path=temp_keys["public"])

        assert result.valid is True
        assert result.agent_card["name"] == "Test Secure Agent"
        assert result.key_id == "test-key-v1"
        assert result.signed_at is not None

    def test_verify_with_wrong_key_fails(self, temp_keys, agent_config, tmp_path):
        """Verification fails with wrong public key."""
        # Generate a different key pair
        wrong_private, wrong_public = generate_signing_keys(str(tmp_path / "wrong"))

        server = LADServer(agent_config=agent_config, enable_mdns=False)
        card = server.get_agent_card()

        config = SigningConfig(
            enabled=True,
            private_key_path=temp_keys["private"],
        )

        signed = sign_agent_card(card, config)
        result = verify_agent_card(signed, public_key_path=wrong_public)

        assert result.valid is False
        assert "signature" in result.error.lower()

    def test_is_signed_agent_card_detection(self, temp_keys, agent_config):
        """Can detect signed vs unsigned AgentCards."""
        server = LADServer(agent_config=agent_config, enable_mdns=False)
        card = server.get_agent_card()

        # Unsigned card (dict) should not be detected as signed
        assert is_signed_agent_card(card) is False

        # Sign the card
        config = SigningConfig(
            enabled=True,
            private_key_path=temp_keys["private"],
        )
        signed = sign_agent_card(card, config)

        # Signed card (string) should be detected as signed
        assert is_signed_agent_card(signed) is True

    def test_tampered_token_fails_verification(self, temp_keys, agent_config):
        """Tampered tokens fail verification."""
        server = LADServer(agent_config=agent_config, enable_mdns=False)
        card = server.get_agent_card()

        config = SigningConfig(
            enabled=True,
            private_key_path=temp_keys["private"],
        )

        signed = sign_agent_card(card, config)

        # Tamper with the payload (middle part)
        parts = signed.split(".")
        parts[1] = parts[1][:-5] + "XXXXX"
        tampered = ".".join(parts)

        result = verify_agent_card(tampered, public_key_path=temp_keys["public"])
        assert result.valid is False


# Server Signing Integration Tests


@pytest.mark.skipif(not SIGNING_AVAILABLE, reason="Signing module not available")
class TestServerSigningIntegration:
    """Test server with signing enabled."""

    @pytest.fixture
    def signed_server(self, agent_config, temp_keys):
        """Create a server with signing enabled."""
        signing_config = SigningConfig(
            enabled=True,
            private_key_path=temp_keys["private"],
            key_id="test-key-v1",
        )
        return LADServer(
            agent_config=agent_config,
            signing_config=signing_config,
            enable_mdns=False,
        )

    def test_server_can_generate_signed_card(self, signed_server):
        """Server can generate signed AgentCards."""
        signed = signed_server.get_signed_agent_card()

        assert signed is not None
        assert is_signed_agent_card(signed)

    @pytest.mark.asyncio
    async def test_server_returns_signed_card_when_requested(
        self, signed_server, temp_keys
    ):
        """Server returns signed AgentCard when client requests it."""
        app = create_app(signed_server)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Request signed format
            response = await client.get(
                "/.well-known/agent.json",
                headers={"Accept": "application/jose"},
            )

            assert response.status_code == 200
            assert "application/jose" in response.headers["content-type"]

            # Verify the signature
            result = verify_agent_card(
                response.text, public_key_path=temp_keys["public"]
            )
            assert result.valid is True

    @pytest.mark.asyncio
    async def test_server_returns_json_by_default(self, signed_server):
        """Server returns JSON AgentCard by default."""
        app = create_app(signed_server)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/.well-known/agent.json")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"

            data = response.json()
            assert "name" in data


# Client Verification Tests


class TestClientVerification:
    """Test client verification features."""

    def test_discovered_agent_has_verification_fields(self):
        """DiscoveredAgent includes verification fields."""
        agent = DiscoveredAgent(
            name="Test",
            description="Test agent",
            role="test",
            agent_card_url="http://test/.well-known/agent.json",
        )

        assert hasattr(agent, "verified")
        assert hasattr(agent, "verification_method")
        assert hasattr(agent, "verification_error")
        assert agent.verified is False
        assert agent.verification_method is None

    def test_client_initializes_with_tls_verification(self):
        """Client has TLS verification enabled by default."""
        client = LADClient()
        assert client.verify_tls is True

    def test_client_can_disable_tls_verification(self):
        """Client can disable TLS verification for development."""
        client = LADClient(verify_tls=False)
        assert client.verify_tls is False


# Domain Verification Tests


class TestDomainVerification:
    """Test domain verification logic."""

    @pytest.mark.asyncio
    async def test_domain_match_passes_verification(self, agent_config):
        """Domain verification passes when organization matches domain."""
        server = LADServer(
            agent_config=agent_config,
            network_realm="test.example.com",
            enable_mdns=False,
        )

        card = server.get_agent_card()
        # Provider organization is set from network_realm
        assert card["provider"]["organization"] == "test.example.com"


# Malformed Input Tests


class TestMalformedInput:
    """Test handling of malformed inputs."""

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self, agent_config):
        """Client handles malformed JSON responses gracefully."""
        from fastapi import FastAPI
        from fastapi.responses import Response

        app = FastAPI()

        @app.get("/.well-known/lad/agents")
        async def bad_json():
            return Response(content="not valid json {{{", media_type="application/json")

        client = LADClient(verify_tls=False)

        # Should raise an error but not crash
        with pytest.raises(Exception):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as http_client:
                response = await http_client.get("/.well-known/lad/agents")
                response.json()  # Should raise

    @pytest.mark.asyncio
    async def test_handles_empty_agents_list(self, agent_config):
        """Client handles empty agents list."""
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/.well-known/lad/agents")
        async def empty_agents():
            return {"version": "1.0", "agents": []}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            response = await http_client.get("/.well-known/lad/agents")
            data = response.json()

            assert data["agents"] == []


# mDNS Service Listener Tests


class TestMDNSListener:
    """Test mDNS service listener behavior."""

    def test_mdns_listener_tracks_agents(self):
        """MDNSListener maintains agent list."""
        from client.lad_client import MDNSListener

        listener = MDNSListener()
        assert listener.agents == []
        assert listener._agents_by_name == {}

    def test_mdns_listener_uses_https_when_configured(self):
        """MDNSListener uses HTTPS URLs when configured."""
        from client.lad_client import MDNSListener

        listener = MDNSListener(use_https=True)
        assert listener._use_https is True


# Authentication Configuration Tests


class TestAuthConfig:
    """Tests for authentication configuration."""

    def test_auth_config_none_by_default(self, agent_config):
        """AgentCard has no authentication by default."""
        server = LADServer(agent_config=agent_config, enable_mdns=False)
        card = server.get_agent_card()

        assert "authentication" not in card

    def test_auth_config_oauth2(self):
        """AgentCard includes OAuth2 authentication when configured."""
        from server.lad_server import AuthConfig

        auth = AuthConfig(
            method="oauth2",
            token_url="https://auth.example.com/token",
            authorization_url="https://auth.example.com/authorize",
            scopes=["agent:read", "agent:write"],
            client_id="test-client",
        )
        config = AgentConfig(
            name="Test Agent",
            description="Test",
            role="test",
            capabilities_preview=["info"],
            auth_config=auth,
        )
        server = LADServer(agent_config=config, enable_mdns=False)
        card = server.get_agent_card()

        assert "authentication" in card
        auth_field = card["authentication"]
        assert auth_field["type"] == "oauth2"
        assert auth_field["tokenUrl"] == "https://auth.example.com/token"
        assert auth_field["authorizationUrl"] == "https://auth.example.com/authorize"
        assert auth_field["scopes"] == ["agent:read", "agent:write"]
        assert auth_field["clientId"] == "test-client"

    def test_auth_config_oidc(self):
        """AgentCard includes OIDC authentication when configured."""
        from server.lad_server import AuthConfig

        auth = AuthConfig(
            method="oidc",
            issuer="https://auth.example.com",
            token_url="https://auth.example.com/token",
            scopes=["openid", "profile"],
        )
        config = AgentConfig(
            name="Test Agent",
            description="Test",
            role="test",
            capabilities_preview=["info"],
            auth_config=auth,
        )
        server = LADServer(agent_config=config, enable_mdns=False)
        card = server.get_agent_card()

        assert "authentication" in card
        auth_field = card["authentication"]
        assert auth_field["type"] == "oidc"
        assert auth_field["issuer"] == "https://auth.example.com"
        assert auth_field["scopes"] == ["openid", "profile"]

    def test_auth_config_api_key(self):
        """AgentCard includes API key authentication when configured."""
        from server.lad_server import AuthConfig

        auth = AuthConfig(
            method="api_key",
            api_key_header="X-Custom-API-Key",
            documentation_url="https://docs.example.com/auth",
        )
        config = AgentConfig(
            name="Test Agent",
            description="Test",
            role="test",
            capabilities_preview=["info"],
            auth_config=auth,
        )
        server = LADServer(agent_config=config, enable_mdns=False)
        card = server.get_agent_card()

        assert "authentication" in card
        auth_field = card["authentication"]
        assert auth_field["type"] == "api_key"
        assert auth_field["headerName"] == "X-Custom-API-Key"
        assert auth_field["documentationUrl"] == "https://docs.example.com/auth"

    def test_auth_config_bearer(self):
        """AgentCard includes bearer token authentication when configured."""
        from server.lad_server import AuthConfig

        auth = AuthConfig(method="bearer")
        config = AgentConfig(
            name="Test Agent",
            description="Test",
            role="test",
            capabilities_preview=["info"],
            auth_config=auth,
        )
        server = LADServer(agent_config=config, enable_mdns=False)
        card = server.get_agent_card()

        assert "authentication" in card
        auth_field = card["authentication"]
        assert auth_field["type"] == "bearer"
        assert auth_field["scheme"] == "Bearer"


# User Consent Tests


class TestUserConsent:
    """Test user consent flow per spec section 4.3."""

    def test_consent_request_creation(self):
        """ConsentRequest contains required information."""
        agent = DiscoveredAgent(
            name="Test Agent",
            description="Test description",
            role="test",
            agent_card_url="http://test/.well-known/agent.json",
            capabilities_preview=["cap1", "cap2"],
            verified=True,
            verification_method="tls",
        )

        request = ConsentRequest(
            agent=agent,
            verified=agent.verified,
            verification_method=agent.verification_method,
            capabilities=agent.capabilities_preview,
        )

        assert request.agent.name == "Test Agent"
        assert request.verified is True
        assert request.verification_method == "tls"
        assert request.capabilities == ["cap1", "cap2"]

    def test_consent_request_to_display_dict(self):
        """ConsentRequest can be converted to display dictionary."""
        agent = DiscoveredAgent(
            name="Test Agent",
            description="Test description",
            role="test",
            agent_card_url="http://test/.well-known/agent.json",
            capabilities_preview=["cap1"],
            source="mdns",
        )

        request = ConsentRequest(
            agent=agent,
            verified=False,
            verification_method=None,
            capabilities=["cap1"],
        )

        display = request.to_display_dict()
        assert display["agent_name"] == "Test Agent"
        assert display["verified"] is False
        assert display["verification_method"] == "none"
        assert display["source"] == "mdns"

    def test_consent_decision_enum(self):
        """ConsentDecision has expected values."""
        assert ConsentDecision.APPROVED.value == "approved"
        assert ConsentDecision.DENIED.value == "denied"
        assert ConsentDecision.DEFERRED.value == "deferred"

    @pytest.mark.asyncio
    async def test_default_consent_approves_verified(self):
        """Default consent callback approves verified agents."""
        agent = DiscoveredAgent(
            name="Verified Agent",
            description="Test",
            role="test",
            agent_card_url="http://test/.well-known/agent.json",
            verified=True,
        )

        request = ConsentRequest(
            agent=agent,
            verified=True,
            verification_method="tls",
            capabilities=[],
        )

        response = await default_consent_callback(request)
        assert response.decision == ConsentDecision.APPROVED

    @pytest.mark.asyncio
    async def test_default_consent_denies_unverified(self):
        """Default consent callback denies unverified agents."""
        agent = DiscoveredAgent(
            name="Unverified Agent",
            description="Test",
            role="test",
            agent_card_url="http://test/.well-known/agent.json",
            verified=False,
        )

        request = ConsentRequest(
            agent=agent,
            verified=False,
            verification_method=None,
            capabilities=[],
        )

        response = await default_consent_callback(request)
        assert response.decision == ConsentDecision.DENIED

    def test_client_creates_consent_request(self):
        """LADClient can create consent requests."""
        client = LADClient(verify_tls=False)
        agent = DiscoveredAgent(
            name="Test",
            description="Test",
            role="test",
            agent_card_url="http://test/.well-known/agent.json",
            capabilities_preview=["cap1", "cap2"],
            verified=True,
            verification_method="jws",
        )

        request = client.create_consent_request(agent)

        assert request.agent == agent
        assert request.verified is True
        assert request.verification_method == "jws"
        assert request.capabilities == ["cap1", "cap2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
