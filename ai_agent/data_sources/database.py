from ai_agent.data_sources.base import DataSource


class DatabaseSource(DataSource):
    """Query any SQLAlchemy-supported DB (PostgreSQL, MySQL, SQLite, etc.)."""

    name = "database"

    def __init__(
        self,
        url: str,
        query: str,
        params: dict | None = None,
        max_rows: int | None = 200,
    ):
        from sqlalchemy import create_engine

        self.engine = create_engine(url)
        self.query = query
        self.params = params or {}
        self.max_rows = max_rows

    def load(self) -> str:
        import pandas as pd
        from sqlalchemy import text

        with self.engine.connect() as conn:
            df = pd.read_sql(text(self.query), conn, params=self.params)

        total_rows = len(df)
        if self.max_rows and total_rows > self.max_rows:
            df = df.head(self.max_rows)

        body = df.to_markdown(index=False)
        header = f"Query returned {total_rows} rows, {len(df.columns)} columns"
        if self.max_rows and total_rows > self.max_rows:
            body += f"\n... (truncated to first {self.max_rows} of {total_rows} rows)"
        return f"{header}\n\n{body}"

    def describe(self) -> str:
        return f"[database query: {self.query[:60]}...]"
