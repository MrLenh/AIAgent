import os

from ai_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
    ):
        import google.generativeai as genai

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is required")
        genai.configure(api_key=key)
        self._genai = genai
        self.model = model

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        system_instruction = "\n".join(m.content for m in messages if m.role == "system") or None
        gemini_messages = [
            {
                "role": "user" if m.role == "user" else "model",
                "parts": [m.content],
            }
            for m in messages
            if m.role != "system"
        ]

        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system_instruction,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        resp = model.generate_content(gemini_messages, **kwargs)

        # Surface safety blocks and empty candidates as explicit errors instead
        # of crashing on resp.text access.
        try:
            text = resp.text or ""
        except Exception as exc:
            feedback = getattr(resp, "prompt_feedback", None)
            finish = ""
            if getattr(resp, "candidates", None):
                finish = getattr(resp.candidates[0], "finish_reason", "")
            hint = ""
            # finish_reason 2 == MAX_TOKENS. Gemini 2.5 "thinking" models burn
            # tokens internally; bumping max_tokens usually fixes this.
            if str(finish) in ("2", "MAX_TOKENS", "FinishReason.MAX_TOKENS"):
                hint = (
                    " Hint: MAX_TOKENS — Gemini 2.5 thinking models consume "
                    "tokens internally. Increase max_tokens or switch to "
                    "gemini-2.5-flash-lite (no thinking)."
                )
            raise RuntimeError(
                f"Gemini returned no text (finish_reason={finish}, "
                f"prompt_feedback={feedback}).{hint} Underlying: {exc}"
            ) from exc

        usage = {}
        if getattr(resp, "usage_metadata", None):
            usage = {
                "input_tokens": resp.usage_metadata.prompt_token_count,
                "output_tokens": resp.usage_metadata.candidates_token_count,
            }
        return LLMResponse(text=text, model=self.model, usage=usage, raw=resp)
