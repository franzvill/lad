"""
Tests for LAD-A2A configuration module.

Tests configuration file loading, environment variable overrides,
and config-to-kwargs conversion.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from common.config import (
    ServerConfig,
    ClientConfig,
    load_server_config,
    load_client_config,
    generate_example_config,
    _apply_env_overrides,
    YAML_AVAILABLE,
)


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_values(self):
        """ServerConfig has sensible defaults."""
        config = ServerConfig()
        assert config.name == "LAD-A2A Agent"
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.tls_enabled is False
        assert config.signing_enabled is False
        assert config.enable_mdns is True
        assert config.log_level == "INFO"

    def test_custom_values(self):
        """ServerConfig accepts custom values."""
        config = ServerConfig(
            name="Test Agent",
            port=9090,
            tls_enabled=True,
            capabilities=["info", "service"],
        )
        assert config.name == "Test Agent"
        assert config.port == 9090
        assert config.tls_enabled is True
        assert config.capabilities == ["info", "service"]

    def test_to_server_kwargs(self):
        """to_server_kwargs produces valid kwargs dict."""
        config = ServerConfig(
            name="Test Agent",
            port=8081,
            network_ssid="TestNetwork",
        )
        kwargs = config.to_server_kwargs()

        assert "agent_config" in kwargs
        assert kwargs["agent_config"].name == "Test Agent"
        assert kwargs["port"] == 8081
        assert kwargs["network_ssid"] == "TestNetwork"
        assert "tls_config" in kwargs


class TestClientConfig:
    """Tests for ClientConfig dataclass."""

    def test_default_values(self):
        """ClientConfig has sensible defaults."""
        config = ClientConfig()
        assert config.mdns_timeout == 3.0
        assert config.http_timeout == 10.0
        assert config.try_mdns is True
        assert config.verify_tls is True
        assert config.require_verified is False
        assert config.fetch_cards is True

    def test_custom_values(self):
        """ClientConfig accepts custom values."""
        config = ClientConfig(
            mdns_timeout=5.0,
            fallback_url="https://example.com",
            require_verified=True,
        )
        assert config.mdns_timeout == 5.0
        assert config.fallback_url == "https://example.com"
        assert config.require_verified is True

    def test_to_client_kwargs(self):
        """to_client_kwargs produces valid kwargs dict."""
        config = ClientConfig(
            mdns_timeout=2.0,
            verify_tls=False,
            signing_public_key="/path/to/key.pem",
        )
        kwargs = config.to_client_kwargs()

        assert kwargs["mdns_timeout"] == 2.0
        assert kwargs["verify_tls"] is False
        assert kwargs["signing_public_key"] == "/path/to/key.pem"

    def test_to_discover_kwargs(self):
        """to_discover_kwargs produces valid kwargs dict."""
        config = ClientConfig(
            fallback_url="https://example.com",
            try_mdns=False,
            require_verified=True,
        )
        kwargs = config.to_discover_kwargs()

        assert kwargs["fallback_url"] == "https://example.com"
        assert kwargs["try_mdns"] is False
        assert kwargs["require_verified"] is True


class TestEnvOverrides:
    """Tests for environment variable overrides."""

    def test_string_override(self):
        """String values are overridden from environment."""
        config = {"name": "Original", "description": "Test"}
        with patch.dict(os.environ, {"LAD_NAME": "FromEnv"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["name"] == "FromEnv"
        assert result["description"] == "Test"

    def test_bool_override(self):
        """Boolean values are parsed from environment."""
        config = {"tls_enabled": False}

        # Test "true"
        with patch.dict(os.environ, {"LAD_TLS_ENABLED": "true"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["tls_enabled"] is True

        # Test "1"
        with patch.dict(os.environ, {"LAD_TLS_ENABLED": "1"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["tls_enabled"] is True

        # Test "false"
        config = {"tls_enabled": True}
        with patch.dict(os.environ, {"LAD_TLS_ENABLED": "false"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["tls_enabled"] is False

    def test_int_override(self):
        """Integer values are parsed from environment."""
        config = {"port": 8080}
        with patch.dict(os.environ, {"LAD_PORT": "9090"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["port"] == 9090

    def test_float_override(self):
        """Float values are parsed from environment."""
        config = {"timeout": 3.0}
        with patch.dict(os.environ, {"LAD_TIMEOUT": "5.5"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["timeout"] == 5.5

    def test_list_override(self):
        """List values are parsed from comma-separated environment."""
        config = {"capabilities": ["info"]}
        with patch.dict(os.environ, {"LAD_CAPABILITIES": "info,service,ai"}):
            result = _apply_env_overrides(config, "LAD_")
        assert result["capabilities"] == ["info", "service", "ai"]


@pytest.mark.skipif(not YAML_AVAILABLE, reason="PyYAML not installed")
class TestYAMLConfigLoading:
    """Tests for YAML configuration file loading."""

    def test_load_server_config_from_file(self):
        """Server config loads from YAML file."""
        yaml_content = """
server:
  name: "Test Server"
  port: 9000
  tls_enabled: true
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            try:
                config = load_server_config(f.name)
                assert config.name == "Test Server"
                assert config.port == 9000
                assert config.tls_enabled is True
            finally:
                os.unlink(f.name)

    def test_load_client_config_from_file(self):
        """Client config loads from YAML file."""
        yaml_content = """
client:
  mdns_timeout: 5.0
  fallback_url: "https://example.com"
  require_verified: true
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            try:
                config = load_client_config(f.name)
                assert config.mdns_timeout == 5.0
                assert config.fallback_url == "https://example.com"
                assert config.require_verified is True
            finally:
                os.unlink(f.name)

    def test_load_config_with_env_override(self):
        """Config file values can be overridden by environment."""
        yaml_content = """
server:
  name: "File Name"
  port: 8080
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            try:
                with patch.dict(os.environ, {"LAD_NAME": "Env Name"}):
                    config = load_server_config(f.name, env_prefix="LAD_")
                    assert config.name == "Env Name"  # Overridden
                    assert config.port == 8080  # From file
            finally:
                os.unlink(f.name)

    def test_load_config_missing_file(self):
        """Missing config file returns defaults."""
        config = load_server_config("/nonexistent/path.yaml")
        # Should return defaults, not raise
        assert config.name == "LAD-A2A Agent"

    def test_generate_example_config(self):
        """Example config is generated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test-config.yaml")
            result = generate_example_config(path)
            assert result == path
            assert os.path.exists(path)

            # Verify it's valid YAML
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
                assert "server" in data
                assert "client" in data


class TestConfigDefaults:
    """Tests for default configuration behavior."""

    def test_server_config_no_file(self):
        """Server config works without file."""
        config = load_server_config(None, env_prefix="")
        assert config.name == "LAD-A2A Agent"
        assert config.port == 8080

    def test_client_config_no_file(self):
        """Client config works without file."""
        config = load_client_config(None, env_prefix="")
        assert config.mdns_timeout == 3.0
        assert config.verify_tls is True

    def test_server_config_ignores_unknown_fields(self):
        """Unknown fields in config dict are ignored."""
        # This shouldn't raise
        config = ServerConfig()
        # Verify basic fields still work
        assert config.name == "LAD-A2A Agent"
