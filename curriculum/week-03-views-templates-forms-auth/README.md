# Week 3 — Views, Templates, Forms, and Auth

> *Models describe your data; views, templates, and forms describe your application. Auth decides who is allowed to do what. By the end of this week you have an application a real human can use without an admin account.*

Welcome to Week 3 of **C16 · Crunch Pro Web Backend**. Week 2 stood up the data model and the admin. The admin is for editors; this week we build the front door that everyone else uses — a public reader, a login page, an author dashboard, and the form that lets an author write an article without touching the admin.

By Sunday you will have shipped **`crunchwriter` v1**: a public article reader at `/`, a login page at `/accounts/login/`, and an author dashboard at `/dashboard/` that is only reachable when authenticated. Three real URLs, three rendered HTML pages, one functioning form.

This is the week Django stops feeling like a database wrapper and starts feeling like a web framework.

## Learning objectives

By the end of this week, you will be able to:

- **Write** function-based views (FBVs) and class-based views (CBVs), and explain when each is the right tool.
- **Use** the four CBV generics you actually need day-to-day: `ListView`, `DetailView`, `CreateView`, `UpdateView`.
- **Render** templates with the Django Template Language (DTL): `{% extends %}`, `{% block %}`, `{% include %}`, `{% url %}`, `{% csrf_token %}`, `{% for %}`, `{% if %}`, filters.
- **Build** a regular `Form` and a `ModelForm`, including custom `clean_<field>` validators and a non-trivial `clean()` cross-field check.
- **Configure** Django's session and authentication system: `LoginView`, `LogoutView`, `PasswordChangeView`, the `login_required` decorator, and `LoginRequiredMixin`.
- **Defend** the application against CSRF using `{% csrf_token %}` and explain what the middleware is actually checking.
- **Route** URLs cleanly with `path()`, `include()`, named URLs, and reverse with `{% url %}` / `reverse()` / `reverse_lazy()`.
- **Read** the request/response cycle for an authenticated form POST end-to-end and identify each middleware that touched it.

## Prerequisites

- **C16 Week 2 mini-project completed** — `crunchwriter` v0 running with `Author`, `Article`, `Category` models and a working admin.
- **Comfortable Python OOP** (C1 Week 7) — CBVs lean on mixins; if MRO is fuzzy, refresh it.
- **HTML 101** — you can read a `<form action method>` tag.

## Topics covered

- The view contract: a callable that takes `HttpRequest` and returns `HttpResponse`
- Function-based views: when to reach for them
- Class-based views: the generic hierarchy and what each generic gives you
- `View` → `TemplateView` → `ListView` / `DetailView` / `CreateView` / `UpdateView` / `DeleteView`
- `as_view()` and what the URL conf actually receives
- `get_queryset`, `get_context_data`, `get_object` — the three CBV hooks you customize most
- The Django Template Language: tags, filters, variables, comments
- Template inheritance: a `base.html`, `{% block %}` overrides, and partials via `{% include %}`
- The `{% url %}` tag and named URLs — never hardcode a path again
- `static` and `STATICFILES_DIRS` — enough to load a stylesheet
- `Form` vs `ModelForm`, and why `ModelForm` exists
- Validation lifecycle: `is_valid()` → `clean_<field>()` → `clean()` → `cleaned_data`
- Cross-field validation and the right place for it
- The session framework: how Django identifies a user across requests
- Authentication backends and `authenticate()` / `login()` / `logout()`
- `login_required`, `LoginRequiredMixin`, `permission_required`, `user_passes_test`
- `LoginView`, `LogoutView`, `PasswordChangeView`, `PasswordResetView` — what ships
- CSRF: what the attack is, what the cookie + token do, when to exempt (almost never)
- `next` parameter on `LoginView` and how to redirect after login
- Messages framework for one-shot user feedback after a POST/redirect

## Weekly schedule

