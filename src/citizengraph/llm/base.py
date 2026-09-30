"""Model interface. All model use goes through LLMClient so tests can use FakeLLM."""

from typing import Protocol


class LLMClient(Protocol):
    def generate(self, prompt: str, *, max_tokens: int = 256, grammar: str | None = None) -> str:
        """Return the model's completion for a short, controlled prompt.

        `grammar` is an optional GBNF grammar for constrained decoding (llama.cpp).
        """
        ...
