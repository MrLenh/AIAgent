from ai_agent.data_sources.base import DataSource
from ai_agent.llm.base import LLMProvider


ANALYSIS_SYSTEM_PROMPT = """You are a senior data analyst. Answer questions
about the provided dataset with concrete findings, key metrics, and actionable
recommendations. When you cite a number, make sure it is supported by the
data. If a question cannot be answered from the data, say so explicitly.

Format the answer as:
## Key Findings
- <bullet>
- <bullet>

## Metrics
<markdown table or list>

## Recommendations
1. <recommendation>
2. <recommendation>
"""


class DataAnalysisTask:
    """Answer natural-language questions about a dataset."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def run(self, question: str, sources: list[DataSource]) -> str:
        if not sources:
            raise ValueError("DataAnalysisTask requires at least one data source")

        blocks = [f"### Source {s.describe()}\n{s.load()}" for s in sources]
        user_prompt = (
            f"Question: {question}\n\n"
            "Dataset(s):\n\n" + "\n\n".join(blocks)
        )
        resp = self.llm.prompt(
            user_prompt,
            system=ANALYSIS_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=3000,
        )
        return resp.text
