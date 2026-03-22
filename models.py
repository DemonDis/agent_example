"""Shared data models for A2A/MPC system."""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
import json


class MessageType(Enum):
    REGISTER = "register"
    DISCOVERY_REQUEST = "discovery_request"
    DISCOVERY_RESPONSE = "discovery_response"
    A2A_TASK = "a2a_task"
    A2A_RESPONSE = "a2a_response"


@dataclass
class AgentCapability:
    name: str
    description: str
    keywords: list[str]
    endpoint: str
    agent_id: str


@dataclass
class A2AMessage:
    type: MessageType
    sender_id: str
    payload: dict
    signature: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type.value,
                "sender_id": self.sender_id,
                "payload": self.payload,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "A2AMessage":
        d = json.loads(data)
        return cls(
            type=MessageType(d["type"]),
            sender_id=d["sender_id"],
            payload=d["payload"],
        )


@dataclass
class MPCQuery:
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
    matched_agents: list[AgentCapability]
    proof: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "matched_agents": [
                    {
                        "name": a.name,
                        "description": a.description,
                        "keywords": a.keywords,
                        "endpoint": a.endpoint,
                        "agent_id": a.agent_id,
                    }
                    for a in self.matched_agents
                ],
                "proof": self.proof,
            }
        )
