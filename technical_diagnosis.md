# 🔬 ТЕХНИЧЕСКАЯ ДИАГНОСТИКА: Залипающий Discord Overlay

## АНАЛИЗ ПРОБЛЕМЫ

### Симптомы указывают на:
1. **System Window Overlay** - панелька отображается поверх всех приложений
2. **Persistent UI State** - состояние сохраняется после перезагрузки
3. **System-level Hook** - перехватывает системные события

### Возможные причины:

#### 1. Discord Overlay Permission
- **Разрешение**: `SYSTEM_ALERT_WINDOW`
- **Проявление**: Floating UI поверх всех приложений
- **Решение**: Отозвать разрешение в настройках

#### 2. Accessibility Service Hijack
- **Механизм**: Accessibility service перехватывает UI события
- **Примеры**: Screen readers, auto-clickers, password managers
- **Диагностика**: Проверить активные accessibility services

#### 3. Floating Widget App
- **Источник**: Сторонние приложения (Facebook Messenger, WhatsApp, screen recorders)
- **Поведение**: Создают persistent overlay
- **Решение**: Отключить floating permissions

#### 4. System UI Glitch
- **Причина**: Коррупция System UI кэша
- **Проявление**: "Призрачные" UI элементы
- **Решение**: Очистка System UI кэша

#### 5. Malware/Adware
- **Поведение**: Persistent ads, fake overlays
- **Диагностика**: Безопасный режим, антивирус
- **Решение**: Полная очистка системы

## ДИАГНОСТИЧЕСКИЕ КОМАНДЫ (ADB)

### Проверка активных overlay:
```bash
adb shell dumpsys window | grep -E "(mHasSurface|mObscured)"
adb shell dumpsys window displays | grep -i overlay
```

### Анализ разрешений Discord:
```bash
adb shell dumpsys package com.discord | grep -A5 -B5 "SYSTEM_ALERT_WINDOW"
```

### Список accessibility services:
```bash
adb shell settings get secure enabled_accessibility_services
```

### Активные floating windows:
```bash
adb shell dumpsys window | grep -i "floating\|popup\|overlay"
```

## МЕТОДИКА ИСКЛЮЧЕНИЯ

### Шаг 1: Изоляция Discord
```bash
adb shell am force-stop com.discord
adb shell pm disable com.discord
# Проверить, исчезла ли панелька
adb shell pm enable com.discord
```

### Шаг 2: Проверка системных overlay
```bash
# Отключить все overlay permissions
adb shell appops set com.discord SYSTEM_ALERT_WINDOW deny
```

### Шаг 3: Accessibility services
```bash
# Получить список
adb shell settings get secure enabled_accessibility_services
# Временно отключить все
adb shell settings put secure enabled_accessibility_services ""
```

## ПРЕВЕНТИВНЫЙ МОНИТОРИНГ

### Регулярные проверки:
1. **Overlay permissions**: Раз в неделю проверять список приложений с SYSTEM_ALERT_WINDOW
2. **Accessibility services**: Мониторить новые подключенные службы
3. **System UI health**: Периодическая очистка кэша System UI

### Автоматизация (Tasker/MacroDroid):
```
IF новое приложение получает overlay permission
THEN уведомить пользователя
```

## ТЕХНИЧЕСКИЕ ДЕТАЛИ

### Android Overlay System:
- **WindowManager.LayoutParams.TYPE_SYSTEM_OVERLAY** (deprecated)
- **WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY** (API 26+)
- **Permission**: `android.permission.SYSTEM_ALERT_WINDOW`

### Жизненный цикл overlay:
1. App requests SYSTEM_ALERT_WINDOW permission
2. User grants permission in Settings
3. App creates WindowManager overlay
4. Overlay persists until explicitly removed

### Проблемные сценарии:
- App crash не удаляет overlay
- Permission revocation не всегда очищает активные overlay
- System UI cache corruption сохраняет "ghost" overlays

## RECOVERY STRATEGIES

### Level 1: Soft Reset
- Force stop app
- Clear app cache
- Revoke overlay permission

### Level 2: System Reset
- Clear System UI cache
- Restart WindowManager service
- Safe mode diagnosis

### Level 3: Hard Reset
- Factory reset
- Clean flash ROM
- Hardware replacement (если проблема в GPU)