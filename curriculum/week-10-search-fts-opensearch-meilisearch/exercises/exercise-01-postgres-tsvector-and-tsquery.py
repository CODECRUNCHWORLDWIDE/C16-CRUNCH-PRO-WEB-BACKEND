"""
Exercise 1 — Postgres FTS: build the tsvector column, run the four query
flavours, observe ts_rank_cd ordering.

Time:   ~1 hour.
Goal:   Take a small corpus of articles; load it into Postgres; build the
        tsvector generated column with weights A (title) and B (body); add
        the GIN index; run searches via to_tsquery, plainto_tsquery,
        phraseto_tsquery, and websearch_to_tsquery; compare ordering
        produced by ts_rank versus ts_rank_cd.

Run:
    # 1. Postgres reachable on localhost:5432 with a database named cc_w10.
    createdb cc_w10  # or use psql

    # 2. Apply the schema (the SQL exercise file builds the tables).
    psql -d cc_w10 -f exercise-05-postgres-fts.sql

    # 3. Run this Python script.
    python3 exercise-01-postgres-tsvector-and-tsquery.py

Try:
    Read the four blocks below — each demonstrates a different tsquery
    front-door. Run the script and read the output. Note which queries
    fail with syntax errors on user input (to_tsquery on a raw phrase)
    and which never fail (websearch_to_tsquery).

Cited:
    - https://www.postgresql.org/docs/current/textsearch.html
    - https://www.postgresql.org/docs/current/textsearch-controls.html
    - https://www.postgresql.org/docs/current/pgtrgm.html

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


logger = logging.getLogger("fts_exercise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


DSN = os.environ.get("CC_W10_DSN", "postgresql://postgres:postgres@localhost:5432/cc_w10")


# ---------------------------------------------------------------------------
# Part A — The seed corpus
# ---------------------------------------------------------------------------


SEED_ARTICLES: list[dict[str, Any]] = [
    {
        "title": "Python async generators",
        "body": (
            "Async generators in Python yield values lazily from an "
            "asynchronous iterator. The PEP 525 introduction explains "
            "the contract: an async generator is a coroutine that yields "
            "and resumes."
        ),
        "author": "Avrot, Laetitia",
        "tags": ["python", "async", "tutorial"],
    },
    {
        "title": "Asynchronous Django views",
        "body": (
            "Django supports asynchronous view handlers since 3.1. The "
            "ORM is still synchronous in most code paths; awaitable ORM "
            "wrappers are progressing. Write async views for IO-bound "
            "work."
        ),
        "author": "Manning, Christopher",
        "tags": ["django", "async", "tutorial"],
    },
    {
        "title": "FastAPI dependencies and Pydantic v2",
        "body": (
            "FastAPI's dependency injection composes with Pydantic v2 "
            "request validators. Generators as dependencies provide a "
            "teardown step; async generators provide an awaitable "
            "teardown."
        ),
        "author": "Avrot, Laetitia",
        "tags": ["fastapi", "pydantic", "tutorial"],
    },
    {
        "title": "Postgres full-text search",
        "body": (
            "Postgres ships tsvector and tsquery types, a GIN index, and "
            "the ts_rank and ts_rank_cd ranking functions. Use a "
            "generated column for tsvector to keep the index fresh."
        ),
        "author": "Bost, Craig",
        "tags": ["postgres", "search"],
    },
    {
        "title": "Build a search bar",
        "body": (
            "The user-facing search bar should accept a free-form query "
            "and return ranked results. Use websearch_to_tsquery for "
            "input from users; it is forgiving of operator-free text."
        ),
        "author": "Turnbull, Doug",
        "tags": ["search", "ux"],
    },
]


# ---------------------------------------------------------------------------
# Part B — Seed the corpus
# ---------------------------------------------------------------------------


async def seed_articles(pool: "asyncpg.Pool") -> None:
    """Insert the seed corpus, idempotently."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM articles_w10;")
        for art in SEED_ARTICLES:
            await conn.execute(
                """
                INSERT INTO articles_w10 (title, body, author, tags)
                VALUES ($1, $2, $3, $4);
                """,
                art["title"],
                art["body"],
                art["author"],
                art["tags"],
            )
        count = await conn.fetchval("SELECT count(*) FROM articles_w10;")
        logger.info("seeded %d articles", count)


# ---------------------------------------------------------------------------
# Part C — The four query front-doors
# ---------------------------------------------------------------------------


async def search_to_tsquery(pool: "asyncpg.Pool", q: str) -> list[dict[str, Any]]:
    """Strict boolean tsquery — & for AND, | for OR, ! for NOT."""
    sql = """
        SELECT id, title,
               ts_rank_cd(tsv, to_tsquery('english', $1), 32) AS score
        FROM articles_w10
        WHERE tsv @@ to_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, q)]


async def search_plainto_tsquery(pool: "asyncpg.Pool", q: str) -> list[dict[str, Any]]:
    """Plain text — splits on whitespace, ANDs the terms; never errors."""
    sql = """
        SELECT id, title,
               ts_rank_cd(tsv, plainto_tsquery('english', $1), 32) AS score
        FROM articles_w10
        WHERE tsv @@ plainto_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, q)]


