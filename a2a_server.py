"""A2A Server - базовый сервер для агентов с поддержкой A2A протокола."""

import asyncio
import hashlib
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Optional, Callable, Awaitable
from models import (
    A2AEnvelope,
    A2AMessageType,
    AgentCapability,
    MPCQuery,
    MPCResponse,
    TaskBody,
    ResultBody,
)


class A2AServer:
    """
    Базовый A2A сервер.

    Поддерживает:
    - Приём и маршрутизацию A2A сообщений
    - Отправку сообщений другим агентам
    - Discovery через MPC-like реестр
    """

    def __init__(self, agent_id: str, port: int):
        self.agent_id = agent_id
        self.port = port
        self._server: Optional[asyncio.Server] = None
        self._running = False

        self.known_agents: dict[str, dict] = {}
        self.pending_messages: dict[str, asyncio.Future] = {}

    async def send_message(
        self,
        to_agent: str,
        msg_type: A2AMessageType,
        body: dict,
        correlation_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Отправить сообщение агенту напрямую."""
        if to_agent not in self.known_agents:
            print(f"[{self.agent_id}] Unknown agent: {to_agent}")
            return None

        agent_info = self.known_agents[to_agent]
        endpoint = agent_info["endpoint"]

        try:
            host_port = endpoint.replace("http://", "").split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 80

            envelope = A2AEnvelope(
                msg_type=msg_type,
                from_agent=self.agent_id,
                to_agent=to_agent,
                body=body,
                correlation_id=correlation_id,
            )

            reader, writer = await asyncio.open_connection(host, port)
            writer.write(envelope.to_json().encode())
            await writer.drain()

            response_data = await reader.read(8192)
            writer.close()
            await writer.wait_closed()

            if response_data:
                response = json.loads(response_data.decode())
                return response
            return None

        except Exception as e:
            print(f"[{self.agent_id}] Send to {to_agent} failed: {e}")
            return None

    async def delegate_to_agent(
        self, agent_id: str, task: str, params: dict, context: Optional[dict] = None
    ) -> Optional[dict]:
        """
        Делегировать задачу другому агенту.

        Returns результат от агента.
        """
        envelope = A2AEnvelope(
            msg_type=A2AMessageType.DELEGATE,
            from_agent=self.agent_id,
            to_agent=agent_id,
            body={
                "task": task,
                "params": params,
                "context": context or {},
            },
        )

        return await self.send_message(
            agent_id,
            A2AMessageType.TASK,
            envelope.body,
            correlation_id=envelope.message_id,
        )

    async def handle_message(self, envelope: A2AEnvelope) -> A2AEnvelope:
        """Обработать входящее A2A сообщение. Переопределяется в наследниках."""
        msg_type = envelope.msg_type

        if msg_type == A2AMessageType.TASK or msg_type == A2AMessageType.DELEGATE:
            return envelope.create_response(
                {
                    "status": "not_implemented",
                    "message": "Override handle_task in subclass",
                }
            )

        elif msg_type == A2AMessageType.CAPABILITIES_REQUEST:
            return envelope.create_response(
                {
                    "status": "not_implemented",
                }
            )

        elif msg_type == A2AMessageType.HEARTBEAT:
            return envelope.create_response({"status": "ok"})

        return envelope.create_response(
            {
                "status": "unknown_message_type",
                "message": f"Unknown type: {msg_type}",
            },
            A2AMessageType.ERROR,
        )

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Обработка входящих соединений."""
        addr = writer.get_extra_info("peername")

        try:
            data = await reader.read(8192)
            if not data:
                return

            message = json.loads(data.decode())

            if "msg_type" in message:
                envelope = A2AEnvelope.from_json(data.decode())
                response = await self.handle_message(envelope)
                writer.write(response.to_json().encode())
            else:
                writer.write(json.dumps({"error": "Invalid A2A message"}).encode())

            await writer.drain()

        except Exception as e:
            print(f"[{self.agent_id}] Error handling client {addr}: {e}")
            writer.write(json.dumps({"error": str(e)}).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        """Запустить сервер."""
        self._server = await asyncio.start_server(
            self.handle_client, "localhost", self.port
        )
        self._running = True
        print(f"[{self.agent_id}] A2A Server started on localhost:{self.port}")

        async with self._server:
            await self._server.serve_forever()

    def stop(self):
        """Остановить сервер."""
        self._running = False
        if self._server:
            self._server.close()


class RegistryServer:
    """
    MPC-like Registry Server для discovery агентов.
    """

    def __init__(self, host: str = "localhost", port: int = 9000):
        self.host = host
        self.port = port
        self.agents: dict[str, AgentCapability] = {}
        self._server: Optional[asyncio.Server] = None

    def register_agent(self, capability: AgentCapability) -> bool:
        self.agents[capability.agent_id] = capability
        print(f"[Registry] Registered: {capability.agent_id} ({capability.name})")
        return True

    def _hash_keyword(self, keyword: str) -> str:
        return hashlib.sha256(keyword.lower().encode()).hexdigest()[:16]

    def _match_agents(self, encrypted_keywords: list[str]) -> list[AgentCapability]:
        matched = []
        for agent in self.agents.values():
            agent_hashes = {self._hash_keyword(k) for k in agent.keywords}
            query_hashes = set(encrypted_keywords)
            if agent_hashes & query_hashes:
                matched.append(agent)
        return matched

    def _generate_proof(self, request_hash: str, matched: list[AgentCapability]) -> str:
        matched_ids = ",".join(sorted(a.agent_id for a in matched))
        combined = f"{request_hash}:{matched_ids}:{len(matched)}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        addr = writer.get_extra_info("peername")

        try:
            data = await reader.read(4096)
            message = json.loads(data.decode())
            msg_type = message.get("type")

            response = None

            if msg_type == "register":
                capability = AgentCapability(
                    agent_id=message["agent_id"],
                    name=message["name"],
                    description=message["description"],
                    keywords=message["keywords"],
                    endpoint=message["endpoint"],
                    port=message["port"],
                    can_delegate=message.get("can_delegate", False),
                )
                self.register_agent(capability)
                response = {"status": "registered", "agent_id": capability.agent_id}

            elif msg_type == "discovery":
                query = MPCQuery(
                    encrypted_keywords=message["encrypted_keywords"],
                    request_hash=message["request_hash"],
                )
                matched = self._match_agents(query.encrypted_keywords)

                mpc_response = MPCResponse(
                    matched_agents=matched,
                    proof=self._generate_proof(query.request_hash, matched),
                )
                response = json.loads(mpc_response.to_json())

            elif msg_type == "list_agents":
                response = {
                    "agents": [
                        {
                            "agent_id": a.agent_id,
                            "name": a.name,
                            "endpoint": a.endpoint,
                            "port": a.port,
                        }
                        for a in self.agents.values()
                    ]
                }

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            print(f"[Registry] Error: {e}")
            writer.write(json.dumps({"error": str(e)}).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        print(f"[Registry] Started on {self.host}:{self.port}")
        async with self._server:
            await self._server.serve_forever()


async def main():
    registry = RegistryServer(host="localhost", port=9000)

    registry.register_agent(
        AgentCapability(
            agent_id="weather_agent",
            name="Weather Agent",
            description="Provides weather forecasts",
            keywords=["weather", "temperature", "погода", "температура"],
            endpoint="http://localhost",
            port=9001,
            can_delegate=True,
        )
    )

    registry.register_agent(
        AgentCapability(
            agent_id="finance_agent",
            name="Finance Agent",
            description="Stock quotes and financial data",
            keywords=["stock", "finance", "акции", "финансы"],
            endpoint="http://localhost",
            port=9002,
            can_delegate=True,
        )
    )

    await registry.start()


if __name__ == "__main__":
    asyncio.run(main())
