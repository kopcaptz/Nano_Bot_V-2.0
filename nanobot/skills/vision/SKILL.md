---
name: vision
description: Computer vision - screenshots, screen analysis, and GUI automation via pyautogui.
metadata: {"nanobot":{"emoji":"👁️","requires":{"python":["mss","pyautogui","Pillow","anthropic","google-generativeai"]}}}
---

# Vision

Control computer via screenshots and GUI automation.

## Fallback Architecture

Vision Analyzer использует цепочку провайдеров: **Claude → Gemini → None**.

- **Claude (anthropic)** — приоритетный провайдер, модель `claude-3-5-sonnet-20241022`
- **Gemini (google)** — fallback при недоступности Claude или ошибке
- **None** — если оба провайдера недоступны

Screenshots сохраняются в `~/.nanobot/screenshots/`.

## Requirements

```bash
pip install mss pyautogui Pillow anthropic google-generativeai
```

### Переменные окружения

| Переменная        | Роль     | Приоритет |
|-------------------|----------|-----------|
| `ANTHROPIC_API_KEY` | Claude   | Основной  |
| `GEMINI_API_KEY`   | Gemini   | Fallback  |

Копируйте `.env.example` в `.env` и укажите ключи.

## Commands

### Screenshot + AI Analysis 👁️

**"/vision что на экране?"** — Сделать скриншот и проанализировать:

```python
from nanobot.skills.vision import vision

# Простой анализ
result = vision.analyze_screenshot()
print(result)  # AI описывает что видит

# Конкретный вопрос
result = vision.analyze_screenshot("Где кнопка 'Сохранить'? Дай координаты.")

# Двухшаговый процесс
path = vision.capture_screenshot()  # Снимок
analysis = vision.analyze_screenshot("Есть ли ошибки?")  # Анализ
```

**Команды для пользователя:**
- `/vision что на экране?` — Общий анализ
- `/vision где кнопка "X"?` — Поиск элемента
- `/vision есть ли ошибки?` — Проверка на ошибки
- `/vision прочитай текст` — OCR альтернатива

### Провайдеры

| Провайдер | Модель | Переменная окружения |
|-----------|--------|----------------------|
| **Claude** (приоритет) | claude-3-5-sonnet-20241022 | `ANTHROPIC_API_KEY` |
| **Gemini** (fallback) | gemini-1.5-flash | `GEMINI_API_KEY` |

### Vision Analyzer API

```python
from nanobot.skills.vision.analyzer import VisionAnalyzer, analyze_screenshot, get_analyzer

# Singleton analyzer (читает ключи из env)
analyzer = get_analyzer()
print(analyzer.get_provider())  # "anthropic" или "google" или None

# Анализ существующего файла
text = analyzer.analyze("C:/tmp/screen.png", "Опиши интерфейс и найди ошибки")

# Быстрый вызов: скриншот + анализ
quick = analyze_screenshot("Есть ли на экране кнопка 'Сохранить'?")
print(quick)
```

### Mouse Control
```python
# Move mouse to coordinates
pyautogui.moveTo(100, 200, duration=0.5)

# Click
pyautogui.click(100, 200)
pyautogui.rightClick(100, 200)
pyautogui.doubleClick(100, 200)

# Drag
pyautogui.dragTo(300, 400, duration=1)
```

### Keyboard
```python
# Type text
pyautogui.typewrite("Hello World", interval=0.01)

# Press keys
pyautogui.press('enter')
pyautogui.hotkey('ctrl', 'c')
pyautogui.hotkey('alt', 'tab')
```

### Screen Info
```python
# Get screen size
width, height = pyautogui.size()  # (1920, 1080)

# Get mouse position
x, y = pyautogui.position()

# Take screenshot
import mss
with mss.mss() as sct:
    screenshot = sct.grab(sct.monitors[1])
```

## Examples

**"What's on my screen?"**
```python
vision_capture_and_analyze("Describe what you see on the screen")
```

**"Open Chrome and go to gmail"**
```python
# Find Chrome icon and click
pyautogui.click(100, 100)  # Chrome position
pyautogui.sleep(1)
pyautogui.click(500, 50)   # Address bar
pyautogui.typewrite("gmail.com")
pyautogui.press('enter')
```

**"Watch for errors"**
```python
# Capture every 5 seconds and check for "Error" text
while True:
    img = vision_capture()
    if "error" in vision_ocr(img).lower():
        send_telegram("Error detected!")
    pyautogui.sleep(5)
```

## Safety

- Always add `duration` to mouse movements
- Use `pyautogui.FAILSAFE = True` (move to corner to abort)
- Confirm before destructive actions
- Screenshots saved to `~/.nanobot/screenshots/`
