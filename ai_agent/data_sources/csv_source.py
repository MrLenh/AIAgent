from pathlib import Path

from ai_agent.data_sources.base import DataSource


class CSVSource(DataSource):
    """Load a CSV file and render it as a markdown table for the prompt."""

    name = "csv"

    def __init__(
        self,
        path: str | Path,
        max_rows: int | None = 200,
        include_summary: bool = True,
    ):
        self.path = Path(path)
        self.max_rows = max_rows
        self.include_summary = include_summary

    def load(self) -> str:
        import pandas as pd

        df = pd.read_csv(self.path)
        total_rows = len(df)
        if self.max_rows and total_rows > self.max_rows:
            df = df.head(self.max_rows)

        parts: list[str] = []
        if self.include_summary:
            parts.append(
                f"CSV: {self.path.name} ({total_rows} rows, {len(df.columns)} cols)"
            )
            parts.append(f"Columns: {', '.join(df.columns.astype(str))}")
        parts.append(df.to_markdown(index=False))
        if self.max_rows and total_rows > self.max_rows:
            parts.append(f"... (truncated to first {self.max_rows} of {total_rows} rows)")
        return "\n\n".join(parts)

    def describe(self) -> str:
        return f"[csv: {self.path.name}]"
