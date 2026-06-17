# Week 10 — Quiz

Ten questions. Lectures closed. One correct answer per question; the answer key is at the end.

---

**Q1.** In Postgres, `to_tsvector('english', 'The quick brown fox jumps')` produces:

- A) Five lexemes, one per input word, preserving original case.
- B) Five lexemes, all lowercased, with `the` stemmed.
- C) Four lexemes after stop-word removal: `'brown'`, `'fox'`, `'jump'`, `'quick'`.
- D) Five lexemes including `'the'`, because stop-word removal happens at query time.

---

**Q2.** Which Postgres `tsquery` function should accept user input from a search bar?

- A) `to_tsquery` — strict syntax catches errors early.
- B) `plainto_tsquery` — splits on whitespace and ANDs the tokens.
- C) `phraseto_tsquery` — forces phrase matching to avoid loose recall.
- D) `websearch_to_tsquery` — supports quoted phrases, `-` for negation, `OR` for disjunction, and never errors on plain text.

---

**Q3.** `CREATE INDEX articles_tsv_idx ON articles USING GIN (tsv);` is the right choice when:

- A) The `tsv` column is updated more often than queried; `GIN` is write-optimised.
- B) The `tsv` column is queried more often than updated; `GIN` is read-optimised with `O(log n)` lookups.
- C) The corpus is small enough that any index suffices.
- D) The `tsv` column must be unique.

---

**Q4.** The `pg_trgm` extension's `%` operator returns `true` when:

- A) Two strings share at least one character.
- B) The trigram similarity (Jaccard over 3-character windows) is above the default threshold (~0.3).
- C) The Levenshtein edit distance is at most 2.
- D) The strings match after lowercasing and stop-word removal.

---

**Q5.** OpenSearch's default scorer is:

- A) `ts_rank_cd` from Postgres.
- B) BM25 — a probabilistic relevance score with tunable `k1` (term-frequency saturation) and `b` (length normalisation).
- C) Cosine similarity over TF-IDF vectors.
- D) PageRank-style link analysis.

---

**Q6.** In OpenSearch's `bool` query, the `filter` clause:

- A) Must match; contributes to the relevance score.
- B) Must match; does not contribute to the score and is cached.
- C) Must not match; subtracts from the relevance score.
- D) May match; boosts the score if it does.

---

**Q7.** Meilisearch's six default ranking rules, in order, are:

- A) `relevance`, `recency`, `proximity`, `popularity`, `exactness`, `attribute`.
- B) `words`, `typo`, `proximity`, `attribute`, `sort`, `exactness`.
- C) `bm25`, `phrase`, `typo`, `field_boost`, `sort`, `exact_match`.
- D) `tf`, `idf`, `proximity`, `attribute`, `sort`, `exactness`.

---

**Q8.** Meilisearch's default typo tolerance allows:

- A) One typo for words ≥ 4 characters; two typos for words ≥ 8 characters.
- B) One typo for words ≥ 5 characters; two typos for words ≥ 9 characters.
- C) Up to three typos for any word.
- D) No typos by default; typo tolerance is opt-in.

---

**Q9.** The "alias swap" reindex pattern in OpenSearch works because:

- A) Aliases are reference-counted; the swap atomically increments the new index and decrements the old.
- B) The `update_aliases` API applies all `remove`/`add` actions atomically — there is no observable in-between state.
- C) OpenSearch internally pauses search traffic during alias updates.
- D) The pattern requires a brief downtime window; "zero downtime" is marketing.

---

**Q10.** A search backend returned `[42, 117, 8, 99, 21, 14, 3, 67]` for the query "python async". The hand-labelled expected top-5 is `{42, 117, 203, 891, 944}`. Precision-at-5 for this query is:

- A) 0.2 (one match in the top 5; 1/5 = 0.2)
- B) 0.4 (two matches: 42 and 117)
- C) 0.5 (the first match was at rank 1)
- D) 0.8 (eight returned, two matched)

---

## Answer key

| Question | Answer | Lecture / reference |
|---:|:---|:---|
| Q1 | C | Lecture 1 §2 — the `english` configuration drops stop words (`the`) and stems (`jumps` → `jump`). |
| Q2 | D | Lecture 1 §3 — `websearch_to_tsquery` is the user-input-safe choice. |
| Q3 | B | Lecture 1 §2.2 — `GIN` is read-optimised; right for tsvector columns. |
| Q4 | B | Lecture 1 §6.1 — trigram similarity above ~0.3 (configurable). |
| Q5 | B | Lecture 2 §4 — BM25 is the default scorer. |
| Q6 | B | Lecture 2 §5.2 — `filter` must match, no score contribution, cached. |
| Q7 | B | Lecture 3 §3 — the six default rules in canonical order. |
| Q8 | B | Lecture 3 §5 — defaults of `minWordSizeForTypos`. |
| Q9 | B | Lecture 3 §6.2 + Challenge 2 — `update_aliases` is atomic. |
| Q10 | B | Lecture 3 §7 — precision-at-5 = 2 of top-5 in expected = 2/5 = 0.4. |
