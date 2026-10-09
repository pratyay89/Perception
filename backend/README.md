# Perception backend

FastAPI service for Perception. Teachers create question papers with model
answers and rubrics. Students in the teacher's class submit answers. An LLM
(Groq) gives each answer a mark and feedback. The teacher can review and
change any mark.

## Quick start

You need Python 3.11 or newer.

### With uv (recommended)

```bash
cd backend
cp .env.example .env        # Windows PowerShell: copy .env.example .env
uv sync
uv run uvicorn main:app --reload
```

### With pip

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env        # Windows PowerShell: copy .env.example .env
uvicorn main:app --reload
```

The server runs at http://127.0.0.1:8000. Open http://127.0.0.1:8000/docs for
the interactive API docs. Tables are created on first start.

With the default settings the data goes into a local SQLite file
(`perception.db`), so there is nothing else to install.

### Turn on AI grading

1. Create a free API key at https://console.groq.com/keys
2. Put it in `backend/.env` as `GROQ_API_KEY=...`
3. Restart the server.

`GET /health` shows `"llm_configured": true` when the key is loaded. Without a
key everything works except the evaluate endpoints, which answer with 503.

## Configuration

All settings live in `.env`. See `.env.example` for the full list.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` hides `/docs` and requires `SECRET_KEY` |
| `SECRET_KEY` | empty | Signs login tokens. In development a random key is created in `.dev_secret_key` |
| `DATABASE_URL` | SQLite file | Use `postgresql+asyncpg://user:pass@host:5432/db` for PostgreSQL |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Addresses of the frontend |
| `GROQ_API_KEY` | empty | Needed for AI grading |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Any Groq chat model |
| `GROQ_REASONING_EFFORT` | `low` | `low`, `medium`, `high`, or `none` for models without reasoning |
| `LLM_MAX_CONCURRENCY` | `2` | Answers sent to the model at the same time |
| `*_MONTHLY_LIMIT` | 20 / 100 / 200000 | Papers, submissions and LLM tokens per user per month |

### PostgreSQL

From the project root:

```bash
docker compose up -d db
```

Then set in `backend/.env`:

```
DATABASE_URL=postgresql+asyncpg://perception:perception@localhost:5432/perception
```

There are no migrations yet. If you change a model, drop the tables (or delete
`perception.db`) and start the server again.

## API

Every route except signup, login and `/health` needs the header
`Authorization: Bearer <access_token>`.

| Method and path | Who | What it does |
| --- | --- | --- |
| `POST /api/auth/signup` | anyone | Create a student or teacher account |
| `POST /api/auth/login` | anyone | Form fields `username` (the email) and `password`. Returns the token |
| `GET /api/auth/me` | user | The current account |
| `DELETE /api/auth` | user | Delete the current account and its data |
| `GET /api/auth/associations` | user | Teacher: their students. Student: their teachers |
| `POST /api/auth/associations?s_email=` | teacher | Add a registered student to the class |
| `DELETE /api/auth/associations?s_email=` | teacher | Remove a student from the class |
| `GET /api/auth/usage` | user | Remaining monthly allowance |
| `POST /api/papers` | teacher | Create a paper with its questions |
| `GET /api/papers` | user | Teacher: own papers. Student: papers of their teachers |
| `GET /api/papers/{qpid}` | user | One paper with questions. Students never get model answers or rubrics |
| `PATCH /api/papers/{qpid}` | teacher | Edit, publish (`is_published`), close or reopen (`is_closed`) |
| `DELETE /api/papers/{qpid}` | teacher | Delete a paper and its submissions |
| `POST /api/submissions/{qpid}` | student | Submit answers. One submission per paper |
| `GET /api/submissions/{qpid}` | user | Teacher: all submissions. Student: their own |
| `GET /api/submissions/{qpid}/{s_email}` | user | One submission with answers, marks and feedback |
| `DELETE /api/submissions/{qpid}/{s_email}` | user | Student: withdraw before results. Teacher: delete |
| `POST /api/evaluations/{qpid}` | teacher | Grade every submission of a paper with the LLM |
| `POST /api/evaluations/{qpid}/{s_email}` | teacher | Grade one submission. `?force=true` grades again |
| `PATCH /api/evaluations/{qpid}/{s_email}/{qid}` | teacher | Set the mark and feedback of one answer by hand |
| `DELETE /api/evaluations/{qpid}` | teacher | Remove all marks of a paper. Answers are kept |
| `DELETE /api/evaluations/{qpid}/{s_email}` | teacher | Remove the marks of one submission |

### Paper status

| Status | Meaning |
| --- | --- |
| `draft` | Not published. Only the teacher sees it |
| `scheduled` | Published, but `start_date` is in the future |
| `open` | Students can read it and submit |
| `closed` | The teacher set `is_closed`. No new submissions |

`duration_minutes` is a time limit shown to the student as a countdown. The
server does not enforce it.

## How grading works

The code is in `app/utils/evaluator.py` and `app/evaluations/service.py`.

- Each answer is sent to the model on its own, with the question, the maximum
  marks, the model answer and the rubric. With no rubric, the model rates
  accuracy, completeness, relevance and clarity and scales the result.
- The model must return JSON with `score` and `feedback`. The request uses
  Groq structured outputs. If the model does not support them, the code falls
  back to plain JSON mode.
- A score outside 0 to the maximum marks is rejected, not cut down. It usually
  means the model used another scale, and cutting it down would give full
  marks. The call is retried. If it still fails, the answer is marked `failed`.
- A blank answer gets 0 without calling the model.
- The student's answer is wrapped in tags and treated as untrusted text. Tag
  look-alikes inside the answer are neutralised before the prompt is built.
- A `failed` answer never blocks the others. Run the evaluation again and only
  the answers without a mark are sent. The teacher can also grade by hand.
- When the provider keeps answering "rate limit", the run stops early. Answers
  already graded are kept and the rest stay `pending`.
- A submission counts as evaluated only when every answer has a mark. Students
  see marks and feedback only then.
- Results are written against the rows as they are after the model has
  answered. If the student withdrew, or the teacher reset or changed a mark in
  the meantime, the stale result is dropped.
- Tokens used are charged to the teacher's monthly balance.

## Tests

```bash
uv run pytest                 # or: pip install -r requirements-dev.txt && pytest
```

The tests use a throwaway SQLite file and a fake LLM. They need no API key and
do not touch your development database.

Run them against PostgreSQL:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/perception_test uv run pytest
```

Five extra tests call the real Groq API. They are skipped unless you ask:

```bash
RUN_LIVE_LLM_TESTS=1 uv run pytest -m live
```

They need `GROQ_API_KEY` in `.env` and use a small amount of your quota.

## Layout

```
backend/
  main.py                  app, CORS, error handlers
  app/config.py            settings from .env
  app/database.py          engine, session, UTC datetime type
  app/core/                enums and shared input checks
  app/auth/                accounts, login, classes, monthly usage
  app/papers/              question papers and questions
  app/submissions/         student answers
  app/evaluations/         LLM grading runs and teacher review
  app/utils/evaluator.py   prompt, Groq request, response parsing
  tests/                   pytest suite
```
