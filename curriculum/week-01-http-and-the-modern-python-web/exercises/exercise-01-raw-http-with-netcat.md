# Exercise 1 — Raw HTTP with `nc`

**Goal:** Make an HTTP request by typing it, line by line, into a TCP socket. No browser, no `curl`, no library. Just you and the bytes.

**Estimated time:** 25 minutes.

---

## Setup

You need `nc` (netcat).

- **macOS:** preinstalled. Try `nc -h` to confirm.
- **Linux:** `sudo apt install netcat-openbsd` if missing.
- **Windows:** install via [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and use Ubuntu's `nc`, or download `ncat` from [Nmap](https://nmap.org/ncat/).

You also need a web server you're allowed to talk to. We'll use `example.com`, which exists for exactly this purpose ([RFC 2606](https://www.rfc-editor.org/rfc/rfc2606)).

---

## Step 1 — Connect

Open your terminal and type:

```bash
nc example.com 80
```

That opens a TCP connection to port 80 (the plain HTTP port). Your terminal will appear to hang — that's correct. `nc` is waiting for you to type something.

> **Why port 80, not 443?** Port 443 is HTTPS, and HTTPS adds a TLS handshake before the HTTP starts. We can't type TLS bytes by hand. So we use plain HTTP for this exercise. **Don't worry that the page might be insecure** — `example.com` exists for testing and serves the same content over both.

---

## Step 2 — Type a request

In your hung terminal, type the following **exactly**. Each line ends with the Enter key.

```
GET / HTTP/1.1
Host: example.com
Connection: close

```

That's three lines of content and one blank line. The blank line is what tells the server "I'm done with headers, please respond."

You should see the server respond with a status line, headers, blank line, and HTML.

---

## Step 3 — Read what came back

The output will look something like:

```
HTTP/1.1 200 OK
Age: 12345
Cache-Control: max-age=604800
Content-Type: text/html; charset=UTF-8
Date: ...
Last-Modified: ...
...

<!doctype html>
<html>
<head>
    <title>Example Domain</title>
...
```

Identify each part:

1. The status-line.
2. The response headers, line by line.
3. The blank line that separates headers from body.
4. The first few lines of the HTML body.

---

## Step 4 — Make it fail (deliberately)

The `Host` header is the only required HTTP/1.1 header. Try omitting it:

```bash
nc example.com 80
```

Then type:

```
GET / HTTP/1.1
Connection: close

```

Most production servers will respond with `400 Bad Request`. That tells you the server *did* parse your request, *did* recognize the version as HTTP/1.1, and *did* enforce the `Host` requirement. Read the response.

---

## Step 5 — Inspect a `HEAD` request

`HEAD` is identical to `GET` except the server only returns headers, no body. Useful for "does this URL exist?" without downloading the content.

```bash
nc example.com 80
```

```
HEAD / HTTP/1.1
Host: example.com
Connection: close

```

You should see the same status line and headers as before, but no HTML.

---

## Step 6 — A `POST` (will likely 405)

`example.com` doesn't accept POSTs. But you can still send one and see what the server says.

```bash
nc example.com 80
```

```
POST /submit HTTP/1.1
Host: example.com
Connection: close
Content-Type: text/plain
Content-Length: 13

hello, world!
```

Two important things:

- The body comes after the blank line that ends headers.
- The `Content-Length: 13` matches exactly the byte count of `hello, world!` (including no trailing newline). If you set it wrong, the server will either truncate your body or hang waiting for more bytes.

Most likely you'll get a `405 Method Not Allowed`. That's expected — the *point* is to see your request reach the server and elicit a real response.

---

## Acceptance criteria

You can mark this exercise done when:

- [ ] You've made at least 3 successful `GET` requests to `example.com` by hand with `nc`.
- [ ] You can identify the request-line, headers, blank line, and body in your request.
- [ ] You can identify the status-line, headers, blank line, and body in the response.
- [ ] You've deliberately triggered a `400 Bad Request` and read the response.
- [ ] You've made a `HEAD` request and observed there's no body.
- [ ] You can explain, in your own words, why the `Host` header is required in HTTP/1.1.

---

## Stretch

- Try the same thing against another site you control or that explicitly allows it (your own personal site is the best target).
- Use `nc -l 8000` in one terminal to listen on port 8000, then in another terminal run `curl http://localhost:8000`. Read what `curl` sent.
- Try sending two `GET`s on the same connection by replacing `Connection: close` with `Connection: keep-alive`. Watch the second response come through the same socket.

---

## Hints

<details>
<summary>If your request hangs forever</summary>

You probably forgot the blank line at the end. HTTP messages end with two consecutive `\r\n`s. In `nc` that's: header line, Enter, header line, Enter, Enter.

</details>

<details>
<summary>If you get connection refused</summary>

Check the domain (`example.com`, not `example.com.`) and the port (`80` for HTTP). If you're behind a corporate proxy or VPN, port 80 outbound may be blocked — try from a personal hotspot or a different network.

</details>

<details>
<summary>If you get "Bad Request" every time</summary>

Common causes:
- Forgot `Host:` header
- Typo in `HTTP/1.1` (case sensitive; not `Http/1.1` or `HTTP/1.0`)
- Extra space in the request-line
- Using LF only instead of CRLF — most servers tolerate it, some don't. `nc` typically converts your Enter to the right line ending, but `nc -C` (or `nc -c`) forces CRLF on Linux.

</details>

---

When this exercise feels comfortable, move to [Exercise 2 — A stdlib HTTP server](exercise-02-stdlib-server.py).
