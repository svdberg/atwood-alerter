#!/usr/bin/env python3
"""
Generate VAPID keys for web push notifications.
"""

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_vapid_keys():
    """Generate VAPID key pair for web push notifications."""

    # Generate a private key
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # Get the public key
    public_key = private_key.public_key()
    # Serialize private key
    private_key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key (uncompressed format for VAPID)
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    # Base64 URL-safe encode (without padding)
    private_key_b64 = base64.urlsafe_b64encode(
        private_key_bytes
    ).decode('utf-8').rstrip('=')
    public_key_b64 = base64.urlsafe_b64encode(
        public_key_bytes
    ).decode('utf-8').rstrip('=')
    return {
        'private_key': private_key_b64,
        'public_key': public_key_b64
    }


def main():
    """Generate and display VAPID keys."""
    print("🔑 Generating VAPID keys for web push notifications...")
    print("")

    keys = generate_vapid_keys()

    print("✅ VAPID keys generated successfully!")
    print("")
    print("📋 Keys (save these securely):")
    print("=" * 50)
    print(f"Public Key:  {keys['public_key']}")
    print(f"Private Key: {keys['private_key']}")
    print("=" * 50)
    print("")
    print("🔐 These keys will be stored in AWS SSM Parameter Store")
    print("📝 The public key will also be added to your frontend configuration")

    return keys


if __name__ == "__main__":
    main()
