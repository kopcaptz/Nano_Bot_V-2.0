"""
Vision analyzer with fallback: Claude (anthropic) → Gemini (google) → None.

Providers are auto-detected via try/except on import.
Screenshots stored in ~/.nanobot/screenshots/
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import base64
import os
from pathlib import Path
from typing import Optional

from loguru import logger

# Provider priority: anthropic first, google as fallback
PROVIDER_PRIORITY = ["anthropic", "google"]

# Try importing Anthropic
try:
    from anthropic import Anthropic

    HAS_ANTHROPIC = True
except ImportError:
    Anthropic = None  # type: ignore[assignment]
    HAS_ANTHROPIC = False

# Try importing Google Generative AI
try:
    import google.generativeai as genai

    HAS_GOOGLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    HAS_GOOGLE = False

CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
GEMINI_MODEL = "gemini-1.5-flash"

_analyzer_instance: Optional["VisionAnalyzer"] = None


class VisionAnalyzer:
    """
    Analyze screenshots/images with fallback: Claude → Gemini.

    Auto-detects available clients from API keys in environment.
    """

    def __init__(
        self,
        anthropic_key: Optional[str] = None,
        google_key: Optional[str] = None,
    ):
        self._anthropic_client = None
        self._google_configured = False
        self._active_provider: Optional[str] = None

        anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        google_key = google_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        # Configure Google for fallback (even when Anthropic is primary)
        if HAS_GOOGLE and google_key and google_key.strip():
            try:
                genai.configure(api_key=google_key.strip())
                self._google_configured = True
            except Exception as e:
                logger.warning("Failed to configure Gemini: {}", e)

        # Initialize Anthropic (priority)
        if HAS_ANTHROPIC and anthropic_key and anthropic_key.strip():
            try:
                self._anthropic_client = Anthropic(api_key=anthropic_key.strip())
                self._active_provider = "anthropic"
            except Exception as e:
                logger.warning("Failed to init Anthropic client: {}", e)

        # Fallback to Google if Anthropic not available
        if self._active_provider is None and self._google_configured:
            self._active_provider = "google"

    def get_provider(self) -> Optional[str]:
        """Return active provider: 'anthropic', 'google', or None."""
        return self._active_provider

    @staticmethod
    def _media_type(image_path: Path) -> Optional[str]:
        ext = image_path.suffix.lower()
        if ext == ".png":
            return "image/png"
        if ext in {".jpg", ".jpeg"}:
            return "image/jpeg"
        return None

    def analyze(self, image_path: str | Path, prompt: str) -> Optional[str]:
        """
        Analyze the image with active provider. Fallback: Claude fails → try Gemini.

        Returns None if no provider available or all fail.
        """
        path = Path(image_path)
        media_type = self._media_type(path)

        if not path.exists():
            logger.error("Image file does not exist: {}", path)
            return None
        if media_type is None:
            logger.error("Unsupported image format for {}. Supported: PNG, JPG, JPEG", path)
            return None

        if self._active_provider is None:
            logger.error("No vision provider available. Set ANTHROPIC_API_KEY or GEMINI_API_KEY")
            return None

        image_base64 = base64.b64encode(path.read_bytes()).decode("utf-8")

        # Build provider order: Claude first (if available), then Gemini as fallback
        order = []
        if self._anthropic_client is not None:
            order.append(("anthropic", self._analyze_with_claude))
        if HAS_GOOGLE and self._google_configured:
            order.append(("google", self._analyze_with_gemini))

        for name, analyzer_fn in order:
            try:
                result = analyzer_fn(path, media_type, image_base64, prompt)
                if result:
                    logger.info("Vision analysis done via provider: {}", name)
                    return result
            except Exception as e:
                logger.warning("Provider {} failed: {}", name, e)
                continue

        logger.error("All vision providers failed for {}", path)
        return None

    def _analyze_with_claude(
        self, path: Path, media_type: str, image_base64: str, prompt: str
    ) -> Optional[str]:
        """Analyze via Anthropic Claude."""
        if self._anthropic_client is None:
            return None
        response = self._anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text_chunks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        result = "\n".join(text_chunks).strip()
        return result if result else None

    def _analyze_with_gemini(
        self, path: Path, media_type: str, image_base64: str, prompt: str
    ) -> Optional[str]:
        """Analyze via Google Gemini (fallback)."""
        if not HAS_GOOGLE:
            return None
        model = genai.GenerativeModel(GEMINI_MODEL)
        content = [
            {
                "inline_data": {
                    "mime_type": media_type,
                    "data": image_base64,
                }
            },
            prompt,
        ]
        response = model.generate_content(content)
        if response.text:
            return response.text.strip()
        return None


def get_analyzer() -> VisionAnalyzer:
    """Get singleton analyzer. Initializes from ANTHROPIC_API_KEY, GEMINI_API_KEY."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = VisionAnalyzer()
    return _analyzer_instance


def analyze_screenshot(
    prompt: str = "Что ты видишь на этом скриншоте? Опиши подробно.",
) -> Optional[str]:
    """Capture screenshot and analyze with active provider (Claude → Gemini fallback)."""
    try:
        from nanobot.skills.vision.vision import capture_screenshot

        screenshot_path = capture_screenshot()
        return get_analyzer().analyze(screenshot_path, prompt)
    except Exception:
        logger.exception("Failed to capture or analyze screenshot")
        return None
