"""Relevance harness — run a query set against all three backends and
compute precision-at-5 per category.

Usage:
    # Default: read queries.json from cwd, write RELEVANCE.md.
    python harness.py

    # Custom query set, custom output:
    python harness.py --queries my_queries.json --out my_relevance.md

The query set is JSON with shape:
    [
        {
            "query": "python async",
            "category": "multi-term",
            "expected_ids": [42, 117, 203, 891, 944]
        },
        ...
    ]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

try:
    from opensearchpy import AsyncOpenSearch
except ImportError:  # pragma: no cover
    AsyncOpenSearch = None  # type: ignore[assignment, misc]

try:
    from meilisearch_python_sdk import AsyncClient as MeiliAsyncClient
except ImportError:  # pragma: no cover
    MeiliAsyncClient = None  # type: ignore[assignment, misc]

from .clients import search_meili, search_opensearch, search_postgres
from .settings import Settings, get_settings


logger = logging.getLogger("crunchsearch.harness")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def precision_at_k(returned: list[int], expected: set[int], k: int = 5) -> float:
    """Fraction of the top-k returned IDs that are in the expected set."""
    top_k = returned[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for doc_id in top_k if doc_id in expected)
    return hits / k


def mean_reciprocal_rank(returned: list[int], expected: set[int]) -> float:
    """1 / (rank of first relevant result); 0 if none of the returned IDs is relevant."""
    for i, doc_id in enumerate(returned, start=1):
        if doc_id in expected:
            return 1.0 / i
    return 0.0


# ---------------------------------------------------------------------------
# Backend wrappers — convert SearchResponse dicts to id lists
# ---------------------------------------------------------------------------


async def run_postgres(pool: "asyncpg.Pool", query: str) -> list[int]:
    raw = await search_postgres(pool, query, limit=25, offset=0)
    return [hit["id"] for hit in raw["hits"]]


async def run_opensearch(client: "AsyncOpenSearch", index: str, query: str) -> list[int]:
    raw = await search_opensearch(client, index, query, limit=25, offset=0)
    return [hit["id"] for hit in raw["hits"]]


async def run_meili(client: "MeiliAsyncClient", index: str, query: str) -> list[int]:
    raw = await search_meili(client, index, query, limit=25, offset=0)
    return [hit["id"] for hit in raw["hits"]]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


async def evaluate(
    queries: list[dict[str, Any]],
    search_fn: Callable[[str], Awaitable[list[int]]],
) -> dict[str, dict[str, float]]:
    """Run every query through search_fn; return per-category p@5 and MRR."""
    by_category: dict[str, list[tuple[float, float]]] = {}
    for q in queries:
        returned = await search_fn(q["query"])
        expected = set(q["expected_ids"])
        p5 = precision_at_k(returned, expected, k=5)
        mrr = mean_reciprocal_rank(returned, expected)
        by_category.setdefault(q["category"], []).append((p5, mrr))

    out: dict[str, dict[str, float]] = {}
    for cat, pairs in by_category.items():
        if not pairs:
            continue
        avg_p5 = sum(p for p, _ in pairs) / len(pairs)
        avg_mrr = sum(m for _, m in pairs) / len(pairs)
        out[cat] = {"p_at_5": avg_p5, "mrr": avg_mrr, "n": float(len(pairs))}
    # Overall row.
    all_pairs = [p for pairs in by_category.values() for p in pairs]
    if all_pairs:
        out["overall"] = {
            "p_at_5": sum(p for p, _ in all_pairs) / len(all_pairs),
            "mrr":    sum(m for _, m in all_pairs) / len(all_pairs),
            "n":      float(len(all_pairs)),
        }
    return out


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def render_report(
    results: dict[str, dict[str, dict[str, float]]],
) -> str:
    """Build the RELEVANCE.md markdown body."""
    backends = list(results.keys())
    categories: list[str] = []
    for per_backend in results.values():
        for cat in per_backend:
            if cat not in categories:
                categories.append(cat)
    # Move "overall" to the end if present.
    if "overall" in categories:
        categories = [c for c in categories if c != "overall"] + ["overall"]

    lines: list[str] = ["# Search backend relevance", ""]
    lines.append("## Precision-at-5 by category")
    lines.append("")
    header = "| Category | " + " | ".join(backends) + " |"
    sep = "|---|" + "|".join(["---:"] * len(backends)) + "|"
    lines.append(header)
    lines.append(sep)
    for cat in categories:
        row = [cat]
        for backend in backends:
            entry = results[backend].get(cat)
            if entry is None:
                row.append("-")
            else:
                p5 = entry["p_at_5"]
                row.append(f"{p5:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Mean Reciprocal Rank (overall)")
    lines.append("")
    mrr_row = ["MRR"]
    for backend in backends:
        entry = results[backend].get("overall")
        mrr_row.append(f"{entry['mrr']:.3f}" if entry else "-")
    lines.append("| Metric | " + " | ".join(backends) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(backends)) + "|")
    lines.append("| " + " | ".join(mrr_row) + " |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def run_harness(
    queries_path: Path,
    out_path: Path,
    settings: Settings | None = None,
) -> None:
    """Run the harness end-to-end."""
    settings = settings or get_settings()
    queries = json.loads(queries_path.read_text())
    if not isinstance(queries, list):
        raise ValueError(f"{queries_path} must contain a JSON array of query objects")

    results: dict[str, dict[str, dict[str, float]]] = {}

    # Postgres
    if asyncpg is not None:
        pool = await asyncpg.create_pool(settings.postgres_dsn, min_size=1, max_size=4)
        if pool is not None:
            try:
                results["postgres"] = await evaluate(
                    queries, lambda q: run_postgres(pool, q)
                )
            finally:
                await pool.close()
    else:
        logger.warning("asyncpg not installed; skipping postgres")

    # OpenSearch
    if AsyncOpenSearch is not None:
        os_client = AsyncOpenSearch(
            hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
            http_auth=(settings.opensearch_user, settings.opensearch_pass),
            use_ssl=True, verify_certs=False, ssl_show_warn=False,
        )
        try:
            results["opensearch"] = await evaluate(
                queries,
                lambda q: run_opensearch(os_client, settings.opensearch_index, q),
            )
        finally:
            await os_client.close()
    else:
        logger.warning("opensearch-py not installed; skipping opensearch")

    # Meilisearch
    if MeiliAsyncClient is not None:
        async with MeiliAsyncClient(settings.meili_url, settings.meili_key) as meili_client:
            results["meili"] = await evaluate(
                queries,
                lambda q: run_meili(meili_client, settings.meili_index, q),
            )
    else:
        logger.warning("meilisearch-python-sdk not installed; skipping meili")

    report = render_report(results)
    out_path.write_text(report)
    logger.info("wrote %s (%d backends, %d queries)", out_path, len(results), len(queries))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run the relevance harness.")
    parser.add_argument("--queries", default="queries.json", help="Path to queries JSON.")
    parser.add_argument("--out", default="RELEVANCE.md", help="Path to write the report.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_harness(Path(args.queries), Path(args.out)))


if __name__ == "__main__":
    main()
