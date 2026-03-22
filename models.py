"""A2A Protocol models."""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
import json
import uuid
from datetime import datetime


class A2AMessageType(Enum):
    TASK = "task"
    RESULT = "result"
    ERROR = "error"
    CAPABILITIES_REQUEST = "capabilities_request"
    CAPABILITIES_RESPONSE = "capabilities_response"
    DELEGATE = "delegate"
    HEARTBEAT = "heartbeat"


class ProtocolVersion:
    CURRENT = "1.0"


@dataclass
class A2AEnvelope:
    """A2A Message Envelope - стандартный конверт для всех A2A сообщений."""

    msg_type: A2AMessageType
    from_agent: str
    to_agent: str
    body: dict
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = ProtocolVersion.CURRENT
    correlation_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    reply_to: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "message_id": self.message_id,
                "version": self.version,
                "msg_type": self.msg_type.value,
                "from": self.from_agent,
                "to": self.to_agent,
                "body": self.body,
                "correlation_id": self.correlation_id,
                "timestamp": self.timestamp,
                "reply_to": self.reply_to,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "A2AEnvelope":
        d = json.loads(data)
        return cls(
            message_id=d["message_id"],
            version=d.get("version", ProtocolVersion.CURRENT),
            msg_type=A2AMessageType(d["msg_type"]),
            from_agent=d["from"],
            to_agent=d["to"],
            body=d["body"],
            correlation_id=d.get("correlation_id"),
            timestamp=d.get("timestamp"),
            reply_to=d.get("reply_to"),
        )

    def create_response(
        self, body: dict, msg_type: Optional[A2AMessageType] = None
    ) -> "A2AEnvelope":
        """Создать ответ на это сообщение."""
        return A2AEnvelope(
            msg_type=msg_type or A2AMessageType.RESULT,
            from_agent=self.to_agent,
            to_agent=self.from_agent,
            body=body,
            correlation_id=self.message_id,
            reply_to=self.reply_to or self.from_agent,
        )


@dataclass
class TaskBody:
    """Тело задачи."""

    task: str
    params: dict
    context: Optional[dict] = None

    @classmethod
    def from_dict(cls, d: dict) -> "TaskBody":
        return cls(
            task=d.get("task", ""),
            params=d.get("params", {}),
            context=d.get("context"),
        )


@dataclass
class ResultBody:
    """Тело результата."""

    status: str
    result: Any
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "result": self.result,
            "metadata": self.metadata,
        }


@dataclass
class AgentCapability:
    """Capability агента для discovery."""

    agent_id: str
    name: str
    description: str
    keywords: list[str]
    endpoint: str
    port: int
    version: str = "1.0"
    can_delegate: bool = False
    metadata: Optional[dict] = None

    def matches(self, query: list[str]) -> bool:
        """Проверить совпадение с запросом."""
        query_lower = [q.lower() for q in query]
        for keyword in self.keywords:
            if keyword.lower() in query_lower:
                return True
        return False


@dataclass
class MPCQuery:
    """Запрос для MPC discovery."""

    encrypted_keywords: list[str]
    request_hash: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "encrypted_keywords": self.encrypted_keywords,
                "request_hash": self.request_hash,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "MPCQuery":
        d = json.loads(data)
        return cls(
            encrypted_keywords=d["encrypted_keywords"],
            request_hash=d["request_hash"],
        )


@dataclass
class MPCResponse:
    """Ответ от MPC discovery."""

    matched_agents: list[AgentCapability]
    proof: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "matched_agents": [
                    {
                        "agent_id": a.agent_id,
                        "name": a.name,
                        "description": a.description,
                        "keywords": a.keywords,
                        "endpoint": a.endpoint,
                        "port": a.port,
                        "version": a.version,
                        "can_delegate": a.can_delegate,
                    }
                    for a in self.matched_agents
                ],
                "proof": self.proof,
            }
        )
