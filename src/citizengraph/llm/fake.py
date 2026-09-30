"""Deterministic stand-in for the model. Used in unit tests and the mock API."""


class FakeLLM:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, max_tokens: int = 256, grammar: str | None = None) -> str:
        self.prompts.append(prompt)
        if self._responses:
            return self._responses.pop(0)
        return "MATCH (s:Service) RETURN s.name LIMIT 1"
