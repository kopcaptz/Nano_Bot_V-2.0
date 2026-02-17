#!/usr/bin/env python3
"""
Benchmark semantic skill search with predefined test queries.

Measures search latency and relevance scores for each query.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nanobot.agent.skill_manager import SkillManager
from nanobot.memory.vector_manager import VectorDBManager


TEST_QUERIES = [
    "создай pull request",
    "найди баг в коде",
    "какая погода",
    "запланируй задачу на завтра",
    "summarize this article",
    "create a new skill",
    "check github issues",
    "take a screenshot",
    "set a reminder for 5pm",
    "explain this code",
]


def main() -> int:
    """Run benchmark and print results."""
    storage_dir = Path.home() / ".nanobot" / "skills"
    db_path = Path.home() / ".nanobot" / "chroma"
    db_manager = VectorDBManager(db_path)
    skill_manager = SkillManager(storage_dir, db_manager=db_manager)

    times_ms: list[float] = []
    top_scores: list[float] = []
    all_scores: list[float] = []

    print("\n--- Skill Search Benchmark ---\n")

    for query in TEST_QUERIES:
        t0 = time.perf_counter()
        results = skill_manager.search_skills(query, limit=5)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        times_ms.append(elapsed_ms)

        results_data = [
            {"skill_name": r.get("skill_name"), "score": round(r.get("score", 0), 4)}
            for r in results
        ]
        if results:
            top_scores.append(results[0].get("score", 0))
            all_scores.extend(r.get("score", 0) for r in results)

        metrics = {
            "event": "benchmark_search",
            "query": query,
            "elapsed_ms": round(elapsed_ms, 2),
            "results": results_data,
        }
        logger.info(json.dumps(metrics))

        print(f"Query: {query}")
        print(f"  Time: {elapsed_ms:.2f} ms")
        for r in results:
            print(f"  - {r.get('skill_name', '?')}: score={r.get('score', 0):.4f}")
        if not results:
            print("  - (no results)")
        print()

    # Summary table
    if times_ms:
        avg_ms = sum(times_ms) / len(times_ms)
        min_ms = min(times_ms)
        max_ms = max(times_ms)
        avg_relevance = sum(top_scores) / len(top_scores) if top_scores else 0
        avg_all = sum(all_scores) / len(all_scores) if all_scores else 0
    else:
        avg_ms = min_ms = max_ms = avg_relevance = avg_all = 0

    summary = {
        "event": "benchmark_summary",
        "queries_count": len(TEST_QUERIES),
        "min_ms": round(min_ms, 2),
        "max_ms": round(max_ms, 2),
        "avg_ms": round(avg_ms, 2),
        "avg_relevance_score_top1": round(avg_relevance, 4),
        "avg_relevance_score_all": round(avg_all, 4) if all_scores else 0,
    }
    logger.info(json.dumps(summary))

    print("--- Summary ---")
    print(f"  min_ms:           {min_ms:.2f}")
    print(f"  max_ms:           {max_ms:.2f}")
    print(f"  avg_ms:           {avg_ms:.2f}")
    print(f"  avg_relevance (top1): {avg_relevance:.4f}")
    print(f"  avg_relevance (all):  {avg_all:.4f}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
