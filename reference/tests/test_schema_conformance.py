"""
Validate the reference server's output against the published JSON Schemas.

This is the check spec section 6.2 mandates for clients and keeps the schema,
the prose, and the reference server from drifting apart (audit finding #19).
"""

import json
import os

import pytest

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from server.lad_server import LADServer, AgentConfig, TLSConfig

jsonschema = pytest.importorskip("jsonschema")

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "spec", "schemas")


def _load(name):
    with open(os.path.join(SCHEMA_DIR, name)) as f:
        return json.load(f)


def _tls_server(**kw):
    # Enable the TLS *scheme* (https URLs) without needing real certs, so the
    # emitted agent_card_url satisfies the schema's https-only requirement.
    return LADServer(
        agent_config=AgentConfig(
            name="Grand Hotel Concierge", description="AI concierge",
            role="hotel-concierge", capabilities_preview=["info", "dining"],
        ),
        network_realm="grandhotel.com",
        enable_mdns=False,
        tls_config=TLSConfig(enabled=True, certfile="x", keyfile="y"),
        **kw,
    )


def test_discovery_response_conforms_to_schema():
    server = _tls_server()
    resp = server.get_discovery_response()
    jsonschema.validate(resp, _load("discovery-response.json"))
    # The reference emits a did:web identity key when it has a verifiable domain.
    assert resp["agents"][0]["id"].startswith("did:web:grandhotel.com")
    assert resp["version"] == "0.2"


def test_plaintext_card_url_is_rejected_by_schema():
    # A non-TLS server emits http:// card URLs, which the schema must reject.
    server = LADServer(
        agent_config=AgentConfig(
            name="Dev", description="d", role="r", capabilities_preview=["info"],
        ),
        network_realm="grandhotel.com",
        enable_mdns=False,
    )
    resp = server.get_discovery_response()
    assert resp["agents"][0]["agent_card_url"].startswith("http://")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(resp, _load("discovery-response.json"))