async def search_phraseto_tsquery(pool: "asyncpg.Pool", q: str) -> list[dict[str, Any]]:
    """Phrase match — terms must appear adjacent and in order."""
    sql = """
        SELECT id, title,
               ts_rank_cd(tsv, phraseto_tsquery('english', $1), 32) AS score
        FROM articles_w10
        WHERE tsv @@ phraseto_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, q)]


async def search_websearch_to_tsquery(pool: "asyncpg.Pool", q: str) -> list[dict[str, Any]]:
    """Google-style — quotes for phrase, - for negation, OR for disjunction."""
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
# Part D — Compare ts_rank versus ts_rank_cd
# ---------------------------------------------------------------------------


async def compare_rankers(pool: "asyncpg.Pool", q: str) -> dict[str, list[dict[str, Any]]]:
    """Run the same query through both rankers; return both result sets."""
    sql_tf = """
        SELECT id, title,
               ts_rank(tsv, websearch_to_tsquery('english', $1)) AS score
        FROM articles_w10
        WHERE tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    sql_cd = """
        SELECT id, title,
               ts_rank_cd(tsv, websearch_to_tsquery('english', $1), 32) AS score
        FROM articles_w10
        WHERE tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        tf_rows = [dict(r) for r in await conn.fetch(sql_tf, q)]
        cd_rows = [dict(r) for r in await conn.fetch(sql_cd, q)]
    return {"ts_rank": tf_rows, "ts_rank_cd": cd_rows}


# ---------------------------------------------------------------------------
# Part E — Weighted ranking and ts_headline snippet
# ---------------------------------------------------------------------------


async def search_with_snippets(pool: "asyncpg.Pool", q: str) -> list[dict[str, Any]]:
    """Use ts_headline to return highlighted snippets alongside results."""
    sql = """
        SELECT id, title,
               ts_rank_cd(tsv, websearch_to_tsquery('english', $1), 32) AS score,
               ts_headline(
                   'english',
                   body,
                   websearch_to_tsquery('english', $1),
                   'StartSel=<em>,StopSel=</em>,MaxFragments=2,FragmentDelimiter=...'
               ) AS snippet
        FROM articles_w10
        WHERE tsv @@ websearch_to_tsquery('english', $1)
        ORDER BY score DESC
        LIMIT 25;
    """
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, q)]


# ---------------------------------------------------------------------------
# Part F — The driver
# ---------------------------------------------------------------------------


async def run_demo() -> None:
    """Drive the exercise: seed, search four ways, compare rankers, snippet."""
    if asyncpg is None:
        logger.error("asyncpg is not installed; install with: pip install asyncpg")
        return

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    if pool is None:  # pragma: no cover - asyncpg always returns a pool
        raise RuntimeError("could not open the pool")

    try:
        await seed_articles(pool)

        print("\n=== to_tsquery('python & async') — strict boolean ===")
        for row in await search_to_tsquery(pool, "python & async"):
            print(f"  {row['score']:.4f}  {row['title']}")

        print("\n=== plainto_tsquery('python async') — friendly default ===")
        for row in await search_plainto_tsquery(pool, "python async"):
            print(f"  {row['score']:.4f}  {row['title']}")

        print("\n=== phraseto_tsquery('python async generators') — phrase ===")
        for row in await search_phraseto_tsquery(pool, "python async generators"):
            print(f"  {row['score']:.4f}  {row['title']}")

        print("\n=== websearch_to_tsquery('\"python async\" -django') — Google-style ===")
        for row in await search_websearch_to_tsquery(pool, '"python async" -django'):
            print(f"  {row['score']:.4f}  {row['title']}")

        print("\n=== Compare ts_rank vs ts_rank_cd for 'python async' ===")
        compared = await compare_rankers(pool, "python async")
        print("  ts_rank:")
        for row in compared["ts_rank"]:
            print(f"    {row['score']:.4f}  {row['title']}")
        print("  ts_rank_cd:")
        for row in compared["ts_rank_cd"]:
            print(f"    {row['score']:.4f}  {row['title']}")

        print("\n=== Highlighted snippets ===")
        for row in await search_with_snippets(pool, "python async"):
            print(f"  {row['title']}")
            print(f"    {row['snippet']}")

        # TASK 1: Why does to_tsquery error on raw input like "python async"
        #         (no operator) but websearch_to_tsquery does not? Document
        #         in SOLUTIONS.md.

        # TASK 2: Reorder the corpus so the same query returns a different
        #         top-ranked result under ts_rank versus ts_rank_cd. The
        #         trick is to write one document where the terms appear far
        #         apart and another where they appear together. Document
        #         the trick in SOLUTIONS.md.

        # TASK 3: Run EXPLAIN ANALYZE on the websearch_to_tsquery query.
        #         Confirm "Bitmap Index Scan on articles_w10_tsv_idx".
        #         Then DROP INDEX articles_w10_tsv_idx; re-run; observe
        #         the Seq Scan and the timing delta.

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_demo())
