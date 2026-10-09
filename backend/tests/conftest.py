"""Shared test setup.

The tests never touch the development database: unless TEST_DATABASE_URL is
set, they run against a throwaway SQLite file that is deleted afterwards.
To run them against PostgreSQL instead:

    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/perception_test pytest
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

# These must be set before anything from `app` is imported, because the
# settings and the database engine are created at import time.
_TMP_DIR = None
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    _TMP_DIR = tempfile.TemporaryDirectory(prefix="perception-tests-")
    _db_file = Path(_TMP_DIR.name) / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_file.as_posix()}"
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-used-only-by-the-test-suite-0123456789"
)
os.environ["DATABASE_ECHO"] = "false"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import Base, engine, init_models  # noqa: E402
from app.utils.evaluator import EvaluationService  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database():
    """Create the tables once for the whole test session."""
    await init_models()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Dispose of the connection pool to avoid "Event loop is closed" errors.
    await engine.dispose()
    if _TMP_DIR is not None:
        _TMP_DIR.cleanup()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class FakeLLM:
    """Stands in for the Groq client, so tests need no API key or network.

    `reply` is either the text the model "returns", an Exception to raise, or
    a function (kwargs -> text or Exception). `calls` records every request.
    `during_call`, if set, is an async function awaited while the "model" is
    busy; tests use it to change things in the middle of an evaluation.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self.reply = json.dumps({"score": 1, "feedback": "Good attempt."})
        self.total_tokens = 100
        self.finish_reason = "stop"
        self.during_call = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.during_call is not None:
            await self.during_call(kwargs)
        reply = self.reply(kwargs) if callable(self.reply) else self.reply
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=reply),
                    finish_reason=self.finish_reason,
                )
            ],
            usage=SimpleNamespace(total_tokens=self.total_tokens),
        )


@pytest.fixture
def fake_llm():
    previous_client = EvaluationService.client
    previous_compat = EvaluationService._compat_mode
    fake = FakeLLM()
    EvaluationService.client = fake
    EvaluationService._compat_mode = False
    yield fake
    EvaluationService.client = previous_client
    EvaluationService._compat_mode = previous_compat


async def register(client: AsyncClient, role: str, name: str | None = None) -> dict:
    """Sign up and log in a fresh user. Returns email and auth headers."""
    email = f"{role}_{uuid.uuid4().hex[:12]}@example.com"
    password = "secure_password_123!"
    response = await client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": password,
            "full_name": name or f"Test {role.title()}",
            "user_type": role,
        },
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"email": email, "headers": {"Authorization": f"Bearer {token}"}}


def paper_payload(**overrides) -> dict:
    payload = {
        "title": "CS Fundamentals Quiz",
        "start_date": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "duration_minutes": 60,
        "is_published": True,
        "questions": [
            {
                "question_text": "Which OOP principle lets a subclass override a method of its parent class?",
                "model_answer": "Polymorphism",
                "rubric": "Full marks for Polymorphism",
                "marks_assigned": 5,
                "sort_order": 1,
            },
            {
                "question_text": "Explain what a deadlock is in an operating system in one sentence.",
                "model_answer": "A set of processes each hold a resource and wait for one held by another, so none can proceed.",
                "rubric": None,
                "marks_assigned": 10,
                "sort_order": 2,
            },
        ],
    }
    payload.update(overrides)
    return payload


@pytest_asyncio.fixture
async def classroom(client):
    """A teacher, a student in their class, and an open two-question paper."""
    teacher = await register(client, "teacher")
    student = await register(client, "student")

    response = await client.post(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=teacher["headers"],
    )
    assert response.status_code == 200, response.text

    response = await client.post(
        "/api/papers/", json=paper_payload(), headers=teacher["headers"]
    )
    assert response.status_code == 201, response.text
    paper = response.json()

    yield SimpleNamespace(
        teacher=teacher,
        student=student,
        paper=paper,
        qpid=paper["qpid"],
        qids=[q["qid"] for q in paper["questions"]],
    )

    for user in (teacher, student):
        await client.delete("/api/auth/", headers=user["headers"])
