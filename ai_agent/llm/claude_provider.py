import os

from ai_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider.

    Default model is the latest Claude Sonnet. Use ``claude-opus-4-7`` for the
    most capable model or ``claude-haiku-4-5-20251001`` for low-latency tasks.
    """

    name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        enable_prompt_caching: bool = True,
    ):
        from anthropic import Anthropic

        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.client = Anthropic(api_key=key)
        self.model = model
        self.enable_prompt_caching = enable_prompt_caching

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        system_parts: list[dict] = []
        chat_messages: list[dict] = []
        for m in messages:
            if m.role == "system":
                block = {"type": "text", "text": m.content}
                system_parts.append(block)
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        # Cache the system prompt (typically the largest, most reused part).
        if self.enable_prompt_caching and system_parts:
            system_parts[-1]["cache_control"] = {"type": "ephemeral"}

        resp = self.client.messages.create(
            model=self.model,
            system=system_parts or None,
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "cache_creation_input_tokens": getattr(
                resp.usage, "cache_creation_input_tokens", 0
            ),
            "cache_read_input_tokens": getattr(
                resp.usage, "cache_read_input_tokens", 0
            ),
        }
        return LLMResponse(text=text, model=self.model, usage=usage, raw=resp)
