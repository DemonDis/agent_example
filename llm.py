"""LLM integration for natural language parsing."""

import os
from dotenv import load_dotenv

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


load_dotenv()


class LLMClient:
    """LLM client using OpenAI-compatible API."""

    def __init__(self):
        self.api_key = os.getenv("API_KEY", "")
        self.base_url = os.getenv("BASE_URL", "")
        self.model = os.getenv("LLM_NAME", "")

        if not self.api_key:
            raise ValueError("API_KEY not found in .env")

        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def parse_request(self, text: str) -> dict:
        """Parse natural language request into structured intent/entities."""

        system_prompt = """Ты - intent parser для A2A агентной системы.
Определи intent пользователя и извлеки entities.

Доступные intents:
- weather: запрос погоды, температуры, прогноза
- finance: запрос акций, финансовых данных, цен

Верни JSON с полями:
- intent: определённый intent (weather/finance/unknown)
- entities: dict с извлечёнными параметрами (location, symbol, и т.д.)

Примеры:
- "погода в Токио" → {"intent": "weather", "entities": {"location": "Tokyo"}}
- "курс акций AAPL" → {"intent": "finance", "entities": {"symbol": "AAPL"}}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=200,
        )

        import json

        result = response.choices[0].message.content.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        return json.loads(result)


def create_llm_client() -> LLMClient:
    """Factory function to create LLM client."""
    return LLMClient()
