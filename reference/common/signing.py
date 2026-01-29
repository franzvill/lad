"""
AgentCard Signing and Verification

Implements JWS-based signing for AgentCards per LAD-A2A spec section 4.2.

Usage:
    # Generate keys (one-time setup)
    from common.signing import generate_signing_keys
    generate_signing_keys("keys/")

    # Server-side: Sign AgentCard
    from common.signing import SigningConfig, sign_agent_card
    config = SigningConfig(private_key_path="keys/private.pem")
    signed_card = sign_agent_card(agent_card, config)

    # Client-side: Verify AgentCard
    from common.signing import verify_agent_card
    result = verify_agent_card(signed_card, public_key_pem=public_key)
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger("lad_a2a.signing")


@dataclass
class SigningConfig:
    """Configuration for AgentCard signing."""
    enabled: bool = False
    private_key_path: Optional[str] = None
    key_id: Optional[str] = None  # "kid" header for key identification
    algorithm: str = "ES256"  # ECDSA with P-256 and SHA-256

    def validate(self) -> bool:
        """Validate signing configuration."""
        if not self.enabled:
            return True
        if not self.private_key_path:
            logger.error("Signing enabled but private_key_path not provided")
            return False
        if not os.path.exists(self.private_key_path):
            logger.error(f"Private key file not found: {self.private_key_path}")
            return False
        return True


@dataclass
class VerificationResult:
    """Result of AgentCard signature verification."""
    valid: bool
    agent_card: Optional[dict] = None
    error: Optional[str] = None
    signed_at: Optional[datetime] = None
    key_id: Optional[str] = None


def generate_signing_keys(
    output_dir: str,
    private_key_name: str = "private.pem",
    public_key_name: str = "public.pem",
) -> tuple[str, str]:
    """Generate a new ECDSA P-256 key pair for AgentCard signing.

    Args:
        output_dir: Directory to write keys to.
        private_key_name: Filename for private key.
        public_key_name: Filename for public key.

    Returns:
        Tuple of (private_key_path, public_key_path).

    Example:
        private_path, public_path = generate_signing_keys("keys/")
    """
    os.makedirs(output_dir, exist_ok=True)

    # Generate ECDSA P-256 key pair
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    # Serialize private key
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize public key
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_key_path = os.path.join(output_dir, private_key_name)
    public_key_path = os.path.join(output_dir, public_key_name)

    with open(private_key_path, "wb") as f:
        f.write(private_key_pem)
    os.chmod(private_key_path, 0o600)  # Restrict private key permissions

    with open(public_key_path, "wb") as f:
        f.write(public_key_pem)

    logger.info(f"Generated signing keys: {private_key_path}, {public_key_path}")
    return private_key_path, public_key_path


def load_private_key(path: str) -> bytes:
    """Load a private key from a PEM file."""
    with open(path, "rb") as f:
        return f.read()


def load_public_key(path: str) -> bytes:
    """Load a public key from a PEM file."""
    with open(path, "rb") as f:
        return f.read()


def sign_agent_card(
    agent_card: dict,
    config: SigningConfig,
) -> str:
    """Sign an AgentCard and return a JWS token.

    The AgentCard is embedded as the JWT payload with additional claims:
    - iat: Issued at timestamp
    - agent_card: The original AgentCard

    Args:
        agent_card: The AgentCard dictionary to sign.
        config: Signing configuration with private key.

    Returns:
        A JWS token (compact serialization) containing the signed AgentCard.

    Raises:
        ValueError: If signing configuration is invalid.
    """
    if not config.enabled:
        raise ValueError("Signing is not enabled")

    if not config.validate():
        raise ValueError("Invalid signing configuration")

    private_key_pem = load_private_key(config.private_key_path)

    # Build payload with AgentCard and metadata
    payload = {
        "agent_card": agent_card,
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }

    # Build headers
    headers = {}
    if config.key_id:
        headers["kid"] = config.key_id

    # Sign with ES256
    token = jwt.encode(
        payload,
        private_key_pem,
        algorithm=config.algorithm,
        headers=headers if headers else None,
    )

    logger.debug(f"Signed AgentCard for {agent_card.get('name', 'unknown')}")
    return token


def verify_agent_card(
    token: str,
    public_key_pem: Optional[bytes] = None,
    public_key_path: Optional[str] = None,
    algorithms: list[str] = None,
) -> VerificationResult:
    """Verify a signed AgentCard JWS token.

    Args:
        token: The JWS token to verify.
        public_key_pem: Public key as PEM bytes.
        public_key_path: Path to public key PEM file (alternative to public_key_pem).
        algorithms: Allowed signing algorithms (default: ["ES256"]).

    Returns:
        VerificationResult with verification status and extracted AgentCard.
    """
    if algorithms is None:
        algorithms = ["ES256"]

    if public_key_path and not public_key_pem:
        public_key_pem = load_public_key(public_key_path)

    if not public_key_pem:
        return VerificationResult(
            valid=False,
            error="No public key provided for verification",
        )

    try:
        # Decode and verify
        payload = jwt.decode(
            token,
            public_key_pem,
            algorithms=algorithms,
        )

        # Extract metadata
        headers = jwt.get_unverified_header(token)

        # Parse issued-at timestamp
        signed_at = None
        if "iat" in payload:
            signed_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)

        return VerificationResult(
            valid=True,
            agent_card=payload.get("agent_card"),
            signed_at=signed_at,
            key_id=headers.get("kid"),
        )

    except jwt.ExpiredSignatureError:
        return VerificationResult(valid=False, error="Token has expired")
    except jwt.InvalidSignatureError:
        return VerificationResult(valid=False, error="Invalid signature")
    except jwt.DecodeError as e:
        return VerificationResult(valid=False, error=f"Failed to decode token: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during verification: {e}")
        return VerificationResult(valid=False, error=f"Verification failed: {e}")


def is_signed_agent_card(data: str | dict) -> bool:
    """Check if the data appears to be a signed AgentCard (JWS token).

    Args:
        data: Either a JWS token string or a plain AgentCard dict.

    Returns:
        True if the data is a JWS token, False if it's a plain dict.
    """
    if isinstance(data, dict):
        return False
    if isinstance(data, str):
        # JWS tokens have 3 parts separated by dots
        parts = data.split(".")
        return len(parts) == 3
    return False
