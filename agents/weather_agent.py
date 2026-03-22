"""Weather Agent - A2A агент с LLM для генерации погодных данных."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from typing import Optional
from agents.base_agent import BaseAgent


class WeatherAgent(BaseAgent):
    """Weather Agent - обрабатывает запросы связанные с погодой."""

    WEATHER_PROMPT = """Ты - метеорологический сервис. На основе данных о погоде сгенерируй реалистичный прогноз.

Верни JSON с полями:
- location: название города
- temperature: температура в градусах Цельсия (число)
- condition: состояние погоды (sunny/cloudy/rainy/partly cloudy/snowy/windy)
- humidity: влажность в процентах (число)
- description: краткое описание погоды на 1-2 предложения

Пример: {"location": "Tokyo", "temperature": 18, "condition": "sunny", "humidity": 65, "description": "Ясно, без осадков"}"""

    def __init__(self, agent_id: str = "weather_agent_001", port: int = 9001):
        super().__init__(
            name="Weather Agent",
            description="Provides weather forecasts and conditions",
            keywords=["weather", "temperature", "forecast", "погода", "температура"],
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

    def _generate_weather(self, location: str) -> dict:
        """Генерация погоды через LLM."""
        user_prompt = f"Город: {location}"

        result = self.generate_response(self.WEATHER_PROMPT, user_prompt)

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
    agent = WeatherAgent(agent_id="weather_agent_001", port=9001)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
