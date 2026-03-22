"""Weather Agent - A2A агент для предоставления погодной информации."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import random
from typing import Optional


class WeatherAgent:
    """
    Weather Agent - обрабатывает запросы связанные с погодой.

    В A2A архитектуре агент:
    1. Регистрируется в MPC Server при старте
    2. Слушает входящие A2A сообщения
    3. Обрабатывает задачи и возвращает результаты
    """

    def __init__(self, agent_id: str = "weather_agent_001", port: int = 9001):
        self.agent_id = agent_id
        self.port = port
        self.name = "Weather Agent"
        self.keywords = ["weather", "temperature", "forecast", "погода", "температура"]
        self.description = "Provides weather forecasts and conditions"
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

            print(f"[Weather Agent] MPC registration: {result}")
            writer.close()
            await writer.wait_closed()
            return result.get("status") == "registered"

        except Exception as e:
            print(f"[Weather Agent] Failed to register with MPC: {e}")
            return False

    def _generate_weather(self, location: str) -> dict:
        """Генерация фейковых погодных данных."""
        conditions = ["sunny", "cloudy", "rainy", "partly cloudy", "clear"]
        temp_range = {
            "tokyo": (15, 25),
            "moscow": (5, 15),
            "london": (8, 18),
            "new york": (10, 22),
        }

        loc_lower = location.lower()
        temp_min, temp_max = (10, 25)
        for city, (t_min, t_max) in temp_range.items():
            if city in loc_lower:
                temp_min, temp_max = t_min, t_max
                break

        return {
            "location": location,
            "temperature": random.randint(temp_min, temp_max),
            "condition": random.choice(conditions),
            "humidity": random.randint(40, 80),
            "timestamp": "2024-03-22 15:00:00",
        }

    async def handle_request(self, request: dict) -> dict:
        """Обработка входящего A2A запроса."""
        task = request.get("task")
        params = request.get("params", {})

        print(f"[Weather Agent] Processing task: {task}")

        if task == "get_weather":
            location = params.get("location", "Unknown")
            weather = self._generate_weather(location)
            return {
                "status": "success",
                "result": weather,
            }

        elif task == "get_forecast":
            location = params.get("location", "Unknown")
            forecasts = [
                self._generate_weather(location),
                self._generate_weather(location),
                self._generate_weather(location),
            ]
            return {
                "status": "success",
                "result": forecasts,
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
        print(f"[Weather Agent] Connection from {addr}")

        try:
            data = await reader.read(4096)
            message = json.loads(data.decode())

            response = await self.handle_request(message)

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            print(f"[Weather Agent] Error: {e}")
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
        print(f"[Weather Agent] Listening on localhost:{self.port}")
        async with self._server:
            await self._server.serve_forever()


async def main():
    agent = WeatherAgent(agent_id="weather_agent_001", port=9001)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
