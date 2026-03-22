"""Finance Agent - A2A агент с LLM и поддержкой делегирования."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from typing import Optional
from agents.base_agent import BaseA2AAgent
from models import A2AEnvelope, A2AMessageType


class FinanceAgent(BaseA2AAgent):
    """Finance Agent - обрабатывает финансовые запросы."""

    FINANCE_PROMPT = """Ты - финансовый сервис. Сгенерируй реалистичные данные по акциям.

Верни ТОЛЬКО валидный JSON (без markdown), например:
{"symbol": "AAPL", "price": 175.50, "change": 2.35, "change_percent": 1.36, "description": "Рост на фоне позитивных новостей"}

Поля:
- symbol: тикер (AAPL, GOOGL, MSFT, TSLA, AMZN)
- price: цена (число)
- change: изменение (число, может быть отрицательным)
- change_percent: процент (число)
- description: описание ситуации"""

    MARKET_SUMMARY_PROMPT = """Ты - финансовый сервис. Сгенерируй сводку по рынку.

Верни ТОЛЬКО массив JSON (без markdown):
[{"symbol": "AAPL", "price": 175.50, "change": 2.35, "change_percent": 1.36, "sector": "Tech"}, ...]

Акции: AAPL, GOOGL, MSFT, TSLA, AMZN

Поля:
- symbol: тикер
- price: цена
- change: изменение
- change_percent: процент
- sector: Tech/Automotive/E-commerce"""

    def __init__(self, agent_id: str = "finance_agent", port: int = 9002):
        super().__init__(
            agent_id=agent_id,
            name="Finance Agent",
            description="Stock quotes and financial data",
            keywords=["stock", "finance", "market", "акции", "финансы", "price"],
            port=port,
        )
        self._server: Optional[asyncio.Server] = None

    async def register_with_registry(
        self, registry_host: str = "localhost", registry_port: int = 9000
    ):
        """Регистрация агента в Registry."""
        try:
            reader, writer = await asyncio.open_connection(registry_host, registry_port)

            registration = {
                "type": "register",
                "agent_id": self.agent_id,
                "name": self.name,
                "description": self.description,
                "keywords": self.keywords,
                "endpoint": "http://localhost",
                "port": self.port,
                "can_delegate": self.can_delegate,
            }

            writer.write(json.dumps(registration).encode())
            await writer.drain()

            response = await reader.read(1024)
            result = json.loads(response.decode())

            print(f"[{self.agent_id}] Registry registration: {result}")
            writer.close()
            await writer.wait_closed()
            return result.get("status") == "registered"

        except Exception as e:
            print(f"[{self.agent_id}] Registry registration failed: {e}")
            return False

    def _generate_quote(self, symbol: str) -> dict:
        """Генерация котировки через LLM."""
        user_prompt = f"Акция: {symbol}"
        result = self.generate_response(self.FINANCE_PROMPT, user_prompt)

        json_str = result.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    def _generate_market_summary(self) -> list:
        """Генерация сводки по рынку через LLM."""
        result = self.generate_response(self.MARKET_SUMMARY_PROMPT, "Сгенерируй сводку")

        json_str = result.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    async def handle_task(
        self, task: str, params: dict, context: Optional[dict] = None
    ) -> dict:
        """Обработка задачи."""
        print(f"[{self.agent_id}] Handle task: {task}, params: {params}")

        if task == "get_quote":
            symbol = params.get("symbol", "UNKNOWN")
            quote = self._generate_quote(symbol)
            return {"status": "success", "result": quote}

        elif task == "get_market_summary":
            quotes = self._generate_market_summary()
            return {"status": "success", "result": quotes}

        elif task == "get_market_context":
            location = params.get("location", "")
            quotes = self._generate_market_summary()
            return {
                "status": "success",
                "result": {
                    "location": location,
                    "market_data": quotes[:2],
                    "note": f"Market data for context in {location}",
                },
            }

        else:
            return {"status": "error", "error": f"Unknown task: {task}"}

    async def handle_message(self, envelope: A2AEnvelope) -> A2AEnvelope:
        """Обработка входящего A2A сообщения."""
        msg_type = envelope.msg_type

        if msg_type == A2AMessageType.TASK or msg_type == A2AMessageType.DELEGATE:
            result = await self.handle_task(
                envelope.body.get("task", ""),
                envelope.body.get("params", {}),
                envelope.body.get("context"),
            )
            return envelope.create_response(result)

        elif msg_type == A2AMessageType.CAPABILITIES_REQUEST:
            return envelope.create_response(
                {
                    "agent_id": self.agent_id,
                    "name": self.name,
                    "description": self.description,
                    "keywords": self.keywords,
                    "can_delegate": self.can_delegate,
                }
            )

        return envelope.create_response(
            {"error": f"Unknown type: {msg_type}"}, A2AMessageType.ERROR
        )

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Обработка входящих A2A соединений."""
        addr = writer.get_extra_info("peername")
        print(f"[{self.agent_id}] Connection from {addr}")

        try:
            data = await reader.read(8192)
            message = json.loads(data.decode())

            if "msg_type" in message:
                envelope = A2AEnvelope.from_json(data.decode())
                response = await self.handle_message(envelope)
                writer.write(response.to_json().encode())
            else:
                task_body = message.get("body", message)
                result = await self.handle_task(
                    task_body.get("task", ""),
                    task_body.get("params", {}),
                    task_body.get("context"),
                )
                writer.write(json.dumps(result).encode())

            await writer.drain()

        except Exception as e:
            print(f"[{self.agent_id}] Error: {e}")
            writer.write(json.dumps({"status": "error", "error": str(e)}).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        """Запуск агента."""
        await self.register_with_registry()
        self._server = await asyncio.start_server(
            self.handle_client, "localhost", self.port
        )
        print(f"[{self.agent_id}] A2A Finance Agent listening on localhost:{self.port}")
        async with self._server:
            await self._server.serve_forever()


async def main():
    agent = FinanceAgent(agent_id="finance_agent", port=9002)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
