# What changed in this version

This version makes the project run end to end again. The backend and the
frontend had drifted apart, and the LLM model in the code no longer exists on
Groq.

## State of the code before

- The frontend still used Firebase login and the old API (`/paper/list`,
  `/type`, `/tsa`, `/evaluate/...`). None of its 14 API calls existed on the
  backend. It also did not compile, because `src/lib/utils.ts` was never
  committed (the root `.gitignore` ignores every `lib/` folder).
- The grader used `llama-3.3-70b-versatile`. Groq shut that model down on
  16 August 2026.
- The existing tests passed only against a database that already had tables.

## Backend fixes

Each of these was reproduced first, then fixed, and now has a test.

| Problem | Now |
| --- | --- |
| The LLM could give more marks than a question is worth (50 on a 10-mark paper) | A score outside 0 to the maximum is rejected and retried, then marked `failed` for the teacher |
| A cut-off LLM reply left old marks in place and still set `evaluated` | Failed answers get 0, and a submission is evaluated only when every answer has a mark |
| Any teacher could read any other teacher's submissions | Only the owner of a paper can read, evaluate, reset or change marks |
| Students always got an empty paper list | Students get the published papers of their teachers, with attempt status and marks |
| A student outside the class could submit | Submitting needs class membership and an open paper |
| Unknown or repeated question ids, a repeated class member, or a new question without marks crashed with 500 | Clear 400, 409 or 422 answers |
| Monthly limits never reset | Balances refill when the month changes |
| Limits and token charges could be bypassed by sending requests at the same time | Counters are changed with single atomic SQL updates |
| Marks could be written over data that changed during grading | Results are stored only if the answer is still the one the LLM read |
| A token kept working after its account was deleted and the email reused | Tokens carry a per-account id that is checked on every request |
| Very large ids, NUL bytes or absurd dates crashed with 500 | Input is bounded and checked. Validation errors no longer echo the input back |
| The student's answer went into the prompt unprotected | The answer is treated as untrusted text and cannot close its own tag |
| No way to finish the teacher's work | New routes: evaluate a whole paper, reset marks, set a mark by hand, remove a student, `/me` |

Also new: SQLite works out of the box for local runs, `.env.example`,
`requirements.txt` for pip, a random development secret instead of a required
one, timestamps always in UTC, and Python 3.11+ instead of 3.13 only.

## Frontend

- Firebase is removed. Login and signup use the backend.
- Every page uses the current API.
- Papers have marks per question, an optional rubric, a start time, an
  optional time limit, and a draft state. Papers can be edited.
- The teacher's paper page can grade one student, grade again, reset, and
  change a mark and its feedback.
- While a student writes, answers are saved in the browser and survive a
  reload.

## Behaviour to know about

- `duration_minutes` is shown as a countdown. The server does not enforce it.
- Evaluating a paper is one long request. On the Groq free tier a large class
  can hit the rate limit. The run then stops, keeps what it graded, and you
  run it again later.
- There are no database migrations. This version adds columns, so start with a
  fresh database.
- Students can no longer read a closed paper they did not answer.
- Once a paper has submissions, its question text and marks cannot change.

## Not verified

The grading code was tested with a fake LLM and with a local stand-in for the
Groq API, through the real Groq SDK. It has not been run against the real Groq
service, because no API key was available. After you add your key, run:

```bash
cd backend
RUN_LIVE_LLM_TESTS=1 uv run pytest -m live
```

The Docker files were not built or run.
