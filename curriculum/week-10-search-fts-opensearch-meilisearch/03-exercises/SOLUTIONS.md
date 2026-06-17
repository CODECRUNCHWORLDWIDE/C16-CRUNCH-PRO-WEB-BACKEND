# Exercise solutions — Week 10

Worked solutions for the four `.py` exercises and the `.sql` exercise, with explanations for the trickier lines. Read these only after you have made a real attempt at the exercises; the value is in the struggle, not the answer.

---

## Exercise 1 — `tsvector` and `tsquery`

### Task 1 — why does `to_tsquery` error on raw input?

`to_tsquery('english', 'python async')` parses its first argument *as a `tsquery` expression* — meaning it expects boolean operators (`&`, `|`, `!`, `<->`, etc.) between terms. A bare whitespace-separated phrase like `python async` is a *syntax error* for `to_tsquery` because the parser sees no operator between `python` and `async`.

`websearch_to_tsquery('english', 'python async')` parses its first argument as a *user-facing search string*: whitespace between terms is implicit `AND`; quotes denote phrases; `-` denotes negation; `OR` (uppercase) denotes disjunction. The parser never errors on plain text — it always produces a valid `tsquery`.

**Rule of thumb**: never pass user input directly to `to_tsquery`. Use `websearch_to_tsquery` (Google-style) or `plainto_tsquery` (naive whitespace-AND). Reserve `to_tsquery` for queries constructed in code from validated inputs.

### Task 2 — making `ts_rank` and `ts_rank_cd` disagree

The key difference: `ts_rank` rewards term frequency; `ts_rank_cd` rewards term proximity. Construct two documents:

- **Doc A** (proximity-heavy): "Python async generators yield lazily." The terms `python` and `async` are adjacent.
- **Doc B** (frequency-heavy): "Python is a language. Async is a keyword. Python loops. Async functions. Python again. Async again." The terms `python` and `async` appear repeatedly but always at least one word apart.

`ts_rank` ranks Doc B higher (more occurrences). `ts_rank_cd` ranks Doc A higher (terms within 2 tokens of each other).

Add both to the corpus, query for `python async` under both rankers, and compare. The reordering demonstrates the trade-off.

### Task 3 — `EXPLAIN ANALYZE` and the `Seq Scan` collapse

With the index in place:

```text
Bitmap Heap Scan on articles_w10  (cost=4.27..15.20 rows=N width=...) (actual time=0.02..0.04 ms)
  ->  Bitmap Index Scan on articles_w10_tsv_idx  (cost=0.00..4.26 rows=N width=0) (actual time=0.01..0.01 ms)
        Index Cond: (tsv @@ '...'::tsquery)
```

After `DROP INDEX articles_w10_tsv_idx`:

```text
Seq Scan on articles_w10  (cost=0.00..16.30 rows=N width=...) (actual time=0.05..0.15 ms)
  Filter: (tsv @@ '...'::tsquery)
```

On the 5-row seed corpus, the difference is invisible (microseconds either way). Repeat on a 100 000-row corpus and the gap opens to two-to-three orders of magnitude. Postgres FTS without the `GIN` index is `O(n)` over the table — fine for development, fatal for production.

---

## Exercise 2 — `pg_trgm` fallback

### Task 1 — why does trigram find `python` for `pythn` but FTS does not?

FTS tokenises documents into *lexemes* at write time. The lexeme `python` is in the index. The query `pythn` tokenises to the lexeme `pythn` (after stemming, which leaves the misspelled token unchanged because it does not match an English rule). The lexeme `pythn` is not in the index; FTS returns zero results.

Trigram similarity does not tokenise into words. It decomposes the entire string into 3-character windows: `python` produces `{  p,  py, pyt, yth, tho, hon, on }`; `pythn` produces `{  p,  py, pyt, yth, thn, hn }`. Three trigrams overlap (`  p`, ` py`, `pyt`, `yth` — actually four out of seven). The Jaccard similarity ≈ `4/9 ≈ 0.44`, comfortably above the default `0.3` threshold.

The FTS data structure is *lexeme-aware* but *character-blind*. The trigram data structure is the opposite. The composition uses each for what it is good at.

### Task 2 — picking the threshold

Measure first. For each candidate query/document pair:

```sql
SELECT similarity('pythn', 'python');   -- ~0.44
SELECT similarity('pythn', 'fastapi');  -- ~0.10
SELECT similarity('pythn', 'postgres'); -- ~0.06
```

A threshold of `0.3` (the default) is fine — it admits `python` but rejects `fastapi` and `postgres`. Lower thresholds (`0.1`) start admitting noise. Higher thresholds (`0.5`) start excluding valid matches.

For two-word queries like `pythn async`, the trigram similarity is computed against the whole title string. `similarity('pythn async', 'Python async generators')` ≈ `0.34` — just above the default. Tighten or loosen empirically; never set the threshold without running it against a representative query set.

### Task 3 — `unaccent` in two sentences

The `unaccent` extension provides a function `unaccent(text)` that strips diacritics: `unaccent('Lætitia')` → `Laetitia`, `unaccent('café')` → `cafe`. The fix is to index `unaccent(title)` and search against `unaccent(query)` — both sides normalised, the similarity is computed on the diacritic-free strings, and `similarity('Lætitia', 'Laetitia')` becomes ≈ `1.0`.

---

