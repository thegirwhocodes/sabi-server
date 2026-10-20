"""
Secrets loader for Sabi server.
Reads from Docker secrets (/run/secrets/) first, falls back to env vars.
"""

import os

SECRETS_DIR = "/run/secrets"


def get_secret(name: str, default: str = "") -> str:
    """
    Load a secret value. Priority:
    1. Docker secret file at /run/secrets/<name>
    2. Environment variable
    3. Default value
    """
    secret_path = os.path.join(SECRETS_DIR, name)
    try:
        with open(secret_path) as f:
            value = f.read().strip()
        # An empty secret file means "not set", not "set to blank". Oct 2026:
        # an empty ELEVENLABS_VOICE_ID file overrode the Bukola default and
        # every ElevenLabs request went to /text-to-speech/ with no voice (404).
        if value:
            return value
    except FileNotFoundError:
        pass
    return os.getenv(name) or default
