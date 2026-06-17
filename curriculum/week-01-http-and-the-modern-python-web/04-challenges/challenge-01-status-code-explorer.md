# Challenge 1 — Status Code Explorer

**Time estimate:** ~90 minutes.

## Problem statement

Build a single Python script `status_explorer.py` that, when run, deliberately triggers **at least one response from each major HTTP status code family**: `2xx`, `3xx`, `4xx`, and `5xx`. The script must:

1. Make all requests against a real, publicly accessible HTTPS service. You may use `https://httpbin.org` or `https://httpstat.us` — both are free, public, no signup, and exist for exactly this kind of testing.
2. Use only the Python standard library — no `requests`, no `httpx`. Use `http.client` or `urllib.request`.
3. For each response, print:
   - The URL requested
   - The HTTP method
   - The status code and reason phrase
   - The `Content-Type` of the response
   - The first 100 bytes of the body (or "(empty body)" if zero-length)
4. Group the output by status family with section headers.

## Acceptance criteria

- [ ] The script runs end-to-end with `python status_explorer.py` and produces output to stdout.
- [ ] Output includes at least one `2xx`, one `3xx`, one `4xx`, and one `5xx` response.
- [ ] At least 8 distinct status codes are triggered total.
- [ ] The script uses only `http.client` or `urllib.request` (no third-party HTTP libraries).
- [ ] The script handles network errors gracefully — if a request fails, the output says so and the script continues.
- [ ] The script does NOT crash on a `3xx` redirect (redirects must be observed, not followed automatically).
- [ ] You wrote a short `README.md` explaining what the script does and how to run it.
- [ ] Code is committed to your Week 1 GitHub repo.

## Stretch

- Add an `--only-family 4xx` CLI flag using `argparse` that filters by family.
- Add a `--save out.html` flag that writes the body of the first `200 OK` response to a file.
- Add a small test using `pytest` that mocks the HTTP responses with `unittest.mock` and verifies your output formatting.

## Hints

<details>
<summary>How to trigger an arbitrary status code on httpstat.us</summary>

`httpstat.us` is the simplest possible service. To trigger any code, request `https://httpstat.us/<code>`:

- `https://httpstat.us/200` returns `200 OK`
- `https://httpstat.us/301` returns `301 Moved Permanently`
- `https://httpstat.us/418` returns `418 I'm a teapot`
- `https://httpstat.us/503` returns `503 Service Unavailable`

You can pass any 3-digit code.

</details>

<details>
<summary>How to make HTTPS requests with `http.client`</summary>

```python
import http.client

conn = http.client.HTTPSConnection("httpstat.us")
conn.request("GET", "/418")
resp = conn.getresponse()
print(resp.status, resp.reason)
print(resp.headers.get("Content-Type"))
body = resp.read()
print(body[:100])
conn.close()
```

Note `HTTPSConnection` (with the S). For `urllib`, `urllib.request.urlopen("https://httpstat.us/418")` works but raises on 4xx/5xx; you need `try/except urllib.error.HTTPError` to inspect those.

</details>

<details>
<summary>How to NOT follow redirects</summary>

With `http.client.HTTPSConnection`, redirects are never auto-followed — you see the `3xx` directly. With `urllib.request`, you'd need to install a custom `HTTPRedirectHandler`. The `http.client` approach is simpler for this challenge.

</details>

## Submission

Commit `status_explorer.py` and `README.md` to your Week 1 GitHub repo under `challenges/challenge-01/`.

## Why this matters

Every Python web developer ends up using `requests` or `httpx` for real work. But your debugging instinct improves a lot when you've used the stdlib at least once. The day a corporate firewall blocks `pip install`, you'll thank yourself.
