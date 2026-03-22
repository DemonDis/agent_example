"""Finance Agent - A2A агент с LLM для генерации финансовых данных."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from typing import Optional
from agents.base_agent import BaseAgent


class FinanceAgent(BaseAgent):
    """Finance Agent - обрабатывает запросы связанные с финансами."""

    FINANCE_PROMPT = """Ты - финансовый сервис котировок. Сгенерируй реалистичные данные по акциям.

Для одной акции верни JSON:
- symbol: тикер (например AAPL, GOOGL)
- price: текущая цена (число с 2 знаками после запятой)
- change: изменение цены (число, может быть отрицательным)
- change_percent: процент изменения (число)
- description: краткое описание ситуации на рынке

Пример: {"symbol": "AAPL", "price": 175.50, "change": 2.35, "change_percent": 1.36, "description": "Рост на фоне позитивных новостей"}"""

    MARKET_SUMMARY_PROMPT = """Ты - финансовый сервис. Сгенерируй сводку по рынку акций.

Верни МАССИВ JSON объектов для 5 акций: AAPL, GOOGL, MSFT, TSLA, AMZN.
Каждый объект содержит:
- symbol: тикер
- price: цена
- change: изменение
- change_percent: процент
- sector: сектор (Tech/Automotive/E-commerce)

Пример: [{"symbol": "AAPL", "price": 175.50, "change": 2.35, "change_percent": 1.36, "sector": "Tech"}]"""

    def __init__(self, agent_id: str = "finance_agent_001", port: int = 9002):
        super().__init__(
            name="Finance Agent",
            description="Stock quotes and financial data",
            keywords=["stock", "finance", "market", "акции", "финансы", "price"],
        )
        self.agent_id = agent_id
        self.port = port
        self._server: Optional[asyncio.Server] = None

    async def register_with_mpc(
        self, mpc_host: str = "localhost", mpc_port: int = 9000
    ):
        """Регистрация агента в MPC сервере."""
        try:
            reader, writer = await asyncio.open_connection(mpc_host, mpc_port)

            registration = {
                "type": "register",
                "agent_id": self.agent_id,
                "name": self.name,
                "description": self.description,
                "keywords": self.keywords,
                "endpoint": f"http://localhost:{self.port}",
            }

            writer.write(json.dumps(registration).encode())
            await writer.drain()

            response = await reader.read(1024)
            result = json.loads(response.decode())

            print(f"[{self.name}] MPC registration: {result}")
            writer.close()
            await writer.wait_closed()
            return result.get("status") == "registered"

        except Exception as e:
            print(f"[{self.name}] Failed to register with MPC: {e}")
            return False

    def _generate_quote(self, symbol: str) -> dict:
        """Генерация котировки через LLM."""
        user_prompt = f"Акция: {symbol}"
        result = self.generate_response(self.FINANCE_PROMPT, user_prompt)

        json_str = result
        if "```json" in result:
            json_str = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            json_str = result.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    def _generate_market_summary(self) -> list:
        """Генерация сводки по рынку через LLM."""
        result = self.generate_response(self.MARKET_SUMMARY_PROMPT, "Сгенерируй сводку")

        json_str = result
        if "```json" in result:
            json_str = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            json_str = result.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    async def handle_request(self, request: dict) -> dict:
        """Обработка входящего A2A запроса."""
        task = request.get("task")
        params = request.get("params", {})

        print(f"[{self.name}] Processing task: {task}")

        if task == "get_quote":
            symbol = params.get("symbol", "UNKNOWN")
            quote = self._generate_quote(symbol)
            return {
                "status": "success",
                "result": quote,
            }

        elif task == "get_market_summary":
            quotes = self._generate_market_summary()
            return {
                "status": "success",
                "result": quotes,
            }

        else:
            return {
                "status": "error",
                "error": f"Unknown task: {task}",
            }

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Обработка входящих A2A соединений."""
        addr = writer.get_extra_info("peername")
        print(f"[{self.name}] Connection from {addr}")

        try:
            data = await reader.read(4096)
            message = json.loads(data.decode())

            response = await self.handle_request(message)

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            writer.write(json.dumps({"status": "error", "error": str(e)}).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        """Запуск агента."""
        await self.register_with_mpc()
        self._server = await asyncio.start_server(
            self.handle_client, "localhost", self.port
        )
        print(f"[{self.name}] Listening on localhost:{self.port}")
        async with self._server:
            await self._server.serve_forever()


async def main():
    agent = FinanceAgent(agent_id="finance_agent_001", port=9002)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
