"""Base agent class with LLM integration."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class BaseAgent:
    """Base class for all A2A agents with LLM support."""

    def __init__(self, name: str, description: str, keywords: list[str]):
        self.name = name
        self.description = description
        self.keywords = keywords

        self.llm_client = None
        if OPENAI_AVAILABLE and os.getenv("API_KEY"):
            try:
                self.llm_client = OpenAI(
                    api_key=os.getenv("API_KEY"),
                    base_url=os.getenv("BASE_URL", ""),
                )
                self.model = os.getenv("LLM_NAME", "")
                print(f"[{self.name}] LLM initialized")
            except Exception as e:
                print(f"[{self.name}] LLM init failed: {e}")

    def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using LLM."""
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
