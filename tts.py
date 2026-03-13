"""
Text-to-Speech using YarnGPT API (Nigerian voices).
Primary TTS for Sabi — 16 Nigerian-accented voices.
"""

import logging

import httpx

from secret_loader import get_secret

logger = logging.getLogger("sabi.tts")

# Voice names must be capitalized (API requirement)
YARNGPT_VOICES = {
    "chinenye": "Chinenye",   # Engaging, warm — primary
    "wura": "Wura",           # Young, sweet
    "adaora": "Adaora",       # Warm, engaging
    "idera": "Idera",         # Melodic, gentle
}

YARNGPT_API_URL = "https://yarngpt.ai/api/v1/tts"
DEFAULT_VOICE = YARNGPT_VOICES["chinenye"]


class TextToSpeech:
    def __init__(self, voice: str = "chinenye"):
        """
        Initialize YarnGPT TTS.

        Args:
            voice: Voice key from YARNGPT_VOICES.
        """
        self.api_key = get_secret("YARNGPT_API_KEY")
        self.voice = YARNGPT_VOICES.get(voice, DEFAULT_VOICE)
        self.client = httpx.Client(timeout=30.0)

        if not self.api_key:
            logger.warning("YARNGPT_API_KEY not set. TTS will fail.")
        else:
            logger.info(f"YarnGPT TTS ready (voice={self.voice}).")

    def synthesize(self, text: str, output_path: str) -> str:
        """
        Convert text to speech audio file via YarnGPT API.

        Args:
            text: Text to speak (max 2000 chars)
            output_path: Path to save audio file

        Returns:
            Path to generated audio file
        """
        if not self.api_key:
            raise RuntimeError("YARNGPT_API_KEY not configured")

        clean_text = (
            text
            .replace("₦", "naira ")
            .replace("  ", " ")
            .strip()
        )

        if len(clean_text) > 2000:
            logger.warning(f"Text exceeds 2000 char limit ({len(clean_text)}), truncating")
            clean_text = clean_text[:2000]

        response = self.client.post(
            YARNGPT_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "text": clean_text,
                "voice": self.voice,
                "response_format": "mp3",
            },
        )

        if not response.is_success:
            logger.error(f"YarnGPT error: {response.status_code} {response.text}")
            raise RuntimeError(f"YarnGPT TTS failed: {response.status_code}")

        with open(output_path, "wb") as f:
            f.write(response.content)

        return output_path