| Day       | Focus                                  | Lectures | Exercises | Challenges | Quiz/Read | Homework | Mini-Project | Self-Study | Daily Total |
|-----------|----------------------------------------|---------:|----------:|-----------:|----------:|---------:|-------------:|-----------:|------------:|
| Monday    | FBV vs CBV; URL routing                | 2h       | 1.5h      | 0h         | 0.5h      | 1h       | 0h           | 0.5h       | 5.5h        |
| Tuesday   | Templates: DTL, inheritance, `{% url %}` | 2h     | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0h         | 6.5h        |
| Wednesday | Forms + ModelForms + validation        | 2h       | 2h        | 1h         | 0.5h      | 1h       | 0h           | 0.5h       | 7h          |
| Thursday  | Auth, sessions, CSRF, `LoginRequiredMixin` | 0h   | 1.5h      | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 6.5h        |
| Friday    | Mini-project deep work                 | 0h       | 0h        | 1h         | 0.5h      | 1h       | 2h           | 0.5h       | 5h          |
| Saturday  | Mini-project deep work + polish        | 0h       | 0h        | 0h         | 0h        | 1h       | 3h           | 0h         | 4h          |
| Sunday    | Quiz + reflection                      | 0h       | 0h        | 0h         | 0.5h      | 0h       | 0h           | 0h         | 0.5h        |
| **Total** |                                        | **6h**   | **7h**    | **4h**     | **3h**    | **6h**   | **7h**       | **2h**     | **35h**     |

## How to navigate this week

| File | What's inside |
|------|---------------|
| [README.md](./README.md) | This overview |
| [resources.md](./resources.md) | Django views/templates/forms/auth docs + extras |
| [lecture-notes/01-function-vs-class-based-views.md](./lecture-notes/01-function-vs-class-based-views.md) | The view contract and the CBV ladder |
| [lecture-notes/02-templates-and-the-form-system.md](./lecture-notes/02-templates-and-the-form-system.md) | DTL, inheritance, `Form` vs `ModelForm`, validation |
| [lecture-notes/03-auth-sessions-csrf-loginrequired.md](./lecture-notes/03-auth-sessions-csrf-loginrequired.md) | Auth, sessions, CSRF, `LoginRequiredMixin` |
| [exercises/README.md](./exercises/README.md) | Index of exercises |
| [exercises/exercise-01-three-views-three-ways.md](./exercises/exercise-01-three-views-three-ways.md) | The same screen as FBV, CBV, and `ListView` |
| [exercises/exercise-02-modelform-with-validation.md](./exercises/exercise-02-modelform-with-validation.md) | A `ModelForm` with two layers of validation |
| [exercises/exercise-03-login-and-protected-views.md](./exercises/exercise-03-login-and-protected-views.md) | Real login + a view nobody else can see |
| [challenges/README.md](./challenges/README.md) | Stretch challenges |
| [challenges/challenge-01-custom-permission-decorator.md](./challenges/challenge-01-custom-permission-decorator.md) | Roll your own decorator that's safer than `user_passes_test` |
| [quiz.md](./quiz.md) | 10 MCQ |
| [homework.md](./homework.md) | Six problems (~6h) |
| [mini-project/README.md](./mini-project/README.md) | `crunchwriter` v1 — the public reader + author dashboard |

## Stretch goals

- Read the **Class-based views topic guide** end-to-end:
  <https://docs.djangoproject.com/en/stable/topics/class-based-views/>
- Read the source of `django.views.generic.edit.FormMixin` once. It is shorter than you expect and explains why CBV form-handling is the way it is.
- Add `django-debug-toolbar` and confirm the **History** panel shows the session cookie + CSRF token cycle on a login POST.
- Skim the **Auth views source** in `django/contrib/auth/views.py`. It's a reference implementation of every pattern you'll write yourself.

## Up next

[Week 4 — PostgreSQL for Application Developers](../week-04-postgresql-for-app-developers/) — once `crunchwriter v1` is up, authors can log in, write articles in a form, and readers can read them at a clean URL.
