# C16 · Crunch Pro Web Backend — Curriculum

This folder contains every weekly module of the 12-week curriculum. Start with [`SYLLABUS.md`](SYLLABUS.md), then open Week 1.

## Weeks

1. [Week 1 — HTTP and the Modern Python Web](week-01-http-and-the-modern-python-web/)
2. [Week 2 — Django Models, the ORM, and the Admin](week-02-django-models-orm-admin/)
3. [Week 3 — Views, Templates, Forms, and Auth](week-03-views-templates-forms-auth/)
4. [Week 4 — PostgreSQL for Application Developers](week-04-postgresql-for-app-developers/)
5. [Week 5 — Django ORM Deep Dive](week-05-django-orm-deep-dive/)
6. [Week 6 — Migrations, Background Jobs, and Caching](week-06-migrations-jobs-caching/)
7. [Week 7 — FastAPI Fundamentals](week-07-fastapi-fundamentals/)
8. [Week 8 — Async, Sync, and the GIL](week-08-async-sync-and-the-gil/)
9. [Week 9 — Auth, OAuth, and JWT](week-09-auth-oauth-jwt/)
10. [Week 10 — Docker, Compose, and the 12-Factor App](week-10-docker-compose-12-factor/)
11. [Week 11 — Testing, CI, and Observability](week-11-testing-ci-observability/)
12. [Week 12 — Security, Deployment, and Capstone](week-12-security-deployment-capstone/)

## Standard week layout

Every week has the same shape so you always know where to look:

```
week-NN-topic/
├── README.md                      ← start here every week
├── resources.md                   ← curated free readings + official docs
├── lecture-notes/
│   ├── 01-...md
│   ├── 02-...md
│   └── 03-...md
├── exercises/
│   ├── README.md
│   ├── exercise-01-*.py
│   ├── exercise-02-*.py
│   └── exercise-03-*.py
├── challenges/
│   ├── README.md
│   ├── challenge-01-*.md
│   └── challenge-02-*.md
├── quiz.md                        ← 10 multiple-choice, answers at bottom
├── homework.md                    ← 5–6 problems, ~6 hours total
└── mini-project/
    ├── README.md                  ← spec + rubric
    └── starter.py / starter/...   ← starter code
```

## Order of operations within a week

The order is designed deliberately — do not skip ahead.

1. Read `README.md`. Get oriented and plan your week.
2. Skim `resources.md` to know what's available when you get stuck.
3. Read each lecture in order. Take notes by hand.
4. Do the exercises. Don't read the next one until the previous runs.
5. Attempt the challenges. They're optional but the gap between "comfortable" and "expert" lives here.
6. Take the quiz with the lectures closed. Grade yourself.
7. Do the homework. This is the primary learning lever.
8. Ship the mini-project. Commit, push, link from your portfolio.

## Tracking your progress

We recommend one GitHub repository per week, named `c16-week-NN-yourhandle`. By Week 12 you'll have 12 public repos showing your progression — that's a stronger portfolio than any single capstone.
