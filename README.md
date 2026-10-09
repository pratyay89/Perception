# Perception - AI-Powered Online Evaluation Portal

In today’s education landscape, **automated assessments** often fail to provide meaningful feedback for descriptive answers.
Even with the presence of AES (Automated Essay Grading), it works in open-world and hence, not Context specific, and does not provide any feedback.

**Perception** bridges this gap by leveraging **Contextual AI-powered evaluation**, ensuring that students receive **accurate, personalized, and constructive feedback**, just like a human evaluator.

## Features

### **For Students**

- View **pending** and **submitted** question sets of assigned teachers.
- Answer **descriptive** questions within the portal.
- Receive **AI-generated feedback and scores** after evaluation by teachers.

### **For Teachers**

- **Create** and **manage** question sets.
- Provide **model answers** and **rubric** to guide AI-based evaluation and obtain custom scores of students as evaluated by the LLM.
- **Review & finalize** AI-generated scores before submission.

### **AI-Based Evaluation**

- Uses **LLM** to **compare** student responses with teacher-provided answers.
- Provides **personalized feedback** and **suggestions** for improvement.
- Ensures **fair and unbiased** evaluation across all students by using pre-defined rules and rubric.

### Application Screenshots

<div align="center">

|       Authentication       |           Teacher Dashboard            |
| :------------------------: | :------------------------------------: |
| ![Login](Images/Pimg1.png) | ![Teacher Dashboard](Images/Pimg2.png) |

|        Question Management        |            Question Creation            |
| :-------------------------------: | :-------------------------------------: |
| ![Teacher View](Images/Pimg3.png) | ![Creating Questions](Images/Pimg4.png) |

|           Student Dashboard            |              AI Evaluation              |
| :------------------------------------: | :-------------------------------------: |
| ![Student Dashboard](Images/Pimg5.png) | ![Student Evaluation](Images/Pimg6.png) |

</div>

## Tech Stack

- **Frontend:** [Next.js](https://nextjs.org/), [Tailwind CSS](https://tailwindcss.com/), [Shadcn UI](https://ui.shadcn.com/)
- **Database:** [PostgreSQL](https://www.postgresql.org/), or SQLite for local development
- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) with JWT login
- **AI Integration:** LLM-based text evaluation with the [Groq](https://groq.com/) inference API (default model `openai/gpt-oss-120b`, set with `GROQ_MODEL`)

The screenshots above are from an earlier version. The result pages now show
one mark and one feedback text per question, graded against the teacher's
rubric.

## Run it locally

You need Python 3.11+ and Node.js 18.18+. Use two terminals.

**1. Backend** (http://127.0.0.1:8000, API docs at `/docs`)

```bash
cd backend
cp .env.example .env        # Windows PowerShell: copy .env.example .env
uv sync
uv run uvicorn main:app --reload
```

No [uv](https://docs.astral.sh/uv/)? Use pip instead:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env        # Windows PowerShell: copy .env.example .env
uvicorn main:app --reload
```

By default the data is stored in a local SQLite file, so no database setup is
needed. For AI grading, create a free key at https://console.groq.com/keys and
put it in `backend/.env` as `GROQ_API_KEY=...`, then restart the backend.

**2. Frontend** (http://localhost:3000)

```bash
cd peak-app
npm install
npm run dev
```

**3. Try it**

1. Sign up as a teacher. In a private window, sign up as a student.
2. As the teacher: open the account menu, choose **Manage Students**, and add
   the student's email.
3. Create a paper with questions, marks and model answers. Leave **Publish**
   ticked.
4. As the student: attempt the paper and submit.
5. As the teacher: on the paper card choose **Evaluate Papers**. Open
   **View & Manage** to read the result and change any mark.
6. As the student: open **View Attempt** to see marks and feedback.

More detail: [backend/README.md](backend/README.md) and
[peak-app/README.md](peak-app/README.md).

## Tests

```bash
cd backend
uv run pytest
```

The tests use a temporary database and a fake LLM. They need no API key.

## Project layout

```
backend/     FastAPI service, LLM grading, tests
peak-app/    Next.js frontend
Images/      screenshots
docker-compose.yml   optional local PostgreSQL
```
