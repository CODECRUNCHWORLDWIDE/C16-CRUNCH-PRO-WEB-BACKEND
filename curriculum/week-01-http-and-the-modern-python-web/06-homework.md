# Week 1 Homework

Six practice problems that revisit the week's topics. The full set should take about **6 hours** in total. Work in your Week 1 Git repository so each problem produces at least one commit you can point to later.

Each problem includes:

- A short **problem statement**.
- **Acceptance criteria** so you know when you're done.
- A **hint** if you get stuck.
- An **estimated time**.

---

## Problem 1 — Read the headers of three real sites

**Problem statement.** Pick three websites you actually use (your university, a personal site, a major SaaS). For each, use `curl -sI` (capital-i, "head") to fetch only the response headers. Save the output of each into a file in `notes/headers/<site>.txt`.

**Acceptance criteria.**

- Three files exist under `notes/headers/`, one per site, each containing real header output.
- Add a `notes/headers/README.md` that lists, for each site:
  - Server software (the `Server:` header, if present)
  - Whether the response was compressed (`Content-Encoding`)
  - Whether `Strict-Transport-Security` is set
  - Whether `Cache-Control` is set, and what its policy is
- Commit all four files.

**Hint.** `curl -sI https://example.com` gets you headers only. If you also want to see the request curl is sending, use `curl -sIv https://example.com`.

**Estimated time.** 30 minutes.

---

## Problem 2 — Categorize 20 status codes

**Problem statement.** Create a Python script `categorize.py` that, given a list of 20 status codes, prints each one and its family (`Informational`, `Success`, `Redirection`, `Client Error`, `Server Error`) and a one-line plain-English meaning of that specific code.

**Acceptance criteria.**

- `python categorize.py` runs with no command-line arguments.
- It prints exactly 20 lines of output, one per status code.
- The 20 codes must include at least one from each family.
- The mapping must use a `dict` or `match`-`case`, not 20 `if/elif` branches.
- The script handles unknown codes gracefully ("Unknown status code").
- Code is committed.

**Hint.** `http.HTTPStatus.OK.phrase` gives you `"OK"`. `http.HTTPStatus(404).phrase` gives `"Not Found"`. Build the family from the first digit: `code // 100`.

**Estimated time.** 45 minutes.

---

## Problem 3 — Build a tiny WSGI middleware

**Problem statement.** Extend `exercises/exercise-03-wsgi-hello-world.py` by adding a **logging middleware** that wraps the app and prints, for each request, a line like:

```
[2026-05-13 14:00:01] GET /json -> 200 (78 bytes, 1.3 ms)
```

The middleware must:

- Not modify the response.
- Measure elapsed time accurately (use `time.perf_counter`).
- Log to stdout.
- Be re-usable as a wrapper around any WSGI app.

**Acceptance criteria.**

- A new file `homework/p3_logging_middleware.py` exists.
- Running it starts the same server, but every request prints a log line.
- The log line includes timestamp, method, path, status code, body size, and milliseconds.
- The original `app(environ, start_response)` is unmodified — the middleware wraps it.
- Code is committed.

**Hint.** A WSGI middleware is just another WSGI app that calls the inner app inside it. Wrap `start_response` so you can capture the status code before the body bytes flow through.

**Estimated time.** 1 hour.

---

## Problem 4 — Compare Django, Flask, FastAPI in 500 words

**Problem statement.** Write a short essay, `notes/framework-comparison.md`, that compares Django, Flask, and FastAPI on five criteria of your choice. Each criterion must include one *concrete code example* showing what the same task looks like in each framework. Suggested criteria:

- How do you define a simple "hello world" route?
- How do you read a query parameter (`?name=ada`)?
- How do you read a JSON body?
- How do you return JSON?
- How do you write a 404 response?

**Acceptance criteria.**

- The file is at `notes/framework-comparison.md`.
- 400–600 words plus 5 code blocks per framework (15 total).
- Each code block is short — under 10 lines.
- Code blocks are syntactically correct (you don't have to *run* them, but they must compile).
- The essay ends with a one-paragraph "which would I pick for ___?" answer for three scenarios *you* invent.
- Committed.

**Hint.** Borrow from the official docs:
- Django: <https://docs.djangoproject.com/en/stable/intro/tutorial01/>
- Flask: <https://flask.palletsprojects.com/en/stable/quickstart/>
- FastAPI: <https://fastapi.tiangolo.com/tutorial/first-steps/>

**Estimated time.** 1 hour 15 minutes.

---

## Problem 5 — Install and tour `httpie`

**Problem statement.** Install [HTTPie](https://httpie.io/) (`pip install httpie`) and use it to:

1. Make a `GET` request to `https://httpbin.org/get` with a custom header `X-Course: c16`.
2. Make a `POST` request to `https://httpbin.org/post` with a JSON body `{"name": "ada", "skill": 9.5}`.
3. Make the same `POST` again with `--verbose`, capturing the raw HTTP request to a file `notes/httpie-raw-request.txt`.

**Acceptance criteria.**

- A file `notes/httpie-raw-request.txt` exists and contains the raw HTTP request (request-line, headers, blank line, body).
- A file `notes/httpie-output.md` exists, contains the three commands you ran, and one paragraph for each describing what the response was.
- Both files committed.

**Hint.** `http POST httpbin.org/post name=ada skill:=9.5` — `name=` for strings, `skill:=` for non-string JSON values. `http --verbose` shows the raw request.

**Estimated time.** 45 minutes.

---

## Problem 6 — Mini reflection essay

**Problem statement.** Write a 300–400 word reflection at `notes/week-01-reflection.md` answering:

1. Of HTTP, WSGI, and the framework landscape — which felt easiest? Which felt hardest? Why?
2. Did anything you previously believed about web frameworks turn out to be wrong this week? If so, what?
3. Which framework would you reach for first for a personal project, and why?
4. What's one thing you'd want to learn next that this week didn't cover?

**Acceptance criteria.**

- File exists, 300–400 words.
- Each numbered question is addressed in its own paragraph.
- File is committed.

**Hint.** This is for *you*, not for a grade. Be honest. Future-you reading it after Week 12 will be grateful.

**Estimated time.** 30 minutes.

---

## Time budget recap

| Problem | Estimated time |
|--------:|--------------:|
| 1 | 30 min |
| 2 | 45 min |
| 3 | 1 h 0 min |
| 4 | 1 h 15 min |
| 5 | 45 min |
| 6 | 30 min |
| **Total** | **~5 h 45 min** |

When you've finished all six, push your repo and open the [mini-project](./07-mini-project/00-overview.md).
