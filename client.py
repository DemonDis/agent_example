"""A2A Orchestrator/Client - терминальный клиент для A2A системы."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import json
import hashlib
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from models import A2AEnvelope, A2AMessageType, MPCQuery

try:
    from llm import create_llm_client

    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False


class A2AClient:
    """
    A2A Orchestrator - координирует взаимодействие через A2A протокол.

    Отвечает за:
    1. Парсинг естественного языка → intent + entities
    2. Discovery агентов через Registry
    3. Отправку задач через A2A протокол
    4. Формирование ответа для пользователя
    """

    def __init__(self, registry_host: str = "localhost", registry_port: int = 9000):
        self.registry_host = registry_host
        self.registry_port = registry_port

        self.llm_client = None
        if LLM_AVAILABLE and os.getenv("API_KEY"):
            try:
                self.llm_client = create_llm_client()
                print("[A2A Client] LLM parsing enabled")
            except Exception as e:
                print(f"[A2A Client] LLM not available: {e}")

        self.intent_keywords = {
            "weather": ["weather", "погода", "temperature", "температура", "forecast"],
            "finance": ["stock", "акции", "finance", "финансы", "price", "цена"],
        }

    def _hash_keyword(self, keyword: str) -> str:
        """Хеширование ключевого слова для MPC-like discovery."""
        return hashlib.sha256(keyword.lower().encode()).hexdigest()[:16]

    async def discover_agents(self, intent: str) -> Optional[list]:
        """Discovery агентов через Registry."""
        keywords = self.intent_keywords.get(intent, [])
        if not keywords:
            return None

        encrypted_keywords = [self._hash_keyword(k) for k in keywords]
        request_hash = hashlib.sha256(intent.encode()).hexdigest()[:16]

        try:
            reader, writer = await asyncio.open_connection(
                self.registry_host, self.registry_port
            )

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

            return result.get("matched_agents")

        except Exception as e:
            print(f"[A2A Client] Discovery error: {e}")
            return None

    async def send_task_a2a(
        self, agent_port: int, task: str, params: dict, context: Optional[dict] = None
    ) -> dict:
        """Отправка задачи агенту через A2A протокол."""
        try:
            reader, writer = await asyncio.open_connection("localhost", agent_port)

            envelope = A2AEnvelope(
                msg_type=A2AMessageType.TASK,
                from_agent="orchestrator",
                to_agent="agent",
                body={
                    "task": task,
                    "params": params,
                    "context": context or {},
                },
            )

            writer.write(envelope.to_json().encode())
            await writer.drain()

            response_data = await reader.read(8192)
            writer.close()
            await writer.wait_closed()

            if response_data:
                response = json.loads(response_data.decode())
                if "body" in response:
                    return response["body"]
                return response

            return {"status": "error", "error": "No response"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def discover_and_route(self, intent: str, params: dict) -> dict:
        """Discovery + отправка задачи агенту."""
        agents = await self.discover_agents(intent)

        if not agents:
            return {"status": "error", "error": "No agents found"}

        agent = agents[0]
        port = agent.get("port", 9001)

        task_map = {
            "weather": "get_weather",
            "finance": "get_quote",
        }
        task = task_map.get(intent, "process")

        print(f"[A2A Client] Found agent: {agent['name']}, port: {port}")
        return await self.send_task_a2a(port, task, params)

    def format_response(self, intent: str, result: dict) -> str:
        """Форматирование ответа для пользователя."""
        if result.get("status") != "success":
            return f"Ошибка: {result.get('error', 'Неизвестная ошибка')}"

        data = result.get("result", {})

        if intent == "weather":
            if isinstance(data, list):
                return "\n".join(
                    [
                        f"  {i + 1}. {r.get('location')}: {r.get('condition')}, {r.get('temperature')}°C"
                        for i, r in enumerate(data)
                    ]
                )
            desc = data.get("description", "")
            return (
                f"{desc}\n"
                f"  📍 {data.get('location', '?')}, "
                f"{data.get('temperature', '?')}°C, "
                f"{data.get('condition', '?')}, "
                f"влажность {data.get('humidity', '?')}%"
            )

        elif intent == "finance":
            if isinstance(data, list):
                return "\n".join(
                    [
                        f"  {r.get('symbol')}: ${r.get('price')} ({r.get('change'):+.2f}%)"
                        for r in data
                    ]
                )
            desc = data.get("description", "")
            return (
                f"{desc}\n"
                f"  {data.get('symbol')}: "
                f"${data.get('price')} "
                f"({data.get('change'):+.2f}, "
                f"{data.get('change_percent'):+.2f}%)"
            )

        return str(data)


async def main():
    client = A2AClient()

    print("=" * 60)
    print("A2A Agent System")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("Введите запрос (или 'quit' для выхода): ").strip()

            if not user_input or user_input.lower() == "quit":
                print("До свидания!")
                break

            print(f"\n[1] Запрос: {user_input}")

            if client.llm_client:
                print("[2] LLM парсинг...")
                parsed = client.llm_client.parse_request(user_input)
                intent = parsed.get("intent", "unknown")
                entities = parsed.get("entities", {})
            else:
                intent = "unknown"
                entities = {}
                for name, keywords in client.intent_keywords.items():
                    if any(kw in user_input.lower() for kw in keywords):
                        intent = name
                        break

            print(f"[3] Intent: {intent}, Entities: {entities}")

            if intent == "unknown":
                print("Не удалось определить тип запроса.")
                continue

            print("[4] Discovery агента...")
            result = await client.discover_and_route(intent, entities)

            print("[5] Форматирование ответа...")
            response = client.format_response(intent, result)
            print(f"\n>>> {response}\n")

        except KeyboardInterrupt:
            print("\nДо свидания!")
            break
        except Exception as e:
            print(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
