# Week 3 — Resources

All free and publicly accessible. Pin Django 5.x: every link below is `/en/stable/`, which currently resolves to the 5.x docs.

## Required reading (work through the week)

- **Writing views** — the introductory view docs:
  <https://docs.djangoproject.com/en/stable/topics/http/views/>
- **URL dispatcher** — `path()`, `include()`, named URLs, `reverse()`:
  <https://docs.djangoproject.com/en/stable/topics/http/urls/>
- **Class-based views — topic guide** (read end-to-end at least once):
  <https://docs.djangoproject.com/en/stable/topics/class-based-views/>
- **Generic display views** (`ListView`, `DetailView`):
  <https://docs.djangoproject.com/en/stable/ref/class-based-views/generic-display/>
- **Generic editing views** (`CreateView`, `UpdateView`, `DeleteView`, `FormView`):
  <https://docs.djangoproject.com/en/stable/ref/class-based-views/generic-editing/>
- **The Django Template Language**:
  <https://docs.djangoproject.com/en/stable/ref/templates/language/>
- **Built-in template tags and filters**:
  <https://docs.djangoproject.com/en/stable/ref/templates/builtins/>
- **Forms — topic guide**:
  <https://docs.djangoproject.com/en/stable/topics/forms/>
- **Forms — `ModelForm`**:
  <https://docs.djangoproject.com/en/stable/topics/forms/modelforms/>
- **User authentication in Django**:
  <https://docs.djangoproject.com/en/stable/topics/auth/>
- **Using the Django authentication system** — sessions, decorators, the views that ship:
  <https://docs.djangoproject.com/en/stable/topics/auth/default/>
- **Cross Site Request Forgery protection**:
  <https://docs.djangoproject.com/en/stable/ref/csrf/>

## The Tutorial (skim, then return when stuck)

- **Django tutorial Part 3 — views and templates**:
  <https://docs.djangoproject.com/en/stable/intro/tutorial03/>
- **Django tutorial Part 4 — forms and generic views**:
  <https://docs.djangoproject.com/en/stable/intro/tutorial04/>

## Books / free chapters

- **Classy Class-Based Views** — every CBV with its full MRO and attribute table; the single most useful third-party Django reference:
  <https://ccbv.co.uk/>
- **Classy Django Forms** — same idea for the forms hierarchy:
  <https://cdf.9vo.lt/>
- **Django Girls Tutorial** — chapters 12–15 cover forms and templates at a gentler pace:
  <https://tutorial.djangogirls.org/>

## On CSRF (worth a focused read)

- **OWASP — Cross-Site Request Forgery**:
  <https://owasp.org/www-community/attacks/csrf>
- **MDN — Same-origin policy** (helps understand why CSRF works):
  <https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy>

## Glossary

| Term | Definition |
|------|------------|
| **View** | A callable that takes an `HttpRequest` and returns an `HttpResponse` |
| **FBV** | Function-based view |
| **CBV** | Class-based view — `as_view()` returns the actual callable |
| **`ListView`** | Generic CBV that renders a queryset as a list |
| **`DetailView`** | Generic CBV that renders one object by lookup |
| **`CreateView`** / **`UpdateView`** | Generic CBVs that build a `ModelForm` and handle POST |
| **Template** | A text file (usually HTML) with Django Template Language interpolation |
| **`{% block %}`** | Named region in a template a child can override |
| **`{% extends %}`** | Declares a parent template; first non-comment line if used |
| **`{% url %}`** | Reverse a URL name to its path at render time |
| **`Form`** | A class describing a set of fields, their validation, and their rendering |
| **`ModelForm`** | A `Form` whose fields are inferred from a model |
| **`cleaned_data`** | The validated, type-coerced output of a successful `is_valid()` |
| **Session** | Per-user server-side data, keyed by a signed cookie |
| **CSRF token** | A per-request secret in a form that the server checks on POST |
| **`login_required`** | Decorator that redirects anonymous users to `LOGIN_URL` |
| **`LoginRequiredMixin`** | The CBV equivalent of `login_required` |
| **`reverse_lazy`** | `reverse()` deferred until first use — needed at class-body scope |

---

*Broken link? Open an issue.*
