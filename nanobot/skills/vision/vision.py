"""
Vision Skill - Computer vision and GUI automation for nanobot.

Requirements: pip install mss pyautogui Pillow litellm
"""

import base64
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import mss
    import pyautogui
    from PIL import Image
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

# Safety settings
if HAS_VISION:
    pyautogui.FAILSAFE = True  # Move to corner to abort
    pyautogui.PAUSE = 0.1

SCREENSHOTS_DIR = Path.home() / ".nanobot" / "screenshots"


def ensure_dir():
    """Ensure screenshots directory exists."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def capture_screenshot(output_path: Optional[Path] = None) -> Path:
    """
    Capture fullscreen screenshot.
    
    Args:
        output_path: Custom save path (optional)
    
    Returns:
        Path to saved screenshot
    """
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    
    ensure_dir()
    
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = SCREENSHOTS_DIR / f"screen_{timestamp}.png"
    
    with mss.mss() as sct:
        screenshot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.save(output_path)
    
    return output_path


def screenshot_to_base64() -> str:
    """
    Capture screenshot and return as base64 string for API.
    
    Returns:
        Base64 encoded PNG image
    """
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    
    with mss.mss() as sct:
        screenshot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()


def analyze_screenshot(prompt: str = "Что ты видишь на этом скриншоте? Опиши подробно.", model: Optional[str] = None, api_key: Optional[str] = None) -> str:
    """
    Capture screenshot and analyze with AI.
    
    Args:
        prompt: Question to ask about the screenshot
        model: LLM model (default: gemini/gemini-2.0-flash-thinking-exp or from config)
        api_key: API key (optional, uses env var)
    
    Returns:
        AI analysis of the screenshot
    
    Example:
        >>> analyze_screenshot("Есть ли здесь кнопка 'Отправить'?")
        'Да, в правом нижнем углу видна синяя кнопка с надписью "Отправить".'
    """
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")

    from nanobot.skills.vision.analyzer import analyze_screenshot as _analyze_screenshot
    from nanobot.skills.vision.analyzer import get_analyzer
    from loguru import logger

    result = _analyze_screenshot(prompt)
    provider = get_analyzer().get_provider()
    logger.info("Vision analyzer active provider: {}", provider)
    if result is None:
        return "❌ Ошибка анализа. Проверь ANTHROPIC_API_KEY или GEMINI_API_KEY и логи."
    return result


def vision_capture_and_analyze(query: str, model: Optional[str] = None) -> str:
    """
    Helper function: capture + analyze in one call.
    
    Args:
        query: What to ask about the screen
        model: Optional model override
    
    Returns:
        AI analysis result with screenshot path
    """
    path = capture_screenshot()
    analysis = analyze_screenshot(query, model)
    return f"📸 Скриншот: {path}\n\n🔍 Анализ:\n{analysis}"


def get_screen_size() -> tuple[int, int]:
    """Get screen resolution (width, height)."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    return pyautogui.size()


def get_mouse_position() -> tuple[int, int]:
    """Get current mouse position (x, y)."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    return pyautogui.position()


def move_mouse(x: int, y: int, duration: float = 0.5):
    """Move mouse to coordinates."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    pyautogui.moveTo(x, y, duration=duration)


def click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left"):
    """
    Click mouse button.
    
    Args:
        x, y: Coordinates (if None - current position)
        button: 'left', 'right', 'middle'
    """
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button)
    else:
        pyautogui.click(button=button)


def double_click(x: Optional[int] = None, y: Optional[int] = None):
    """Double click at position."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    
    if x is not None and y is not None:
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.doubleClick()


def type_text(text: str, interval: float = 0.01):
    """Type text with optional delay between keys."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    pyautogui.typewrite(text, interval=interval)


def press_key(key: str):
    """Press single key (e.g., 'enter', 'esc', 'tab')."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    pyautogui.press(key)


def hotkey(*keys: str):
    """
    Press key combination.
    
    Example: hotkey('ctrl', 'c'), hotkey('alt', 'tab')
    """
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    pyautogui.hotkey(*keys)


def sleep(seconds: float):
    """Pause execution."""
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    pyautogui.sleep(seconds)


def scroll(amount: int, x: Optional[int] = None, y: Optional[int] = None):
    """
    Scroll mouse wheel.
    
    Args:
        amount: Positive = up, negative = down
        x, y: Position to scroll at (optional)
    """
    if not HAS_VISION:
        raise ImportError("Install: pip install mss pyautogui Pillow")
    
    if x is not None and y is not None:
        pyautogui.scroll(amount, x, y)
    else:
        pyautogui.scroll(amount)


# Alias for convenience
capture = capture_screenshot
screenshot = capture_screenshot
