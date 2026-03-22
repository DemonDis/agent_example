"""Finance Agent - A2A агент для предоставления финансовой информации."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import random
from typing import Optional


class FinanceAgent:
    """
    Finance Agent - обрабатывает запросы связанные с финансами.
    """

    def __init__(self, agent_id: str = "finance_agent_001", port: int = 9002):
        self.agent_id = agent_id
        self.port = port
        self.name = "Finance Agent"
        self.keywords = ["stock", "finance", "market", "акции", "финансы", "price"]
        self.description = "Stock quotes and financial data"
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

            print(f"[Finance Agent] MPC registration: {result}")
            writer.close()
            await writer.wait_closed()
            return result.get("status") == "registered"

        except Exception as e:
            print(f"[Finance Agent] Failed to register with MPC: {e}")
            return False

    def _generate_stock_quote(self, symbol: str) -> dict:
        """Генерация фейковых котировок."""
        base_prices = {
            "AAPL": 175.0,
            "GOOGL": 140.0,
            "MSFT": 380.0,
            "TSLA": 250.0,
            "AMZN": 175.0,
        }
        base = base_prices.get(symbol.upper(), 100.0)
        price = round(base + random.uniform(-5, 5), 2)

        return {
            "symbol": symbol.upper(),
            "price": price,
            "change": round(random.uniform(-5, 5), 2),
            "change_percent": round(random.uniform(-2, 2), 2),
            "volume": random.randint(1000000, 10000000),
        }

    async def handle_request(self, request: dict) -> dict:
        """Обработка входящего A2A запроса."""
        task = request.get("task")
        params = request.get("params", {})

        print(f"[Finance Agent] Processing task: {task}")

        if task == "get_quote":
            symbol = params.get("symbol", "UNKNOWN")
            quote = self._generate_stock_quote(symbol)
            return {
                "status": "success",
                "result": quote,
            }

        elif task == "get_market_summary":
            symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
            quotes = [self._generate_stock_quote(s) for s in symbols]
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
        print(f"[Finance Agent] Connection from {addr}")

        try:
            data = await reader.read(4096)
            message = json.loads(data.decode())

            response = await self.handle_request(message)

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            print(f"[Finance Agent] Error: {e}")
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
        print(f"[Finance Agent] Listening on localhost:{self.port}")
        async with self._server:
            await self._server.serve_forever()


async def main():
    agent = FinanceAgent(agent_id="finance_agent_001", port=9002)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
