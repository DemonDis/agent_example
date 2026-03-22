"""Base A2A Agent с поддержкой протокола."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

from models import A2AEnvelope, A2AMessageType, AgentCapability

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class BaseA2AAgent:
    """
    Базовый класс для A2A агентов.

    Особенности:
    - Поддержка A2A протокола
    - Делегирование задач другим агентам
    - Интеграция с LLM
    - Регистрация в Registry
    """

    def __init__(
        self, agent_id: str, name: str, description: str, keywords: list[str], port: int
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.keywords = keywords
        self.port = port
        self.can_delegate = True

        self.llm_client = None
        self.model = None
        self._init_llm()

        self.capability = AgentCapability(
            agent_id=agent_id,
            name=name,
            description=description,
            keywords=keywords,
            endpoint="http://localhost",
            port=port,
            can_delegate=self.can_delegate,
        )

    def _init_llm(self):
        """Инициализация LLM клиента."""
        if OPENAI_AVAILABLE and os.getenv("API_KEY"):
            try:
                self.llm_client = OpenAI(
                    api_key=os.getenv("API_KEY"),
                    base_url=os.getenv("BASE_URL", ""),
                )
                self.model = os.getenv("LLM_NAME", "")
                print(f"[{self.agent_id}] LLM initialized: {self.model}")
            except Exception as e:
                print(f"[{self.agent_id}] LLM init failed: {e}")

    def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """Генерация ответа через LLM."""
        if not self.llm_client:
            raise RuntimeError("LLM not available")

        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()

    async def delegate_task(
        self, agent_id: str, task: str, params: dict, context: Optional[dict] = None
    ) -> Optional[dict]:
        """
        Делегировать задачу другому агенту.

        Returns результат выполнения задачи.
        """
        from a2a_server import A2AServer

        server = A2AServer(self.agent_id, self.port)
        return await server.delegate_to_agent(agent_id, task, params, context)

    async def handle_task(
        self, task: str, params: dict, context: Optional[dict] = None
    ) -> dict:
        """
        Обработать задачу.

        Переопределяется в наследниках.
        """
        raise NotImplementedError("Implement handle_task in subclass")

    async def handle_message(self, envelope: A2AEnvelope) -> A2AEnvelope:
        """Обработать входящее A2A сообщение."""
        msg_type = envelope.msg_type

        if msg_type == A2AMessageType.TASK or msg_type == A2AMessageType.DELEGATE:
            task_body = envelope.body
            result = await self.handle_task(
                task_body.get("task", ""),
                task_body.get("params", {}),
                task_body.get("context"),
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

        elif msg_type == A2AMessageType.HEARTBEAT:
            return envelope.create_response({"status": "ok"})

        return envelope.create_response(
            {"error": f"Unknown message type: {msg_type}"}, A2AMessageType.ERROR
        )

    def get_capability(self) -> AgentCapability:
        """Получить capability агента."""
        return self.capability