## Exercise 3 — OpenSearch

### Task 1 — `_analyze` output for the custom analyzer

```python
result = await client.indices.analyze(
    index=INDEX,
    body={"analyzer": "crunch_english", "text": "Asynchronous generators are running"},
)
# result["tokens"]:
# [{"token": "asynchron", ...}, {"token": "gener", ...}, {"token": "run", ...}]
```

Three tokens. `are` is dropped (stop word). `Asynchronous` is lowercased to `asynchronous` and then stemmed to `asynchron`. `generators` becomes `gener`. `running` becomes `run`. The stop-word + stem chain produces a tight, normalised representation; the index stores three terms for a five-word input.

### Task 2 — `match` vs `match_phrase`

Add documents:

- **Doc X**: "Python is great. Async is also great." (Terms scattered.)
- **Doc Y**: "Python async makes IO non-blocking." (Terms adjacent.)

`match: "python async"` scores Doc X and Doc Y both highly (both contain both terms). The exact ordering depends on BM25 (term frequency, document length). `match_phrase: "python async"` returns only Doc Y, because only Doc Y contains the phrase in order with no other tokens between.

`match` is recall-friendly; `match_phrase` is precision-strict. For most user-facing search, `match` (or `multi_match` of type `best_fields`) is the right default; surface `match_phrase` behind a quoted-string convention in the UI.

### Task 3 — per-field BM25 tuning

Create a second index:

```python
INDEX_BODY_V2["settings"]["similarity"] = {
    "title_bm25": {"type": "BM25", "k1": 0.5, "b": 0.0},
}
INDEX_BODY_V2["mappings"]["properties"]["title"]["similarity"] = "title_bm25"
```

`k1=0.5` saturates term frequency fast (the 2nd occurrence adds little). `b=0.0` disables length normalisation. For short titles, both are sensible because (a) the same word twice in a 4-word title rarely means "more relevant", and (b) length normalisation punishes short titles arbitrarily.

Index the same documents into both indexes; query both for `python`. The top-1 results will often agree (BM25 is robust); the *relative* scores differ; the *ordering* changes only when the corpus has documents that are close in the default scoring. The harness from Exercise 4 / Challenge 1 is the right tool to confirm whether your tuning helped or hurt.

---

## Exercise 4 — Meilisearch

### Task 1 — `oneTypo` threshold trade-off

Lowering `minWordSizeForTypos.oneTypo` from `5` to `3` admits typos in shorter words. Run the seed and query `cat`:

- At `5`: `cat` (3 chars) does not allow any typo; the query `cat` only matches documents containing `cat` exactly.
- At `3`: `cat` (3 chars) allows one typo; the query `cat` now also matches `bat`, `car`, `cap`, etc.

The trade-off: at `3`, recall is much higher; precision drops sharply for short queries. A user typing `cat` and getting "bat" results is unhappy. The default `5` is calibrated for English where 4-character common words (`bat`, `cap`, etc.) are common enough that one-typo distance produces noise.

### Task 2 — reordering `searchableAttributes`

Default `["title", "body"]`: titles rank higher. The `attribute` ranking rule looks at *which field* a query term matched first; earlier-listed attributes count more.

Switching to `["body", "title"]`: body matches now outrank title matches at the `attribute` tiebreaker stage. For a query like `python` (which matches both fields in most articles), the top-1 result becomes the article with the most-relevant *body* mention, not the one with `python` in the title.

The lesson: `searchableAttributes` order is a *relevance lever*, not a neutral configuration. For most products, "title first" is right because titles are curated; body text is incidental.

### Task 3 — disabling typo tolerance

Set `typoTolerance.enabled = False` and re-run `pythn async`:

- With typo: returns documents matching `python async` (because `pythn` is corrected to `python` within Damerau-Levenshtein distance 1).
- Without typo: returns zero results, because `pythn` is not a token in any indexed document.

Whether typo tolerance is "essential" or "optional" depends on the product. For a search bar where users type fast and misspell often (mobile apps, internal search, product search), typo tolerance is essential. For a query language where users build precise queries deliberately (admin tools, log search, internal CLI), typo tolerance is wrong — `pythn` should be a zero-result query, not a near-match.

---

## Exercise 5 — the SQL schema

### Choice notes

- **`STORED` generated column over `VIRTUAL`**. `STORED` materialises the `tsvector` to disk on every write; `VIRTUAL` (in newer Postgres) recomputes on read. For FTS where reads are far more frequent than writes, `STORED` is correct.
- **Weights `A` on title, `B` on body**. The default `ts_rank` weight vector is `{0.1, 0.2, 0.4, 1.0}` for `{D, C, B, A}`. Title-`A` matches count ten times as much as body-`D` matches, four times as much as body-`B`. Tunable per call via the `weights` argument to `ts_rank`.
- **`GIN` over `GiST`**. For an article corpus that updates infrequently (compared to reads), `GIN` is correct. Switch to `GiST` only if you observe sustained `UPDATE` pressure on the `tsv` column.
- **Trigram index on `title` but not `body`**. Body trigram indexes are large (a 5 KB body produces ~5 000 trigrams). Enable selectively after the harness shows you need fuzzy body matching.

### Verification queries (uncomment as you work)

The block under "Sample queries" in the SQL file demonstrates each pattern. Uncomment and run after seeding (via Exercise 1) to confirm the index is being used.
