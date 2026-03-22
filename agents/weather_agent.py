"""Weather Agent - A2A агент с LLM и поддержкой делегирования."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from typing import Optional
from agents.base_agent import BaseA2AAgent
from models import A2AEnvelope, A2AMessageType


class WeatherAgent(BaseA2AAgent):
    """Weather Agent - обрабатывает погодные запросы и может делегировать."""

    WEATHER_PROMPT = """Ты - метеорологический сервис. На основе данных о погоде сгенерируй реалистичный прогноз.

Верни ТОЛЬКО валидный JSON (без markdown), например:
{"location": "Tokyo", "temperature": 18, "condition": "sunny", "humidity": 65, "description": "Ясно, без осадков"}

Поля:
- location: название города
- temperature: температура в °C (число)
- condition: состояние (sunny/cloudy/rainy/partly cloudy/snowy/windy)
- humidity: влажность % (число)
- description: описание на 1-2 предложения"""

    def __init__(self, agent_id: str = "weather_agent", port: int = 9001):
        super().__init__(
            agent_id=agent_id,
            name="Weather Agent",
            description="Provides weather forecasts and conditions",
            keywords=["weather", "temperature", "forecast", "погода", "температура"],
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
                "endpoint": f"http://localhost",
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

    def _generate_weather(self, location: str) -> dict:
        """Генерация погоды через LLM."""
        user_prompt = f"Город: {location}"
        result = self.generate_response(self.WEATHER_PROMPT, user_prompt)

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

        if task == "get_weather":
            location = params.get("location", "Unknown")
            weather = self._generate_weather(location)

            context = context or {}
            if context.get("need_finance"):
                print(f"[{self.agent_id}] Delegating to finance_agent...")
                finance_result = await self.delegate_task(
                    "finance_agent",
                    "get_market_context",
                    {"location": location},
                    context={"source": "weather_agent"},
                )
                if finance_result:
                    weather["finance_context"] = finance_result.get("result", {})

            return {"status": "success", "result": weather}

        elif task == "get_forecast":
            location = params.get("location", "Unknown")
            forecasts = [self._generate_weather(location) for _ in range(3)]
            return {"status": "success", "result": forecasts}

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
        print(f"[{self.agent_id}] A2A Weather Agent listening on localhost:{self.port}")
        async with self._server:
            await self._server.serve_forever()


async def main():
    agent = WeatherAgent(agent_id="weather_agent", port=9001)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
