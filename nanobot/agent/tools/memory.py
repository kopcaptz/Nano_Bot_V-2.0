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
            "Search for facts in your memory. You can filter by domain, category, "
            "or perform a semantic search using a natural language query. "
            "Use this to recall user preferences, project details, or past decisions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query for semantic search across all facts.",
                },
                "domain": {
                    "type": "string",
                    "description": "Filter by domain (e.g., 'User Preferences', 'Project: Nano Bot').",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g., 'Architecture', 'Hobbies').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 10).",
                },
            },
        }

    async def execute(
        self,
        query: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> str:
        from nanobot.memory.db import get_facts_filtered, search_facts, semantic_search

        results: list[dict[str, Any]] = []
        limit_val = max(1, min(limit, 50))

        # Semantic search when query is provided
        if query:
            try:
                hits = semantic_search(query, limit=limit_val)
                results.extend(hits)
            except Exception:
                # Fallback to text search
                hits = search_facts(query)
                results.extend(hits[:limit_val])

        # Filtering by domain/category
        if domain or category:
            filtered = get_facts_filtered(
                domain=domain if domain and str(domain).strip() else None,
                category=category if category and str(category).strip() else None,
                limit=limit_val,
            )
            # Add only facts not already in results
            existing_keys = {(r.get("category", ""), r.get("key", "")) for r in results}
            for f in filtered:
                if (f.get("category", ""), f.get("key", "")) not in existing_keys:
                    results.append(f)
                    existing_keys.add((f.get("category", ""), f.get("key", "")))
                if len(results) >= limit_val:
                    break

        if not query and not domain and not category:
            return "Error: At least one parameter (query, domain, or category) must be provided."

        if not results:
            return "No facts found matching your search criteria."

        # Format results
        lines = [f"Found {len(results)} fact(s):\n"]
        for i, fact in enumerate(results[:limit_val], 1):
            d = fact.get("domain") or "—"
            c = fact.get("category", "—")
            k = fact.get("key", "—")
            v = fact.get("value", "—")
            dist = fact.get("distance")
            line = f"{i}. [{d}] {c} → {k}: {v}"
            if dist is not None:
                line += f" (relevance: {1 - dist:.2f})"
            lines.append(line)

        return "\n".join(lines)
