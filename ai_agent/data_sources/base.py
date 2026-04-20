from abc import ABC, abstractmethod


class DataSource(ABC):
    """Data source that can be serialized into prompt context for the LLM."""

    name: str = "base"

    @abstractmethod
    def load(self) -> str:
        """Return a text blob ready to be embedded in a prompt."""

    def describe(self) -> str:
        return f"[{self.name}]"
