"""AI Agent module: connect LLMs, data sources, and publishing platforms."""

from ai_agent.agent import AIAgent
from ai_agent.history import HistoryStore
from ai_agent.llm import OpenAIProvider, ClaudeProvider, GeminiProvider
from ai_agent.data_sources import TextSource, CSVSource, DatabaseSource
from ai_agent.platforms import ShopifyClient, WordPressClient, WooCommerceClient
from ai_agent.audit import (
    BlogCrawler,
    GSCClient,
    AhrefsClient,
    KeywordAuditTask,
    AuditReport,
    ContentPlanTask,
    ContentPlan,
    PlanItem,
    AuditStorage,
)

__all__ = [
    "AIAgent",
    "HistoryStore",
    "OpenAIProvider",
    "ClaudeProvider",
    "GeminiProvider",
    "TextSource",
    "CSVSource",
    "DatabaseSource",
    "ShopifyClient",
    "WordPressClient",
    "WooCommerceClient",
    "BlogCrawler",
    "GSCClient",
    "AhrefsClient",
    "KeywordAuditTask",
    "AuditReport",
    "ContentPlanTask",
    "ContentPlan",
    "PlanItem",
    "AuditStorage",
]
