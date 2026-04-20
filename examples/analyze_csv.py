"""Run a natural-language analysis on a CSV dataset."""

from dotenv import load_dotenv

from ai_agent import AIAgent, CSVSource, OpenAIProvider

load_dotenv()


def main() -> None:
    agent = AIAgent(llm=OpenAIProvider(model="gpt-4o"))
    agent.register_source(CSVSource("data/sales.csv"), name="sales")

    report = agent.analyze(
        "Which product categories grew fastest in the last quarter, and why?",
        use_sources=["sales"],
    )
    print(report)


if __name__ == "__main__":
    main()
