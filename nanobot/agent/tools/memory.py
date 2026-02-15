"""Memory search tool for agent's structured facts."""

from typing import Any

from nanobot.agent.tools.base import Tool


class MemorySearchTool(Tool):
    """Tool for searching agent's hierarchical memory."""

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search the agent's structured long-term memory for facts. "
            "Use this when you need to recall specific information about the user, "
            "past conversations, or learned knowledge. "
            "You can filter by domain (broad area) and/or category (specific topic)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query describing what you're looking for",
                },
                "domain": {
                    "type": "string",
                    "description": "Optional: filter by domain (e.g., 'User Preferences', 'Project: Nano Bot', 'Personal')",
                },
                "category": {
                    "type": "string",
                    "description": "Optional: filter by category (e.g., 'Architecture', 'Hobbies', 'Communication')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        domain: str | None = None,
        category: str | None = None,
        limit: int = 5,
        **kwargs: Any,
    ) -> str:
        from nanobot.memory.db import get_facts_filtered, semantic_search

        limit_val = max(1, min(limit or 5, 50))
        domain_opt = domain if domain and str(domain).strip() else None
        category_opt = category if category and str(category).strip() else None

        results: list[dict[str, Any]] = []

        try:
            if domain_opt or category_opt:
                # Filtered search by domain and/or category
                results = get_facts_filtered(
                    domain=domain_opt,
                    category=category_opt,
                    limit=limit_val,
                )
            else:
                # Vector/semantic search
                results = semantic_search(query, limit=limit_val)
        except Exception as exc:
            return f"Error searching memory: {exc}"

        if not results:
            return "No facts found matching your query."

        # Format results
        lines = [f"Found {len(results)} facts:\n"]
        for i, fact in enumerate(results[:limit_val], 1):
            d = fact.get("domain") or "general"
            c = fact.get("category", "—")
            sub = fact.get("sub_category") or ""
            k = fact.get("key", "—")
            v = fact.get("value", "—")

            if sub and str(sub).strip():
                line = f"{i}. [Domain: {d}] {c} > {sub} > {k}: {v}"
            else:
                line = f"{i}. [Domain: {d}] {c} > {k}: {v}"
            lines.append(line)

        return "\n".join(lines)
