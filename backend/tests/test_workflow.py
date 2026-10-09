"""Tests for access rules and the paper / submission workflow."""

from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import paper_payload, register

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------


async def test_login_returns_bearer_token_and_profile(client):
    user = await register(client, "teacher", name="Ada Lovelace")

    response = await client.post(
        "/api/auth/login",
        # Email matching is case-insensitive
        data={"username": user["email"].upper(), "password": "secure_password_123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["email"] == user["email"]
    assert data["role"] == "teacher"
    assert data["full_name"] == "Ada Lovelace"

    me = await client.get("/api/auth/me", headers=user["headers"])
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]
    assert me.json()["user_type"] == "teacher"
    assert "password_hash" not in me.json()

    await client.delete("/api/auth/", headers=user["headers"])


async def test_invalid_or_missing_token_is_rejected(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    response = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


async def test_token_of_deleted_account_stops_working(client):
    user = await register(client, "teacher")
    assert (
        await client.delete("/api/auth/", headers=user["headers"])
    ).status_code == 204

    assert (
        await client.get("/api/auth/me", headers=user["headers"])
    ).status_code == 401
    response = await client.post(
        "/api/papers/", json=paper_payload(), headers=user["headers"]
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "field, value",
    [("password", "short"), ("full_name", "   "), ("user_type", "admin")],
)
async def test_signup_validation(client, field, value):
    payload = {
        "email": "validation@example.com",
        "password": "secure_password_123!",
        "full_name": "Someone",
        "user_type": "student",
    }
    payload[field] = value
    response = await client.post("/api/auth/signup", json=payload)
    assert response.status_code == 422


async def test_class_membership(client, classroom):
    teacher, student = classroom.teacher, classroom.student

    # Adding the same student twice is a conflict, not a server error
    response = await client.post(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=teacher["headers"],
    )
    assert response.status_code == 409

    data = (
        await client.get("/api/auth/associations", headers=teacher["headers"])
    ).json()
    assert data["associations"] == [student["email"]]
    assert data["users"] == [{"email": student["email"], "full_name": "Test Student"}]

    data = (
        await client.get("/api/auth/associations", headers=student["headers"])
    ).json()
    assert data["associations"] == [teacher["email"]]

    # Students cannot remove themselves or anyone else
    response = await client.delete(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=student["headers"],
    )
    assert response.status_code == 403

    response = await client.delete(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=teacher["headers"],
    )
    assert response.status_code == 204
    response = await client.delete(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=teacher["headers"],
    )
    assert response.status_code == 404

    # No longer in the class: the paper is gone from the student's list
    papers = (await client.get("/api/papers/", headers=student["headers"])).json()
    assert papers == []
    response = await client.get(
        f"/api/papers/{classroom.qpid}", headers=student["headers"]
    )
    assert response.status_code == 403


async def test_usage_is_refilled_on_a_new_month(client, classroom):
    from app.auth.model import UserUsage
    from app.config import settings
    from app.database import AsyncSessionLocal

    email = classroom.teacher["email"]
    usage = (
        await client.get("/api/auth/usage", headers=classroom.teacher["headers"])
    ).json()
    # One paper was created by the fixture
    assert usage["papers_created_balance"] == settings.PAPERS_CREATED_MONTHLY_LIMIT - 1
    assert usage["total_papers_created"] == 1

    async with AsyncSessionLocal() as session:
        row = await session.get(UserUsage, email)
        row.last_reset_date = date.today().replace(day=1) - timedelta(days=1)
        row.llm_tokens_balance_monthly = 0
        await session.commit()

    usage = (
        await client.get("/api/auth/usage", headers=classroom.teacher["headers"])
    ).json()
    assert usage["papers_created_balance"] == settings.PAPERS_CREATED_MONTHLY_LIMIT
    assert usage["llm_tokens_balance"] == settings.LLM_TOKEN_BALANCE_MONTHLY_LIMIT
    assert usage["last_reset_date"] == date.today().isoformat()
    # Lifetime totals are not reset
    assert usage["total_papers_created"] == 1

    # Students can read their own usage too
    response = await client.get("/api/auth/usage", headers=classroom.student["headers"])
    assert response.status_code == 200


async def test_paper_creation_limit(client, monkeypatch):
    from app.auth.model import UserUsage
    from app.database import AsyncSessionLocal

    teacher = await register(client, "teacher")
    async with AsyncSessionLocal() as session:
        row = await session.get(UserUsage, teacher["email"])
        row.papers_created_balance_monthly = 0
        await session.commit()

    response = await client.post(
        "/api/papers/", json=paper_payload(), headers=teacher["headers"]
    )
    assert response.status_code == 402

    await client.delete("/api/auth/", headers=teacher["headers"])


# --------------------------------------------------------------------------
# Papers
# --------------------------------------------------------------------------


async def test_student_lists_and_reads_assigned_papers(client, classroom):
    papers = (
        await client.get("/api/papers/", headers=classroom.student["headers"])
    ).json()

    assert len(papers) == 1
    paper = papers[0]
    assert paper["qpid"] == classroom.qpid
    assert paper["status"] == "open"
    assert paper["question_count"] == 2
    assert paper["teacher_name"] == "Test Teacher"
    assert paper["attempted"] is False
    assert paper["evaluated"] is False
    assert paper["marks_obtained"] is None

    response = await client.get(
        f"/api/papers/{classroom.qpid}", headers=classroom.student["headers"]
    )
    assert response.status_code == 200
    detail = response.json()
    assert len(detail["questions"]) == 2
    # Students must never receive the model answer or the rubric
    for question in detail["questions"]:
        assert "model_answer" not in question
        assert "rubric" not in question
    assert "Polymorphism" not in response.text


async def test_teacher_reads_own_paper_with_model_answers(client, classroom):
    response = await client.get(
        f"/api/papers/{classroom.qpid}", headers=classroom.teacher["headers"]
    )
    assert response.status_code == 200
    questions = response.json()["questions"]
    assert questions[0]["model_answer"] == "Polymorphism"
    assert questions[0]["rubric"] == "Full marks for Polymorphism"
    assert float(response.json()["total_marks"]) == 15.0

    papers = (
        await client.get("/api/papers", headers=classroom.teacher["headers"])
    ).json()
    assert [p["qpid"] for p in papers] == [classroom.qpid]
    assert papers[0]["submission_count"] == 0


async def test_questions_come_back_in_sort_order(client):
    teacher = await register(client, "teacher")
    questions = [
        {"question_text": "third", "marks_assigned": 1, "sort_order": 3},
        {"question_text": "first", "marks_assigned": 1, "sort_order": 1},
        {"question_text": "second", "marks_assigned": 1, "sort_order": 2},
    ]
    response = await client.post(
        "/api/papers/",
        json=paper_payload(questions=questions),
        headers=teacher["headers"],
    )
    assert [q["question_text"] for q in response.json()["questions"]] == [
        "first",
        "second",
        "third",
    ]
    await client.delete("/api/auth/", headers=teacher["headers"])


async def test_draft_and_scheduled_papers_are_hidden_from_students(client, classroom):
    teacher, student = classroom.teacher, classroom.student
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    draft = (
        await client.post(
            "/api/papers/",
            json=paper_payload(title="Draft", is_published=False),
            headers=teacher["headers"],
        )
    ).json()
    scheduled = (
        await client.post(
            "/api/papers/",
            json=paper_payload(title="Scheduled", start_date=tomorrow),
            headers=teacher["headers"],
        )
    ).json()
    assert draft["status"] == "draft"
    assert scheduled["status"] == "scheduled"

    listed = (await client.get("/api/papers/", headers=student["headers"])).json()
    titles = {p["title"]: p["status"] for p in listed}
    # A scheduled paper is announced, but its questions stay hidden
    assert titles == {"CS Fundamentals Quiz": "open", "Scheduled": "scheduled"}

    for paper in (draft, scheduled):
        response = await client.get(
            f"/api/papers/{paper['qpid']}", headers=student["headers"]
        )
        assert response.status_code == 403
        response = await client.post(
            f"/api/submissions/{paper['qpid']}",
            json={"answers": []},
            headers=student["headers"],
        )
        assert response.status_code == 403


async def test_other_teachers_and_unrelated_students_cannot_read_a_paper(
    client, classroom
):
    other_teacher = await register(client, "teacher")
    outsider = await register(client, "student")

    for user in (other_teacher, outsider):
        response = await client.get(
            f"/api/papers/{classroom.qpid}", headers=user["headers"]
        )
        assert response.status_code == 403
        papers = (await client.get("/api/papers/", headers=user["headers"])).json()
        assert papers == []

    # Updating or deleting someone else's paper looks like it does not exist
    response = await client.patch(
        f"/api/papers/{classroom.qpid}",
        json={"title": "Hijacked"},
        headers=other_teacher["headers"],
    )
    assert response.status_code == 404
    response = await client.delete(
        f"/api/papers/{classroom.qpid}", headers=other_teacher["headers"]
    )
    assert response.status_code == 404

    for user in (other_teacher, outsider):
        await client.delete("/api/auth/", headers=user["headers"])


async def test_paper_validation(client):
    teacher = await register(client, "teacher")
    cases = [
        paper_payload(title="   "),
        paper_payload(duration_minutes=0),
        paper_payload(questions=[]),  # published without questions
        paper_payload(questions=[{"question_text": "Q", "marks_assigned": 0}]),
        paper_payload(questions=[{"question_text": "Q", "marks_assigned": -2}]),
        paper_payload(questions=[{"question_text": "  ", "marks_assigned": 2}]),
    ]
    for payload in cases:
        response = await client.post(
            "/api/papers/", json=payload, headers=teacher["headers"]
        )
        assert response.status_code == 422, payload

    # A draft may start out empty
    response = await client.post(
        "/api/papers/",
        json=paper_payload(questions=[], is_published=False),
        headers=teacher["headers"],
    )
    assert response.status_code == 201
    # ...but it cannot be published while it has no questions
    response = await client.patch(
        f"/api/papers/{response.json()['qpid']}",
        json={"is_published": True},
        headers=teacher["headers"],
    )
    assert response.status_code == 400

    await client.delete("/api/auth/", headers=teacher["headers"])


async def test_update_paper_questions(client, classroom):
    q1, q2 = classroom.qids
    headers = classroom.teacher["headers"]
    url = f"/api/papers/{classroom.qpid}"

    # Keep q1 (new marks), drop q2, add a new question
    response = await client.patch(
        url,
        json={
            "title": "Renamed",
            "questions": [
                {"qid": q1, "marks_assigned": 7},
                {"question_text": "A new question", "marks_assigned": 3},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "Renamed"
    assert [q["question_text"] for q in data["questions"]] == [
        "A new question",
        "Which OOP principle lets a subclass override a method of its parent class?",
    ]
    assert float(data["total_marks"]) == 10.0
    assert q2 not in [q["qid"] for q in data["questions"]]

    # A new question needs text and marks
    response = await client.patch(
        url, json={"questions": [{"question_text": "No marks"}]}, headers=headers
    )
    assert response.status_code == 400

    # A qid from nowhere is rejected instead of silently creating a question
    response = await client.patch(
        url,
        json={"questions": [{"qid": 999_999, "marks_assigned": 1}]},
        headers=headers,
    )
    assert response.status_code == 400

    # Explicit nulls on required fields are ignored, not written to the database
    response = await client.patch(
        url, json={"title": None, "start_date": None}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


async def test_questions_are_frozen_once_there_are_submissions(client, classroom):
    q1, q2 = classroom.qids
    headers = classroom.teacher["headers"]
    url = f"/api/papers/{classroom.qpid}"
    await client.post(
        f"/api/submissions/{classroom.qpid}",
        json={"answers": [{"qid": q1, "student_answer": "Polymorphism"}]},
        headers=classroom.student["headers"],
    )

    blocked = [
        [{"qid": q1}],  # removes q2
        [{"qid": q1}, {"qid": q2}, {"question_text": "New", "marks_assigned": 1}],
        [{"qid": q1, "marks_assigned": 50}, {"qid": q2}],
        [{"qid": q1, "question_text": "Reworded"}, {"qid": q2}],
    ]
    for questions in blocked:
        response = await client.patch(
            url, json={"questions": questions}, headers=headers
        )
        assert response.status_code == 409, questions

    # Refining the model answer and rubric is still allowed
    response = await client.patch(
        url,
        json={
            "questions": [
                {"qid": q1, "model_answer": "Polymorphism (method overriding)", "rubric": "Strict"},
                {"qid": q2},
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["questions"][0]["model_answer"] == "Polymorphism (method overriding)"


# --------------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------------


async def test_submission_validation(client, classroom):
    q1, _ = classroom.qids
    url = f"/api/submissions/{classroom.qpid}"
    headers = classroom.student["headers"]

    response = await client.post(
        url,
        json={"answers": [{"qid": 999_999, "student_answer": "x"}]},
        headers=headers,
    )
    assert response.status_code == 400

    response = await client.post(
        url,
        json={
            "answers": [
                {"qid": q1, "student_answer": "a"},
                {"qid": q1, "student_answer": "b"},
            ]
        },
        headers=headers,
    )
    assert response.status_code == 400

    response = await client.post(
        url,
        json={"answers": [{"qid": q1, "student_answer": "x" * 20_001}]},
        headers=headers,
    )
    assert response.status_code == 422

    # Nothing was stored by the rejected attempts
    assert (await client.get(url, headers=headers)).json() == []

    response = await client.post("/api/submissions/999999", json={}, headers=headers)
    assert response.status_code == 404


async def test_student_outside_the_class_cannot_submit(client, classroom):
    outsider = await register(client, "student")
    response = await client.post(
        f"/api/submissions/{classroom.qpid}",
        json={"answers": [{"qid": classroom.qids[0], "student_answer": "Polymorphism"}]},
        headers=outsider["headers"],
    )
    assert response.status_code == 403
    await client.delete("/api/auth/", headers=outsider["headers"])


async def test_closed_paper_rejects_new_submissions(client, classroom):
    headers = classroom.teacher["headers"]
    url = f"/api/papers/{classroom.qpid}"
    answer = {"answers": [{"qid": classroom.qids[0], "student_answer": "Polymorphism"}]}

    response = await client.patch(url, json={"is_closed": True}, headers=headers)
    assert response.json()["status"] == "closed"

    response = await client.post(
        f"/api/submissions/{classroom.qpid}",
        json=answer,
        headers=classroom.student["headers"],
    )
    assert response.status_code == 403
    assert "closed" in response.json()["detail"]

    response = await client.patch(url, json={"is_closed": False}, headers=headers)
    assert response.json()["status"] == "open"
    response = await client.post(
        f"/api/submissions/{classroom.qpid}",
        json=answer,
        headers=classroom.student["headers"],
    )
    assert response.status_code == 201

    # The student keeps access to a paper they answered, even after it closes
    await client.patch(
        url, json={"is_closed": True, "is_published": False}, headers=headers
    )
    response = await client.get(url, headers=classroom.student["headers"])
    assert response.status_code == 200


async def test_teachers_only_see_submissions_of_their_own_papers(client, classroom):
    q1, _ = classroom.qids
    s_email = classroom.student["email"]
    await client.post(
        f"/api/submissions/{classroom.qpid}",
        json={"answers": [{"qid": q1, "student_answer": "Polymorphism"}]},
        headers=classroom.student["headers"],
    )
    other_teacher = await register(client, "teacher")
    other_student = await register(client, "student")
    list_url = f"/api/submissions/{classroom.qpid}"
    detail_url = f"{list_url}/{s_email}"

    assert (
        await client.get(list_url, headers=other_teacher["headers"])
    ).status_code == 403
    assert (
        await client.get(detail_url, headers=other_teacher["headers"])
    ).status_code == 403
    assert (
        await client.delete(detail_url, headers=other_teacher["headers"])
    ).status_code == 403
    # Another student cannot read or delete it either
    assert (
        await client.get(detail_url, headers=other_student["headers"])
    ).status_code == 403
    assert (
        await client.delete(detail_url, headers=other_student["headers"])
    ).status_code == 403
    assert (await client.get(list_url, headers=other_student["headers"])).json() == []

    # The owner sees it, with the student's name
    owner_list = (
        await client.get(list_url, headers=classroom.teacher["headers"])
    ).json()
    assert [(s["s_email"], s["student_name"]) for s in owner_list] == [
        (s_email, "Test Student")
    ]
    detail = await client.get(detail_url, headers=classroom.teacher["headers"])
    assert detail.status_code == 200
    assert len(detail.json()["answers"]) == 2

    for user in (other_teacher, other_student):
        await client.delete("/api/auth/", headers=user["headers"])


async def test_student_cannot_withdraw_after_evaluation(client, classroom, fake_llm):
    q1, _ = classroom.qids
    url = f"/api/submissions/{classroom.qpid}/{classroom.student['email']}"
    await client.post(
        f"/api/submissions/{classroom.qpid}",
        json={"answers": [{"qid": q1, "student_answer": "Polymorphism"}]},
        headers=classroom.student["headers"],
    )
    await client.post(
        f"/api/evaluations/{classroom.qpid}", headers=classroom.teacher["headers"]
    )

    response = await client.delete(url, headers=classroom.student["headers"])
    assert response.status_code == 403

    # The teacher still can, which lets the student attempt the paper again
    response = await client.delete(url, headers=classroom.teacher["headers"])
    assert response.status_code == 204
    response = await client.post(
        f"/api/submissions/{classroom.qpid}",
        json={"answers": [{"qid": q1, "student_answer": "Polymorphism again"}]},
        headers=classroom.student["headers"],
    )
    assert response.status_code == 201


async def test_deleting_a_paper_removes_its_submissions(client, classroom):
    q1, _ = classroom.qids
    await client.post(
        f"/api/submissions/{classroom.qpid}",
        json={"answers": [{"qid": q1, "student_answer": "Polymorphism"}]},
        headers=classroom.student["headers"],
    )

    response = await client.delete(
        f"/api/papers/{classroom.qpid}", headers=classroom.teacher["headers"]
    )
    assert response.status_code == 204

    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.submissions.model import Answer, Submission

    async with AsyncSessionLocal() as session:
        for model in (Submission, Answer):
            count = await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.qpid == classroom.qpid)
            )
            assert count == 0


async def test_deleting_a_teacher_removes_their_papers_and_class(client):
    teacher = await register(client, "teacher")
    student = await register(client, "student")
    await client.post(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=teacher["headers"],
    )
    paper = (
        await client.post(
            "/api/papers/", json=paper_payload(), headers=teacher["headers"]
        )
    ).json()
    await client.post(
        f"/api/submissions/{paper['qpid']}",
        json={"answers": []},
        headers=student["headers"],
    )

    response = await client.delete("/api/auth", headers=teacher["headers"])
    assert response.status_code == 204

    # The student account survives, with nothing left from that teacher
    assert (await client.get("/api/papers/", headers=student["headers"])).json() == []
    associations = (
        await client.get("/api/auth/associations", headers=student["headers"])
    ).json()
    assert associations["associations"] == []
    response = await client.get(
        f"/api/submissions/{paper['qpid']}/{student['email']}",
        headers=student["headers"],
    )
    assert response.status_code == 404

    assert (
        await client.delete("/api/auth/", headers=student["headers"])
    ).status_code == 204


async def test_health_reports_llm_configuration(client, fake_llm):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["llm_configured"] is True
