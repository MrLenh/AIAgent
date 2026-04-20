from pathlib import Path

from ai_agent.data_sources.base import DataSource


class TextSource(DataSource):
    """Load raw text, either from a string or a file path."""

    name = "text"

    def __init__(self, content: str | None = None, path: str | Path | None = None):
        if not content and not path:
            raise ValueError("TextSource requires either content or path")
        self._content = content
        self._path = Path(path) if path else None

    def load(self) -> str:
        if self._content is not None:
            return self._content
        return self._path.read_text(encoding="utf-8")

    def describe(self) -> str:
        return f"[text: {self._path or 'inline'}]"
