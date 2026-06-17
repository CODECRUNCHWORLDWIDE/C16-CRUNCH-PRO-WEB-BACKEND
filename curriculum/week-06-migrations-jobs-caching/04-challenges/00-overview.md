# Week 6 — Challenges

One stretch challenge this week, ~3 hours. Optional but recommended. The challenge is a full thumbnail-generation pipeline with three sizes, retries, idempotency, and a measurement of the worker's behaviour under concurrent load. It is the warm-up for the mini-project; doing the challenge first cuts the mini-project time roughly in half.

| # | Challenge | Time |
|---|-----------|-----:|
| 1 | [Image thumbnails async](./challenge-01-image-thumbnails-async.md) — three sizes, retries, idempotent, with concurrency measurement | ~3h |

Challenges are graded on the **completeness of the pipeline** and the **defensibility of the choices**. A submission that handles only one thumbnail size but explains its retry policy and idempotency guard well beats a three-size submission whose tasks are not idempotent.
