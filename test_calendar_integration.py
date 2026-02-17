"""
Тестирование Google Calendar интеграции в Nano Bot V-2.0

Проверяет:
1. SmitheryBridge базовую функциональность
2. Handler календарные функции
3. LLM Router системный промпт
4. End-to-end интеграцию
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.smithery_bridge import SmitheryBridge
from src.core.handler import CommandHandler
from src.core.llm_router import LLMRouter
from src.core.memory import CrystalMemory
from src.core.event_bus import EventBus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CalendarIntegrationTester:
    """Тестер интеграции Google Calendar"""
    
    def __init__(self):
        self.bridge = SmitheryBridge(timeout=30)
        self.results = []
        
    def log_test(self, name: str, status: str, details: str = ""):
        """Logirovanie rezultata testa"""
        result = {
            "test": name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        
        icon = "[OK]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[WARN]"
        logger.info(f"{icon} {name}: {status}")
        if details:
            logger.info(f"   -> {details}")
    
    async def test_1_smithery_cli_available(self):
        """Тест 1: Проверка доступности Smithery CLI"""
        try:
            path = self.bridge._get_smithery_path()
            self.log_test(
                "Smithery CLI доступность",
                "PASS",
                f"Найден: {path}"
            )
            return True
        except FileNotFoundError as e:
            self.log_test(
                "Smithery CLI доступность",
                "FAIL",
                str(e)
            )
            return False
    
    async def test_2_list_tools(self):
        """Тест 2: Получение списка инструментов Google Calendar"""
        try:
            # Используем правильное имя сервера из вашей конфигурации
            tools = await self.bridge.list_tools(
                server="googlecalendar-kMHR",
                limit=50
            )
            
            if isinstance(tools, dict) and tools.get("isError"):
                self.log_test(
                    "Список инструментов Calendar",
                    "WARN",
                    f"Ошибка: {tools.get('error')}"
                )
                return False
            
            tool_count = len(tools) if isinstance(tools, list) else 0
            tool_names = [t.get("name", "unknown") for t in tools[:5]] if isinstance(tools, list) else []
            
            self.log_test(
                "Список инструментов Calendar",
                "PASS",
                f"Найдено {tool_count} инструментов. Примеры: {', '.join(tool_names)}"
            )
            return True
            
        except Exception as e:
            self.log_test(
                "Список инструментов Calendar",
                "FAIL",
                f"Исключение: {e}"
            )
            return False
    
    async def test_3_call_events_list(self):
        """Тест 3: Вызов events_list для получения событий"""
        try:
            # Диапазон: завтра
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            time_min = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            time_max = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
            
            result = await self.bridge.call_tool(
                server="googlecalendar-kMHR",
                tool_name="events_list",
                params={
                    "calendarId": "primary",
                    "timeMin": time_min.isoformat(),
                    "timeMax": time_max.isoformat(),
                    "maxResults": 10
                }
            )
            
            if isinstance(result, dict) and result.get("isError"):
                self.log_test(
                    "Вызов events_list",
                    "WARN",
                    f"Ошибка: {result.get('error')}"
                )
                return False
            
            # Проверяем структуру ответа
            if isinstance(result, dict):
                events = result.get("items", [])
                self.log_test(
                    "Вызов events_list",
                    "PASS",
                    f"Получено {len(events)} событий на завтра"
                )
                return True
            elif isinstance(result, list):
                self.log_test(
                    "Вызов events_list",
                    "PASS",
                    f"Получено {len(result)} событий на завтра"
                )
                return True
            else:
                self.log_test(
                    "Вызов events_list",
                    "WARN",
                    f"Неожиданный формат ответа: {type(result)}"
                )
                return False
                
        except Exception as e:
            self.log_test(
                "Вызов events_list",
                "FAIL",
                f"Исключение: {e}"
            )
            return False
    
    async def test_4_handler_calendar_regex(self):
        """Тест 4: Проверка регулярных выражений Handler для календаря"""
        try:
            # Создаём минимальный Handler для тестирования regex
            event_bus = EventBus()
            memory = CrystalMemory(max_messages_per_chat=50)
            
            # Создаём LLMRouter с фиктивными данными (не будем вызывать API)
            llm_router = LLMRouter(
                api_key="test",
                model="test",
                request_timeout_seconds=30
            )
            
            handler = CommandHandler(
                event_bus=event_bus,
                llm_router=llm_router,
                memory=memory
            )
            
            # Тестируем regex паттерны
            test_cases = [
                ("[ACTION:CALENDAR_LIST]", "CALENDAR_LIST", True),
                ("[ACTION:CALENDAR_CREATE] {\"summary\":\"Test\"}", "CALENDAR_CREATE", True),
                ("[ACTION:CALENDAR_UPDATE] {\"eventId\":\"123\"}", "CALENDAR_UPDATE", True),
                ("[ACTION:CALENDAR_DELETE] {\"eventId\":\"123\"}", "CALENDAR_DELETE", True),
            ]
            
            passed = 0
            for text, action_type, should_match in test_cases:
                if action_type == "CALENDAR_LIST":
                    match = handler._RE_CALENDAR_LIST.search(text)
                elif action_type == "CALENDAR_CREATE":
                    match = handler._RE_CALENDAR_CREATE.search(text)
                elif action_type == "CALENDAR_UPDATE":
                    match = handler._RE_CALENDAR_UPDATE.search(text)
                elif action_type == "CALENDAR_DELETE":
                    match = handler._RE_CALENDAR_DELETE.search(text)
                else:
                    match = None
                
                if bool(match) == should_match:
                    passed += 1
            
            self.log_test(
                "Handler календарные regex",
                "PASS" if passed == len(test_cases) else "FAIL",
                f"Прошло {passed}/{len(test_cases)} тестов"
            )
            return passed == len(test_cases)
            
        except Exception as e:
            self.log_test(
                "Handler календарные regex",
                "FAIL",
                f"Исключение: {e}"
            )
            return False
    
    async def test_5_handler_time_range_resolver(self):
        """Тест 5: Проверка разрешения относительных дат в Handler"""
        try:
            event_bus = EventBus()
            memory = CrystalMemory(max_messages_per_chat=50)
            llm_router = LLMRouter(api_key="test", model="test")
            
            handler = CommandHandler(
                event_bus=event_bus,
                llm_router=llm_router,
                memory=memory
            )
            
            # Тестируем распознавание дат
            test_cases = [
                ("Что у меня завтра?", "завтра"),
                ("What's tomorrow on my calendar?", "tomorrow"),
                ("Что послезавтра?", "послезавтра"),
                ("Events for today", "сегодня/today"),
            ]
            
            passed = 0
            for command, expected_hint in test_cases:
                params = handler._resolve_calendar_time_range(command, None)
                if params and "timeMin" in params and "timeMax" in params:
                    passed += 1
            
            self.log_test(
                "Handler разрешение дат",
                "PASS" if passed == len(test_cases) else "FAIL",
                f"Распознано {passed}/{len(test_cases)} относительных дат"
            )
            return passed == len(test_cases)
            
        except Exception as e:
            self.log_test(
                "Handler разрешение дат",
                "FAIL",
                f"Исключение: {e}"
            )
            return False
    
    async def test_6_llm_router_system_prompt(self):
        """Тест 6: Проверка системного промпта LLM Router"""
        try:
            llm_router = LLMRouter(
                api_key="test",
                model="test"
            )
            
            # Строим сообщения для проверки промпта
            messages = llm_router._build_messages(
                command="Что у меня завтра?",
                context=[]
            )
            
            system_message = messages[0]
            system_content = system_message.get("content", "")
            
            # Проверяем наличие календарных инструкций
            checks = [
                ("CALENDAR TOOLS" in system_content, "Секция CALENDAR TOOLS"),
                ("[ACTION:CALENDAR_LIST]" in system_content, "Тег CALENDAR_LIST"),
                ("[ACTION:CALENDAR_CREATE" in system_content, "Тег CALENDAR_CREATE"),
                ("[ACTION:CALENDAR_UPDATE" in system_content, "Тег CALENDAR_UPDATE"),
                ("[ACTION:CALENDAR_DELETE" in system_content, "Тег CALENDAR_DELETE"),
                ("[CALENDAR_DATA_READONLY]" in system_content, "Тег CALENDAR_DATA_READONLY"),
            ]
            
            passed = sum(1 for check, _ in checks if check)
            failed_checks = [name for check, name in checks if not check]
            
            self.log_test(
                "LLM Router системный промпт",
                "PASS" if passed == len(checks) else "WARN",
                f"Найдено {passed}/{len(checks)} элементов. Отсутствует: {', '.join(failed_checks) if failed_checks else 'нет'}"
            )
            return passed == len(checks)
            
        except Exception as e:
            self.log_test(
                "LLM Router системный промпт",
                "FAIL",
                f"Исключение: {e}"
            )
            return False
    
    def print_summary(self):
        """Vyvod itogovoy svodki"""
        print("\n" + "="*70)
        print("ITOGOVAYA SVODKA TESTIROVANIYA")
        print("="*70)
        
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        warned = sum(1 for r in self.results if r["status"] == "WARN")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        total = len(self.results)
        
        print(f"\n[OK] Uspeshno: {passed}/{total}")
        print(f"[WARN] Preduprezhdeniya: {warned}/{total}")
        print(f"[FAIL] Oshibki: {failed}/{total}")
        
        print("\n" + "-"*70)
        print("DETALI TESTOV:")
        print("-"*70)
        
        for r in self.results:
            icon = "[OK]" if r["status"] == "PASS" else "[FAIL]" if r["status"] == "FAIL" else "[WARN]"
            print(f"\n{icon} {r['test']}")
            print(f"   Status: {r['status']}")
            if r["details"]:
                print(f"   Detali: {r['details']}")
        
        print("\n" + "="*70)
        
        # Itogovaya ocenka
        if failed == 0 and warned == 0:
            print("VSE TESTY PROYDENY! Integraciya rabotaet otlichno!")
        elif failed == 0:
            print("BAZOVAYA FUNKCIONALNOST RABOTAET (est preduprezhdeniya)")
        else:
            print("EST KRITICHESKIE OSHIBKI - trebuetsya ispravlenie")
        
        print("="*70 + "\n")


async def main():
    """Главная функция тестирования"""
    print("\n" + "="*70)
    print("TESTIROVANIE GOOGLE CALENDAR INTEGRACII")
    print("="*70)
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proekt: Nano Bot V-2.0")
    print("="*70 + "\n")
    
    tester = CalendarIntegrationTester()
    
    # Zapuskaem testy po poryadku
    print("Zapusk testov...\n")
    
    await tester.test_1_smithery_cli_available()
    await tester.test_2_list_tools()
    await tester.test_3_call_events_list()
    await tester.test_4_handler_calendar_regex()
    await tester.test_5_handler_time_range_resolver()
    await tester.test_6_llm_router_system_prompt()
    
    # Выводим итоговую сводку
    tester.print_summary()
    
    # Sohranyaem rezultaty v JSON
    results_file = project_root / "test_results_calendar.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(tester.results, f, indent=2, ensure_ascii=False)
    
    print(f"Rezultaty sohraneny v: {results_file}\n")


if __name__ == "__main__":
    asyncio.run(main())
