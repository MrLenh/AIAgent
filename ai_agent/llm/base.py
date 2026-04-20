from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


Role = Literal["system", "user", "assistant"]


@dataclass
class LLMMessage:
    role: Role
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    usage: dict = field(default_factory=dict)
    raw: object = None


class LLMProvider(ABC):
    """Uniform interface over OpenAI, Anthropic, and Gemini."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        ...

    def prompt(
        self,
        user_prompt: str,
        *,
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        messages: list[LLMMessage] = []
        if system:
            messages.append(LLMMessage(role="system", content=system))
        messages.append(LLMMessage(role="user", content=user_prompt))
        return self.complete(messages, **kwargs)
