"""
Exercise 2 — pg_trgm: trigram similarity for typo-tolerant fallback.

Time:   ~1 hour.
Goal:   Install the pg_trgm extension; add the GIN trgm indexes; query
        with the % similarity operator; build the FTS-then-trigram
        fallback pattern.

Run:
    psql -d cc_w10 -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
    psql -d cc_w10 -f exercise-05-postgres-fts.sql  # if not already
    python3 exercise-02-pg-trgm-fuzzy-fallback.py

Try:
    Run the script. The first block searches "pythn async" via FTS
    (zero results — the misspelled token does not match any indexed
    lexeme). The second block searches the same string via trigram
    similarity (matches "python async" with similarity ~0.5). The
    third block runs the composite fallback (FTS first, trigram on
    empty).

Cited:
    - https://www.postgresql.org/docs/current/pgtrgm.html
    - https://www.postgresql.org/docs/current/textsearch-controls.html

The TASK comments below mark prompts you should answer in SOLUTIONS.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]


logger = logging.getLogger("trgm_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


DSN = os.environ.get("CC_W10_DSN", "postgresql://postgres:postgres@localhost:5432/cc_w10")


# ---------------------------------------------------------------------------
# Part A — Inspecting trigrams
# ---------------------------------------------------------------------------


async def show_trigrams(pool: "asyncpg.Pool", word: str) -> list[str]:
    """Return the trigram decomposition of a string via show_trgm()."""
    sql = "SELECT show_trgm($1) AS trigrams;"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, word)
        if row is None:
            return []
        return list(row["trigrams"])


async def similarity_score(pool: "asyncpg.Pool", a: str, b: str) -> float:
    """Compute the Jaccard trigram similarity between two strings."""
    sql = "SELECT similarity($1, $2) AS sim;"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, a, b)
        return float(row["sim"]) if row is not None else 0.0


# ---------------------------------------------------------------------------
# Part B — FTS-only (will return nothing for the misspelled query)
# ---------------------------------------------------------------------------


async def fts_only(pool: "asyncpg.Pool", q: str) -> list[dict[str, Any]]:
    """Strict FTS via websearch_to_tsquery; no fallback."""
    sql = """
        SELECT id, title,
               ts_rank_cd(tsv, websearch_to_tsquery('english', $1), 32) AS score
        FROM articles_w10
        WHERE tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, q)]


# ---------------------------------------------------------------------------
# Part C — Trigram similarity on title
# ---------------------------------------------------------------------------


async def trgm_only(pool: "asyncpg.Pool", q: str, threshold: float = 0.2) -> list[dict[str, Any]]:
    """Trigram-only fuzzy match on title with explicit threshold."""
    sql = """
        SELECT id, title,
               similarity(title, $1) AS score
        FROM articles_w10
        WHERE similarity(title, $1) >= $2
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, q, threshold)]


# ---------------------------------------------------------------------------
# Part D — The fallback composition
# ---------------------------------------------------------------------------


async def fts_with_trgm_fallback(
    pool: "asyncpg.Pool",
    q: str,
    fallback_threshold: int = 5,
) -> dict[str, Any]:
    """FTS first; on fewer than `fallback_threshold` hits, also run trigram."""
    fts_rows = await fts_only(pool, q)
    used_fallback = False
    if len(fts_rows) < fallback_threshold:
        trgm_rows = await trgm_only(pool, q, threshold=0.2)
        # Merge: keep FTS hits first (higher confidence), then trigram hits
        # that are not already in the FTS set.
        seen_ids = {r["id"] for r in fts_rows}
        merged = list(fts_rows)
        for r in trgm_rows:
            if r["id"] not in seen_ids:
                merged.append(r)
                seen_ids.add(r["id"])
        used_fallback = True
        return {"hits": merged, "used_fallback": used_fallback}
    return {"hits": fts_rows, "used_fallback": used_fallback}


# ---------------------------------------------------------------------------
# Part E — Diacritic-handling demonstration
# ---------------------------------------------------------------------------


async def show_unaccent_gap(pool: "asyncpg.Pool") -> None:
    """Demonstrate that trigram similarity treats accented and unaccented chars differently."""
    pairs: list[tuple[str, str]] = [
        ("Laetitia", "Lætitia"),
        ("cafe", "café"),
        ("naive", "naïve"),
    ]
    for a, b in pairs:
        sim = await similarity_score(pool, a, b)
        logger.info("similarity(%r, %r) = %.3f", a, b, sim)


# ---------------------------------------------------------------------------
# Part F — The driver
# ---------------------------------------------------------------------------


async def run_demo() -> None:
    """Drive the exercise: trigrams, FTS-only, trgm-only, composed fallback."""
    if asyncpg is None:
        logger.error("asyncpg is not installed; install with: pip install asyncpg")
        return

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    if pool is None:
        raise RuntimeError("could not open the pool")

    try:
        print("\n=== Trigram decomposition of 'python' ===")
        trigs = await show_trigrams(pool, "python")
        print(f"  {trigs}")

        print("\n=== similarity('python', 'pythn') ===")
        sim = await similarity_score(pool, "python", "pythn")
        print(f"  {sim:.3f}")

        print("\n=== FTS-only for 'pythn async' (misspelled) ===")
        rows = await fts_only(pool, "pythn async")
        print(f"  FTS returned {len(rows)} rows:")
        for row in rows:
            print(f"    {row['score']:.4f}  {row['title']}")

        print("\n=== Trigram-only for 'pythn async' ===")
        rows = await trgm_only(pool, "pythn async", threshold=0.2)
        print(f"  Trigram returned {len(rows)} rows:")
        for row in rows:
            print(f"    {row['score']:.4f}  {row['title']}")

        print("\n=== FTS-then-trigram fallback for 'pythn async' ===")
        result = await fts_with_trgm_fallback(pool, "pythn async", fallback_threshold=2)
        print(f"  Fallback used: {result['used_fallback']}")
        for row in result["hits"]:
            print(f"    {row['score']:.4f}  {row['title']}")

        print("\n=== Diacritic similarity ===")
        await show_unaccent_gap(pool)

        # TASK 1: Why does trigram similarity find "python" for the query
        #         "pythn" while FTS does not? Explain in SOLUTIONS.md in
        #         terms of the index data structures.

        # TASK 2: Pick a threshold that returns "python" for "pythn" but
        #         NOT "fastapi" for "pythn". Document your choice in
        #         SOLUTIONS.md with the similarity scores you measured.

        # TASK 3: The diacritic block shows similarity(Laetitia, Lætitia)
        #         is poor. Research the `unaccent` extension and describe
        #         how it would fix this — without code, in two sentences.

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_demo())
