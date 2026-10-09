# Perception frontend

Next.js app for Perception. It talks to the FastAPI backend in `../backend`.

## Run it

You need Node.js 18.18 or newer. Start the backend first.

```bash
cd peak-app
npm install
npm run dev
```

Open http://localhost:3000.

The app calls the backend at `http://127.0.0.1:8000/api`. To use another
address, copy `.env.example` to `.env.local` and change `NEXT_PUBLIC_API_URL`.
The backend must also list this app's address in `CORS_ORIGINS`.

## Pages

| Path | Who | What |
| --- | --- | --- |
| `/login`, `/signup` | anyone | Email and password. No Firebase |
| `/dashboard` | both | Teacher: papers and class. Student: assigned papers |
| `/create-paper` | teacher | New paper with marks, model answers and rubrics |
| `/edit-paper/[id]` | teacher | Edit a paper |
| `/view-paper/[id]` | both | Teacher: submissions, AI grading, manual marks. Student: results |
| `/attempt-paper/[id]` | student | Write and submit answers |

## Notes

- The login token is kept in the browser's local storage. `src/lib/api.ts`
  adds it to every request and logs out on a 401.
- While a student writes, answers are saved in the browser only. They reach
  the server when the student submits.
- Shared helpers are in `src/lib` (`api.ts`, `auth.ts`, `types.ts`,
  `format.ts`, `utils.ts`).
