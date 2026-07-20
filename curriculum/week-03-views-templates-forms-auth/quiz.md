# Week 3 — Quiz

Ten questions. Lectures closed.

---

**Q1.** A Django view is, at minimum:

- A) A subclass of `django.views.View`.
- B) A callable that takes an `HttpRequest` and returns an `HttpResponse`.
- C) A function decorated with `@view`.
- D) A class that defines `get()` and `post()`.

---

**Q2.** In a CBV URL pattern, `path("hi/", MyView.as_view())`, what does `as_view()` return?

- A) An instance of `MyView`.
- B) The `MyView` class.
- C) A callable (a view function) that instantiates `MyView` per request.
- D) An `HttpResponse`.

---

**Q3.** Why use `reverse_lazy` instead of `reverse` at class body scope?

- A) `reverse_lazy` is faster.
- B) `reverse_lazy` caches the result.
- C) `reverse` runs immediately; at class-definition time the URL conf may not be loaded, so it raises.
- D) They are interchangeable; `reverse_lazy` is just an alias.

---

**Q4.** In a Django template, where must `{% extends "base.html" %}` appear?

- A) Anywhere in the file.
- B) The first non-comment line.
- C) Inside a `{% block %}`.
- D) At the bottom.

---

**Q5.** Cross-field validation (one field depends on another) belongs in:

- A) `clean_<fieldname>()`.
- B) `__init__()`.
- C) `clean()`.
- D) The model's `save()`.

---

**Q6.** After `article = form.save(commit=False)` on a `ModelForm` with M2M fields, what must you call after `article.save()`?

- A) `form.save_m2m()`.
- B) `form.save(commit=True)`.
- C) Nothing — `save()` handles M2M.
- D) `article.save_m2m()`.

---

**Q7.** What does the `sessionid` cookie contain?

- A) The user's hashed password.
- B) A signed payload including the user's ID and the time of login.
- C) A random key that identifies a row in the `django_session` table on the server.
- D) The user's permissions, JSON-encoded.

---

**Q8.** A logged-in user POSTs a form without `{% csrf_token %}` inside it. What happens?

- A) The form submits normally; the session cookie is enough.
- B) Django returns 403 from `CsrfViewMiddleware`.
- C) Django returns 400 because the form is malformed.
- D) Django returns 401 because authentication failed.

---

**Q9.** In `class MyView(LoginRequiredMixin, ListView):` — why must `LoginRequiredMixin` come first?

- A) Convention; it's not required.
- B) The MRO calls `dispatch()` left to right; if the generic runs first, the auth check never gates the request.
- C) `ListView` raises if mixed with anything after it.
- D) Django sorts the bases alphabetically at runtime.

---

**Q10.** A logged-in user tries to edit another user's article via `/dashboard/<their_pk>/edit/`. The view does `get_queryset(): return Article.objects.filter(author=request.user)`. The user sees:

- A) 403 Forbidden.
- B) 404 Not Found.
- C) 401 Unauthorized.
- D) The edit form — the filter is bypassed.

---

## Answer key

<details>
<summary>Reveal</summary>

1. **B** — A callable that takes `HttpRequest` and returns `HttpResponse`. Everything else is sugar.
2. **C** — `as_view()` returns a callable that instantiates the class per request and dispatches.
3. **C** — At class-definition time the URL conf isn't necessarily loaded. `reverse_lazy` defers evaluation.
4. **B** — `{% extends %}` must be the first non-comment line; anything before it breaks the inheritance.
5. **C** — `clean_<field>()` cannot see other fields reliably; `clean()` sees all of `cleaned_data`.
6. **A** — With `commit=False`, M2M cannot persist until the instance has a PK; you must call `form.save_m2m()` after `save()`.
7. **C** — The cookie holds a random session key; the session row in the DB is where the data lives.
8. **B** — `CsrfViewMiddleware` rejects the POST with 403.
9. **B** — MRO is left-to-right; the auth check must fire before the generic's dispatch.
10. **B** — 404. The queryset filters out the article entirely, so `get_object_or_404` doesn't find it. 404 leaks less information than 403.

</details>

If 9+: ship the homework. 7-8: re-read the relevant lecture. <7: re-read Lecture 1 from the top, then come back to this quiz before homework.
