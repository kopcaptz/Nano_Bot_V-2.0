#!/usr/bin/env python3
"""
Простой тест скриншотов + Vision AI
Запуск: python test_vision.py
"""
import os
import base64
from pathlib import Path

def test_screenshot():
    print("📸 Тест скриншотов...")
    
    try:
        import mss
        import pyautogui
        print("✅ mss и pyautogui найдены")
    except ImportError as e:
        print(f"❌ Нужно установить: pip install mss pyautogui Pillow")
        return
    
    # Скриншот
    output_dir = Path.home() / ".nanobot" / "screenshots"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = output_dir / f"test_{timestamp}.png"
    
    try:
        # Делаем скриншот
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Главный монитор
            img = sct.grab(monitor)
            from PIL import Image
            img_pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            img_pil.save(str(screenshot_path))
        
        print(f"✅ Скриншот сохранён: {screenshot_path}")
        
        # Показываем base64 для теста (обрезаем для читаемости)
        with open(screenshot_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()[:100] + "..."
        print(f"📎 Base64 (первые 100 символов): {img_base64}")
        
        print("\n🎉 Тест пройден! Теперь можно отправлять скриншоты в Claude Vision.")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_screenshot()
