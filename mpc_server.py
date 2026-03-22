"""
MPC Server - упрощённый реестр агентов с MPC-подобным функционалом.

В реальной системе MPC вычисления выполнялись бы распределённо
между несколькими узлами с использованием протоколов (SPDZ, SPDZ2, etc.)
Здесь мы демонстрируем КОНЦЕПЦИЮ: сервер не знает ЧТО ищет клиент,
только выполняет matching по зашифрованным/хешированным данным.
"""

import asyncio
import hashlib
import json
import random
import string
from typing import Optional
from models import AgentCapability, MPCQuery, MPCResponse


class MPCServer:
    """
    Упрощённый MPC Server.

    В реальности MPC протоколы требуют:
    - Минимум 3 участника для большинства протоколов
    - Секретное разделение данных (Secret Sharing)
    - Zero-Knowledge Proofs для верификации

    Здесь мы симулируем:
    - Хеширование запросов (запрос не хранится в открытом виде)
    - Capability matching по хешированным ключевым словам
    - Добавление "доказательства" выполнения
    """

    def __init__(self, host: str = "localhost", port: int = 9000):
        self.host = host
        self.port = port
        self.agents: dict[str, AgentCapability] = {}
        self._server: Optional[asyncio.Server] = None

    def register_agent(self, capability: AgentCapability) -> bool:
        """Регистрация агента в реестре."""
        agent_id = capability.agent_id
        self.agents[agent_id] = capability
        print(f"[MPC Server] Registered agent: {agent_id} ({capability.name})")
        return True

    def _hash_keyword(self, keyword: str) -> str:
        """Хеширование ключевого слова (симуляция encryption)."""
        return hashlib.sha256(keyword.lower().encode()).hexdigest()[:16]

    def _match_agents(self, encrypted_keywords: list[str]) -> list[AgentCapability]:
        """
        MPC-style matching.

        В реальном MPC сервер получает ЗАШИФРОВАННЫЕ keywords.
        Он не может их расшифровать, но может сравнить с хешами capabilities.
        """
        matched = []

        for agent in self.agents.values():
            agent_hashes = {self._hash_keyword(k) for k in agent.keywords}
            query_hashes = set(encrypted_keywords)

            if agent_hashes & query_hashes:
                matched.append(agent)

        return matched

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Обработка запросов от клиентов и агентов."""
        addr = writer.get_extra_info("peername")
        print(f"[MPC Server] Connection from {addr}")

        try:
            data = await reader.read(4096)
            message = json.loads(data.decode())

            msg_type = message.get("type")
            response = None

            if msg_type == "register":
                capability = AgentCapability(
                    name=message["name"],
                    description=message["description"],
                    keywords=message["keywords"],
                    endpoint=message["endpoint"],
                    agent_id=message["agent_id"],
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

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            print(f"[MPC Server] Error: {e}")
            writer.write(json.dumps({"error": str(e)}).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def _generate_proof(self, request_hash: str, matched: list[AgentCapability]) -> str:
        """Генерация proof (в реальности - ZK proof)."""
        matched_ids = ",".join(sorted(a.agent_id for a in matched))
        combined = f"{request_hash}:{matched_ids}:{len(matched)}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    async def start(self):
        """Запуск MPC сервера."""
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        print(f"[MPC Server] Started on {self.host}:{self.port}")
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        """Остановка сервера."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()


async def main():
    server = MPCServer(host="localhost", port=9000)

    server.register_agent(
        AgentCapability(
            name="Weather Agent",
            description="Provides weather forecasts and conditions",
            keywords=["weather", "temperature", "forecast", "погода", "температура"],
            endpoint="http://localhost:9001",
            agent_id="weather_agent_001",
        )
    )

    server.register_agent(
        AgentCapability(
            name="Finance Agent",
            description="Stock quotes and financial data",
            keywords=["stock", "finance", "market", "акции", "финансы"],
            endpoint="http://localhost:9002",
            agent_id="finance_agent_001",
        )
    )

    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
