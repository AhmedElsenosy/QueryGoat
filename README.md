# QueryGoat 🐐

**A daily SQL puzzle — like Wordle, but for SQL.**

Every day, one new SQL puzzle is published for everyone. You write a real SQL query in your browser, it runs against a real database on the server, and you win if your result set matches the expected answer. Streaks, points, badges, and a global leaderboard keep the daily habit alive — and a daily email nudges you back to play.

> 100% free forever: every service in the stack runs on a free tier.

---

## Table of contents

- [What it is](#what-it-is)
- [How it works](#how-it-works)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [API reference](#api-reference)
- [The daily agent (LangGraph)](#the-daily-agent-langgraph)
- [SQL sandbox & grading](#sql-sandbox--grading)
- [Game systems (points, streaks, badges, leaderboard)](#game-systems-points-streaks-badges-leaderboard)
- [Daily email](#daily-email)
- [Scheduled publishing (GitHub Actions)](#scheduled-publishing-github-actions)
- [Database schema](#database-schema)
- [Configuration](#configuration)
- [Testing](#testing)
- [Credits](#credits)

---

## What it is

- One puzzle per day, same for everyone (Wordle rule).
- Puzzles are presented **LeetCode-style**: problem statement, database schema with sample rows, FK relationships, and the exact output shape — never a raw research caption, never the answer.
- You submit SQL; the **server executes it** in a locked-down sandbox and compares your **result set** (values, not text) against the gold result.
- Solve it → earn points, grow your streak, climb the leaderboard. Miss a day → your streak dies.

## How it works

```
 Spider dataset (SQLite + gold SQL)
        │  ingest (one-time, difficulty-filtered)
        ▼
 PostgreSQL question bank ── 14 curated databases, ~272 medium/hard puzzles
        │
        │  daily agent (LangGraph, runs at UTC midnight)
        ▼
 Today's published puzzle ──> GET /puzzles/today ──> Frontend (Next.js)
        │                                   │
        │ emails all users                  ▼
        ▼                              POST /puzzles/today/submit
 Sweep of puzzle emails                  │  sandbox executes your SQL
                                         ▼
                              value fingerprint vs gold fingerprint
                                         │
                              pass → points + streak + badges + leaderboard
```

## Features

### Built and working

| Area | Details |
|------|---------|
| **Auth** | Gmail-only registration, Argon2 password hashing, JWT access (15 min) + refresh (14 d) with rotation & revocation, full Google OAuth2 flow |
| **Question bank** | 14 curated Spider databases, ~272 medium/hard questions ingested with executed-and-verified answers |
| **Daily agent** | LangGraph pipeline: pick → execute → validate → LLM-rewrite → LLM-verify → publish. Idempotent per day |
| **Prompt rewriting** | Gemini turns research captions like *"What is the Edispl of BMWs whose MPG is superier?"* into clean, self-contained LeetCode-style statements; a second LLM call writes SQL from the rewrite alone and must reproduce the gold result or the rewrite is retried/rejected |
| **Puzzle API** | `GET /puzzles/today` returns schema, FKs, and sample rows read live from the SQLite file (they can't drift) |
| **Submissions** | `POST /puzzles/today/submit` re-executes user SQL server-side, grades by result-set fingerprint, records attempts and first solves |
| **Anti-cheat** | sqlglot safety parsing, read-only in-memory exec, timeouts, row caps, and rejection of constant-only queries (`SELECT 0.99`) that never touch the data |
| **Points & badges** | easy = 1, medium = 2, hard = 3, extra = 4 points on first solve only; badges: Beginner 10 / Intermediate 25 / Advanced 50 / GOAT 100 |
| **Streaks** | UTC-day chained streak with longest-streak tracking; a missed day displays as broken without any cron |
| **Leaderboard** | `GET /leaderboard` — points first, longest streak as tie-break, optional personal `me` block with your rank |
| **Daily email** | Gmail SMTP announcements with the puzzle prompt and solve link, exactly-once per day via `daily_puzzles.notified_at` |
| **Rate limiting** | slowapi wired on auth (per IP) and submissions (per user) |
| **CORS** | middleware allowing localhost + `APP_FRONTEND_URL` |
| **Tests** | 45 pytest tests: auth, sandbox, agent idempotency, submissions, stats/points/streaks, leaderboard, rate limits, emailer (fake SMTP) |

### Not built yet (see [Roadmap](#roadmap))

Practice mode, frontend, deployment, Alembic has just been initialized.

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI (Python 3.12) |
| ORM / DB | SQLAlchemy 2.0, PostgreSQL (local today, Neon/Supabase planned) |
| Puzzle DBs | 14 SQLite files from the Spider dataset |
| Auth | JWT + Argon2 + Google OAuth2 |
| SQL evaluation | sqlglot (parse & safety) + in-memory SQLite |
| Agent | LangGraph StateGraph |
| LLM | Google Gemini via `google-genai`, behind a provider abstraction (swap to OpenAI/Anthropic by subclass) |
| Email | stdlib `smtplib` against Gmail SMTP |
| Jobs | GitHub Actions cron (file present, fires post-deployment) |
| Tests | pytest + FastAPI TestClient |
| Frontend (planned) | Next.js on Vercel |

## Project structure

```
backend/venv/src/                  ← backend root (this repo)
├── app/
│   ├── main.py                    FastAPI app, routers, CORS, rate limiting
│   ├── config.py                  Pydantic Settings (reads .env)
│   ├── db.py                      engine, SessionLocal, init_db bootstrap
│   ├── models.py                  users, refresh_tokens, databases,
│   │                              questions, agent_runs, daily_puzzles,
│   │                              submissions, user_stats
│   ├── schemas.py                 Pydantic request/response models
│   ├── security.py                Argon2 + JWT helpers
│   ├── deps.py                    get_current_user / get_optional_user
│   ├── gmail.py                   Gmail-only validation + canonicalization
│   ├── emailer.py                 SMTP puzzle announcements
│   ├── sandbox.py                 SQL safety parser + executor + fingerprints
│   ├── schema_inspector.py        schema/FK/sample extraction for puzzle cards
│   ├── rate_limit.py              slowapi Limiter + submit keyfunc
│   ├── routes/                    auth, puzzles, users, leaderboard, internal
│   ├── services/                  auth, google_oauth, grader (grading core),
│   │                              stats (points/streak/badges)
│   ├── agent/                     LangGraph daily agent (state, nodes, graph,
│   │                              prompts, run_daily, CLI)
│   ├── ingest/                    Spider ingestion (curated list, filters, CLI)
│   └── llm/                       provider abstraction + GeminiProvider
├── data/sqlite/                   the 14 puzzle SQLite databases
├── tests/                         45 tests across every service
├── migrations/                    Alembic (baseline = user_stats)
├── alembic.ini
└── .env                           secrets (never commit)

.github/workflows/daily-puzzle.yml  ← repo root: daily publish trigger

spider/                            ← upstream dataset (not committed)
```

## Getting started

```bash
# 1. Environment
python3.12 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/venv/src/requirements.txt

# 2. Postgres locally, then set DATABASE_URL in .env
#    A template for every variable lives in .env.example

# 3. Ingest Spider data (one-time; ~272 medium/hard questions)
cd backend/venv/src
python -m app.ingest

# 4. Publish today's puzzle (agent picks, validates, rewrites, emails users)
python -m app.agent

# 5. Run the API
uvicorn app.main:app --reload        # http://127.0.0.1:8000
# Swagger UI at http://127.0.0.1:8000/docs

# 6. Tests (45 passing)
pytest tests/ -v
```

CLI equivalents: `python -m app.ingest` (bank fill), `python -m app.agent` (daily publish), both idempotent.

## API reference

All responses JSON. Bearer tokens on protected routes.

### Auth — prefix `/auth`

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `POST /auth/register` | `{username, gmail, password}` | 201 `UserPublic` | Gmail-only; 409 if taken; canonicalized (`ahmed.elf@gmail.com` == `ahmedelf+nospam@gmail.com`) |
| `POST /auth/login` | `{username, password}` | `TokenResponse` | Rate limit 5/min/IP |
| `POST /auth/refresh` | `{refresh_token}` | `TokenResponse` | **Rotating**: old token revoked; 10/min/IP |
| `GET /auth/me` | — | `UserPublic` | Bearer required |
| `GET /auth/google/login` | — | redirect | Starts OAuth2 with signed state |
| `GET /auth/google/callback` | query `code`, `state` | `TokenResponse` | Auto-creates or links account |

`TokenResponse`: `{access_token, refresh_token, token_type:"bearer", expires_in}` — access lasts 15 min, refresh 14 days.

### Puzzles — prefix `/puzzles`

| Method & path | Body | Response | Notes |
|---|---|---|---|
| `GET /puzzles/today` | — | `DailyPuzzlePublic` | Public; 404 before publishing |
| `POST /puzzles/today/submit` | `{sql}` | `SubmitTodayResponse` | Bearer; 15/min **per user**; 404 pre-publish |

`DailyPuzzlePublic`:

```json
{
  "puzzle_date": "2026-10-20",
  "prompt": "What is the average unit price of tracks that belong to Jazz genre?",
  "difficulty": "medium",
  "database": "Chinook",
  "schema_info": [
    {
      "name": "Track",
      "columns": [{"name": "TrackId", "type": "INTEGER", "pk": true}],
      "foreign_keys": [{"from_column": "GenreId", "to_table": "Genre", "to_column": "GenreId"}],
      "sample_columns": ["TrackId", "Name", "UnitPrice"],
      "sample_rows": [[1, "For Those About To Rock", 0.99]]
    }
  ],
  "output_shape": {"columns": 1, "rows": 1}
}
```

`SubmitTodayResponse`:

```json
{
  "is_correct": true,
  "status": "correct",            // correct | wrong | sql_error | timeout | too_many_rows | cheat
  "message": "Correct! You solved today's puzzle. +2 points — 1 day streak!",
  "attempts": 3,
  "solved": true,
  "puzzle_date": "2026-10-20",
  "points": 2,
  "total_points": 132,
  "current_streak": 1,
  "badge": "GOAT"
}
```

User mistakes (bad SQL, timeouts, "cheats") come back as **200** with a status, so they still count as attempts; only infrastructure failures are HTTP errors.

### Users — prefix `/users`

| Method & path | Response | Notes |
|---|---|---|
| `GET /users/me/stats` | `UserStatsResponse` | Bearer; points, badge, streaks, per-difficulty counters, last solve date |

### Leaderboard

| Method & path | Response | Notes |
|---|---|---|
| `GET /leaderboard?limit=50` | `{entries: [...], me: ... \| null}` | Public; with a valid Bearer the caller's rank row appears in `me` even outside the top N |

Entry: `{rank, user_id, username, points, current_streak, total_solved, badge}` — ordered by points desc, longest streak desc, earliest join asc.

### Internal

| Method & path | Headers | Response | Notes |
|---|---|---|---|
| `POST /internal/daily/run` | `X-Daily-Job-Secret` | `DailyRunResponse` | Triggers the agent pipeline; 503 without configured secret, 401 on wrong secret |

### Health

`GET /health` → `{ok, user, database}`.

## The daily agent (LangGraph)

```
START
  → already_published            (idempotency guard; also retries a missed email send)
      └─ publish exists? → notify_users → END
  → select_candidate             (random eligible unused question; avoids last 5 DBs)
  → execute_gold                 (sandbox run of the gold SQL)
  → validate_result              (hash match vs ingest, size caps)
      └─ rejected → retry → select_candidate (max 5 candidates)
  → rewrite_prompt               (Gemini: caption → LeetCode statement)
  → verify_rewrite               (second LLM sees ONLY sentence+schema, writes SQL)
      └─ fingerprints match  → publish → notify_users → END
      └─ mismatch after 3     → reject → retry
  → notify_users                 (email all active users; exactly-once stamp)
```

Key design decisions:

1. **Real data only** — every question comes from human-annotated Spider data; answers are verified by executing SQL, never by trusting an LLM.
2. **Result-set comparison** — grading compares fingerprints of result *values*, not SQL text, because many valid queries produce the same answer.
3. **LLM improves UX, never decides correctness** — the rewrite is graded by whether an independent LLM call, seeing only the rewrite, can reproduce the gold result.
4. **Graceful degradation** — no `GEMINI_API_KEY`? Original captions ship. No Gmail creds? Emails skip. The daily puzzle never fails because of extras.
5. **Idempotent everywhere** — reruns return `already_published` and never duplicate puzzles or emails.

## SQL sandbox & grading

Every user-submitted query is re-executed server-side (`app/sandbox.py`):

- **sqlglot allow-list:** single read-only statement rooted in `SELECT`/`UNION`/`EXCEPT`/`INTERSECT`; `INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/ATTACH/DETACH/PRAGMA`, multi-statement input, `RAND()` and `load_extension` are all rejected.
- **Isolation:** the puzzle SQLite file is copied into `:memory:` with `PRAGMA query_only=ON`; the original file is never touched.
- **Timeout:** progress handler aborts at 2 s (infinite-recursive-CTE attacks die here).
- **Row cap:** 50 rows for puzzles / 200 for sandbox runs.
- **Anti-cheat (`assert_uses_data`):** the query must reference at least one base table and project at least one data-derived expression (column, `*`, or aggregate). Constant-only answers (`SELECT 0.99`, `SELECT 0.99 AS x FROM Genre LIMIT 1`) are rejected as `cheat` and recorded as attempts.

**Grading** (`app/services/grader.py`): user result vs gold result compared by **value fingerprint** — SHA-256 over normalized cells, rows sorted unless the gold SQL had `ORDER BY`. Column labels are deliberately ignored so `AVG(T2.UnitPrice)` and `AS avg_price` grade the same.

## Game systems (points, streaks, badges, leaderboard)

State lives in one `user_stats` row per user, updated in the same transaction as the first-solve `Submission` insert — the DB's partial unique index `(user_id, question_id) WHERE is_correct` makes double-awarding impossible even on concurrent submits.

| Difficulty | Points |
|---|---|
| easy | 1 |
| medium | 2 |
| hard | 3 |
| extra | 4 |

| Badge | Total points |
|---|---|
| Beginner | 10+ |
| Intermediate | 25+ |
| Advanced | 50+ |
| **GOAT** | 100+ |

**Streak rules:** UTC days (matching when puzzles publish). Solving yesterday's chain → +1; a gap → restart at 1; `longest_streak` is permanent bragging rights. Display rule: alive only if the last solve was today or yesterday — so a missed day *looks* broken with zero cron jobs.

## Daily email

`notify_users` (LangGraph node) sends one plain-text email per active user from a single SMTP session (Gmail, STARTTLS, 0.1 s pacing, 450/day cap, bad credentials or refused recipients are logged not fatal). Content: puzzle prompt, database + difficulty, output shape, and the **solve link pointing at `APP_FRONTEND_URL`**.

Emails are exactly-once per puzzle day via `daily_puzzles.notified_at`; the flag is stamped only on success so a dead send retries on the next run.

## Scheduled publishing (GitHub Actions)

`.github/workflows/daily-puzzle.yml` (repo root):

- `cron: 5 0 * * *` (00:05 UTC, just after the puzzle-date rollover) + `35 0` safety retry + manual `workflow_dispatch`.
- POSTs `{BACKEND_URL}/internal/daily/run` with the `DAILY_JOB_SECRET` header, 3 attempts, fail-loudly (GitHub emails you on failure).
- Repo secrets to configure: `BACKEND_URL`, `DAILY_JOB_SECRET`.

## Database schema

| Table | Purpose | Highlights |
|---|---|---|
| `users` | accounts | unique lowercase username, unique email, `email_canonical` (Gmail anti-alias), nullable `password_hash` for Google-only accounts, unique `google_sub` |
| `refresh_tokens` | sessions | unique `jti`, `revoked_at` for rotation |
| `databases` | 14 puzzle DBs | `spider_db_id`, `sqlite_path` relative to src |
| `questions` | the bank | `gold_sql` + normalized, difficulty CHECK, executed `result_hash`, unique per (db, gold), partial-unique `used_as_daily_on`, `rewritten_prompt` |
| `agent_runs` | pipeline telemetry | status CHECK (running/published/already_published/failed), attempts, reject reasons JSONB |
| `daily_puzzles` | one per date | unique date, FK question + agent run, `notified_at` stamp |
| `submissions` | every attempt | first-solve partial unique index, attempts for grading telemetry |
| `user_stats` | game state | points, per-difficulty counters, streaks, last solve date |

Migrations: Alembic (`migrations/`), URL sourced from `.env`; the historical schema was bootstrap-created by `init_db()` (dev convenience — production should run `alembic upgrade head`).

## Configuration

All in `.env` (template in `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | signing secret for access/refresh/OAuth-state JWTs |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | token lifetimes (15 / 14) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | OAuth2 login |
| `EMAIL_ADDRESS` / `EMAIL_PASSWORD` | Gmail app-password SMTP sender |
| `APP_FRONTEND_URL` | browser origin + the "solve it now" link in emails |
| `DAILY_JOB_SECRET` | shared secret for the internal trigger/workflow |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | LLM prompt rewriting (default `gemini-2.0-flash`) |
| `RATE_LIMIT_LOGIN/_REGISTER/_REFRESH/_SUBMIT` | slowapi budgets |

## Testing

```bash
pytest tests/ -v          # 45 tests
```

Coverage highlights: Gmail canonicalization, register/login/refresh rotation, Google OAuth (mocked), sandbox safety & execution caps, fingerprint semantics, agent idempotency, gold-SQL secrecy in responses, submission grading incl. anti-cheat variants, points/streak chaining + gap resets, badge thresholds, leaderboard ordering + `me` block, rate-limit 429s (register/login by IP; submit per-user), emailer with a fake SMTP layer (real SMTP is unreachable from tests by conftest design).

## Credits

- Question texts, gold SQL, and databases come from the [Spider dataset](https://yale-lily.github.io/spider) (CC BY-SA 4.0) — human-annotated, 14 databases curated for solvable, confident puzzles.
- Built with FastAPI, LangGraph, sqlglot, and Google Gemini.

## Frontend

- Frontend link : [QueryGoat Frontend](https://github.com/AhmedElsenosy/QueryGoat-Frontend)
