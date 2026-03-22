"""
Orchestrator/Client - терминальный клиент для A2A/MPC системы.

Запускается из терминала, принимает запросы на естественном языке,
использует MPC Server для discovery агентов, и направляет задачи
напрямую найденным агентам.
"""

import asyncio
import json
import hashlib
import re
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from models import MPCQuery

try:
    from llm import create_llm_client

    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False


class A2AOrchestrator:
    """
    Orchestrator - координирует взаимодействие клиента с A2A агентами.

    Отвечает за:
    1. Парсинг естественного языка → intent + entities
    2. MPC-style discovery запрос к серверу
    3. Маршрутизация задач найденным агентам
    4. Формирование ответа для пользователя
    """

    def __init__(self, mpc_host: str = "localhost", mpc_port: int = 9000):
        self.mpc_host = mpc_host
        self.mpc_port = mpc_port

        self.llm_client = None
        if LLM_AVAILABLE and os.getenv("API_KEY"):
            try:
                self.llm_client = create_llm_client()
                print("[Orchestrator] LLM parsing enabled")
            except Exception as e:
                print(f"[Orchestrator] LLM not available: {e}")

        self.intent_keywords = {
            "weather": [
                "weather",
                "погода",
                "temperature",
                "температура",
                "forecast",
                "дождь",
                "sunny",
            ],
            "finance": [
                "stock",
                "акции",
                "finance",
                "финансы",
                "price",
                "цена",
                "market",
            ],
        }

        self.entity_patterns = {
            "location": r"(?:в|at|in)\s+([A-Za-zА-Яа-яёЁ\s]+?)(?:\s+\d|\s+г|$|\?)",
            "symbol": r"\b([A-Z]{2,5})\b",
        }

    def _hash_keyword(self, keyword: str) -> str:
        """Хеширование ключевого слова для MPC запроса."""
        return hashlib.sha256(keyword.lower().encode()).hexdigest()[:16]

    def _parse_rule_based(self, text: str) -> dict:
        """Rule-based parsing fallback."""
        text_lower = text.lower()

        intent = "unknown"
        for intent_name, keywords in self.intent_keywords.items():
            if any(kw in text_lower for kw in keywords):
                intent = intent_name
                break

        entities = {}
        location_match = re.search(
            self.entity_patterns["location"], text, re.IGNORECASE
        )
        if location_match:
            entities["location"] = location_match.group(1).strip()

        symbol_match = re.search(self.entity_patterns["symbol"], text)
        if symbol_match:
            entities["symbol"] = symbol_match.group(1)

        return {
            "intent": intent,
            "entities": entities,
        }

    def parse_request(self, text: str) -> dict:
        """
        Парсинг запроса на естественном языке.

        Использует LLM если доступен, иначе rule-based parsing.
        """
        entities = {}

        if self.llm_client:
            try:
                print("[Orchestrator] Using LLM for parsing...")
                result = self.llm_client.parse_request(text)
                return {
                    "intent": result.get("intent", "unknown"),
                    "entities": result.get("entities", {}),
                    "original": text,
                }
            except Exception as e:
                print(f"[Orchestrator] LLM parsing failed: {e}, using rule-based")

        result = self._parse_rule_based(text)
        return {
            "intent": result["intent"],
            "entities": result["entities"],
            "original": text,
        }

    async def discover_agents(self, intent: str) -> Optional[dict]:
        """
        MPC-style discovery запрос.

        В реальном MPC:
        - Запрос клиента шифруется с использованием его секрета
        - Сервер выполняет вычисления над зашифрованными данными
        - Результат возвращается без раскрытия содержимого
        """
        keywords = self.intent_keywords.get(intent, [])
        if not keywords:
            return None

        encrypted_keywords = [self._hash_keyword(k) for k in keywords]
        request_hash = hashlib.sha256(intent.encode()).hexdigest()[:16]

        query = MPCQuery(
            encrypted_keywords=encrypted_keywords,
            request_hash=request_hash,
        )

        try:
            reader, writer = await asyncio.open_connection(self.mpc_host, self.mpc_port)

            message = {
                "type": "discovery",
                "encrypted_keywords": encrypted_keywords,
                "request_hash": request_hash,
            }

            writer.write(json.dumps(message).encode())
            await writer.drain()

            response = await reader.read(4096)
            result = json.loads(response.decode())

            writer.close()
            await writer.wait_closed()

            return result

        except Exception as e:
            print(f"[Orchestrator] Discovery error: {e}")
            return None

    async def send_task(self, agent_endpoint: str, task: str, params: dict) -> dict:
        """Отправка задачи агенту напрямую (A2A communication)."""
        try:
            host_port = agent_endpoint.replace("http://", "").split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 80

            reader, writer = await asyncio.open_connection(host, port)

            message = {
                "task": task,
                "params": params,
            }

            writer.write(json.dumps(message).encode())
            await writer.drain()

            response = await reader.read(4096)
            result = json.loads(response.decode())

            writer.close()
            await writer.wait_closed()

            return result

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def format_response(self, intent: str, agent_result: dict) -> str:
        """Форматирование ответа для пользователя."""
        if agent_result.get("status") != "success":
            return f"Ошибка: {agent_result.get('error', 'Неизвестная ошибка')}"

        result = agent_result.get("result", {})

        if intent == "weather":
            return (
                f"Погода в {result.get('location', 'неизвестно')}: "
                f"{result.get('condition', 'N/A')}, "
                f"{result.get('temperature', '?')}°C, "
                f"влажность {result.get('humidity', '?')}%"
            )

        elif intent == "finance":
            return (
                f"{result.get('symbol', 'N/A')}: "
                f"${result.get('price', '?')} "
                f"({result.get('change', '?'):+.2f}, "
                f"{result.get('change_percent', '?'):+.2f}%)"
            )

        return str(result)


async def main():
    orchestrator = A2AOrchestrator()

    print("=" * 60)
    print("A2A Agent System via MPC Discovery")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("Введите запрос (или 'quit' для выхода): ").strip()

            if not user_input or user_input.lower() == "quit":
                print("До свидания!")
                break

            print(f"\n[1] Получен запрос: {user_input}")

            parsed = orchestrator.parse_request(user_input)
            print(
                f"[2] Парсинг: intent={parsed['intent']}, entities={parsed['entities']}"
            )

            if parsed["intent"] == "unknown":
                print("Не удалось определить тип запроса. Попробуйте уточнить.")
                continue

            print(f"[3] Поиск агента через MPC сервер...")
            discovery = await orchestrator.discover_agents(parsed["intent"])

            if not discovery or not discovery.get("matched_agents"):
                print("Агенты не найдены.")
                continue

            agent = discovery["matched_agents"][0]
            print(f"[4] Найден агент: {agent['name']} ({agent['agent_id']})")

            task_map = {
                "weather": "get_weather",
                "finance": "get_quote",
            }
            task = task_map.get(parsed["intent"], "process")

            print(f"[5] Отправка задачи '{task}' агенту...")
            result = await orchestrator.send_task(
                agent["endpoint"],
                task,
                parsed["entities"],
            )

            response = orchestrator.format_response(parsed["intent"], result)
            print(f"\n>>> Ответ: {response}\n")

        except KeyboardInterrupt:
            print("\nДо свидания!")
            break
        except Exception as e:
            print(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
