"""Things that go wrong in real use: simultaneous requests, hostile input,
a misbehaving LLM, and attempts to get around the rules."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.model import UserUsage
from app.database import AsyncSessionLocal
from tests.conftest import paper_payload, register

pytestmark = pytest.mark.asyncio


async def _submit(client, room, answers: dict[int, str], student=None):
    student = student or room.student
    response = await client.post(
        f"/api/submissions/{room.qpid}",
        json={
            "answers": [
                {"qid": qid, "student_answer": text} for qid, text in answers.items()
            ]
        },
        headers=student["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _usage(client, user) -> dict:
    return (await client.get("/api/auth/usage", headers=user["headers"])).json()


async def _set_usage(email: str, **columns) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(UserUsage, email)
        for name, value in columns.items():
            setattr(row, name, value)
        await session.commit()


def _once(action):
    """Wrap an async action so it runs during the first LLM call only."""
    state = {"done": False}

    async def hook(_kwargs):
        if not state["done"]:
            state["done"] = True
            await action()

    return hook


# --------------------------------------------------------------------------
# Things that change while the LLM is working
# --------------------------------------------------------------------------


async def test_marks_never_land_on_a_resubmitted_answer(client, classroom, fake_llm):
    q1, q2 = classroom.qids
    room, student, teacher = classroom, classroom.student, classroom.teacher
    own = f"/api/submissions/{room.qpid}/{student['email']}"
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait on each other forever"})

    async def withdraw_and_resubmit():
        assert (await client.delete(own, headers=student["headers"])).status_code == 204
        await _submit(client, room, {q1: "garbage one", q2: "garbage two"})

    fake_llm.during_call = _once(withdraw_and_resubmit)
    fake_llm.reply = json.dumps({"score": 5, "feedback": "Perfect, Polymorphism is right"})

    response = await client.post(
        f"/api/evaluations/{room.qpid}/{student['email']}", headers=teacher["headers"]
    )

    assert response.status_code == 200, response.text
    data = response.json()
    # The marks belonged to the old answers, so none of them were stored
    assert data["evaluated"] is False
    assert float(data["total_marks_obtained"]) == 0.0
    assert [a["student_answer"] for a in data["answers"]] == [
        "garbage one",
        "garbage two",
    ]
    assert all(a["status"] == "pending" for a in data["answers"])
    assert all(a["feedback"] is None for a in data["answers"])
    assert "discarded" in data["message"]
    # The LLM calls happened, so they are still billed
    assert data["tokens_used"] == 200


async def test_reset_during_evaluation_does_not_release_half_a_result(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    room, student, teacher = classroom, classroom.student, classroom.teacher
    base = f"/api/evaluations/{room.qpid}/{student['email']}"
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait forever"})
    await client.patch(
        f"{base}/{q1}", json={"marks_obtained": 4}, headers=teacher["headers"]
    )

    async def reset():
        assert (
            await client.delete(base, headers=teacher["headers"])
        ).status_code == 200

    fake_llm.during_call = _once(reset)
    fake_llm.reply = json.dumps({"score": 2, "feedback": "ok"})

    response = await client.post(base, headers=teacher["headers"])

    data = response.json()
    by_qid = {a["qid"]: a for a in data["answers"]}
    assert by_qid[q1]["status"] == "pending"  # the reset stands
    assert by_qid[q2]["status"] == "success"
    assert data["evaluated"] is False
    assert float(data["total_marks_obtained"]) == 2.0

    seen = (
        await client.get(
            f"/api/submissions/{room.qpid}/{student['email']}",
            headers=student["headers"],
        )
    ).json()
    assert seen["evaluated"] is False
    assert float(seen["total_marks_obtained"]) == 0.0
    assert all(a["feedback"] is None for a in seen["answers"])


async def test_override_during_evaluation_is_kept_and_total_is_right(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    room, student, teacher = classroom, classroom.student, classroom.teacher
    base = f"/api/evaluations/{room.qpid}/{student['email']}"
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait forever"})

    async def override():
        response = await client.patch(
            f"{base}/{q1}",
            json={"marks_obtained": 5, "feedback": "Teacher says full marks"},
            headers=teacher["headers"],
        )
        assert response.status_code == 200

    fake_llm.during_call = _once(override)
    fake_llm.reply = json.dumps({"score": 1, "feedback": "AI says 1"})

    data = (await client.post(base, headers=teacher["headers"])).json()

    by_qid = {a["qid"]: a for a in data["answers"]}
    assert float(by_qid[q1]["marks_obtained"]) == 5.0
    assert by_qid[q1]["feedback"] == "Teacher says full marks"
    assert float(by_qid[q2]["marks_obtained"]) == 1.0
    assert data["evaluated"] is True
    assert float(data["total_marks_obtained"]) == 6.0


async def test_withdrawal_during_evaluation_is_reported_not_a_crash(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    room, student, teacher = classroom, classroom.student, classroom.teacher
    own = f"/api/submissions/{room.qpid}/{student['email']}"
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait forever"})
    before = await _usage(client, teacher)

    async def withdraw():
        assert (await client.delete(own, headers=student["headers"])).status_code == 204

    fake_llm.during_call = _once(withdraw)

    response = await client.post(
        f"/api/evaluations/{room.qpid}/{student['email']}", headers=teacher["headers"]
    )

    assert response.status_code == 409
    assert "withdrawn" in response.json()["detail"]
    after = await _usage(client, teacher)
    assert before["llm_tokens_balance"] - after["llm_tokens_balance"] == 200


async def test_paper_evaluation_survives_a_student_withdrawing(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    room, teacher = classroom, classroom.teacher
    second = await register(client, "student")
    await client.post(
        "/api/auth/associations",
        params={"s_email": second["email"]},
        headers=teacher["headers"],
    )
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait forever"})
    await _submit(client, room, {q1: "Lyon", q2: "No idea"}, student=second)

    async def second_student_withdraws():
        response = await client.delete(
            f"/api/submissions/{room.qpid}/{second['email']}",
            headers=second["headers"],
        )
        assert response.status_code == 204

    fake_llm.during_call = _once(second_student_withdraws)

    response = await client.post(
        f"/api/evaluations/{room.qpid}", headers=teacher["headers"]
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["submission_count"] == 1
    assert data["evaluated_count"] == 1
    assert [s["s_email"] for s in data["submissions"]] == [room.student["email"]]

    await client.delete("/api/auth/", headers=second["headers"])


async def test_unexpected_llm_error_fails_one_answer_not_the_request(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    room, teacher = classroom, classroom.teacher
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait forever"})

    def reply(kwargs):
        if "Polymorphism" in kwargs["messages"][1]["content"]:
            return RuntimeError("something nobody planned for")
        return json.dumps({"score": 3, "feedback": "ok"})

    fake_llm.reply = reply
    before = await _usage(client, teacher)

    response = await client.post(
        f"/api/evaluations/{room.qpid}/{room.student['email']}",
        headers=teacher["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    by_qid = {a["qid"]: a for a in data["answers"]}
    assert by_qid[q1]["status"] == "failed"
    assert by_qid[q2]["status"] == "success"
    assert data["failed_count"] == 1
    # The call that worked is billed
    after = await _usage(client, teacher)
    assert before["llm_tokens_balance"] - after["llm_tokens_balance"] == 100


# --------------------------------------------------------------------------
# Limits under simultaneous requests
# --------------------------------------------------------------------------


async def test_paper_limit_holds_under_simultaneous_requests(client):
    teacher = await register(client, "teacher")
    await _set_usage(teacher["email"], papers_created_balance_monthly=2)

    responses = await asyncio.gather(
        *(
            client.post(
                "/api/papers/", json=paper_payload(), headers=teacher["headers"]
            )
            for _ in range(8)
        )
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 201] + [402] * 6
    usage = await _usage(client, teacher)
    assert usage["papers_created_balance"] == 0
    assert usage["total_papers_created"] == 2
    papers = (await client.get("/api/papers/", headers=teacher["headers"])).json()
    assert len(papers) == 2

    await client.delete("/api/auth/", headers=teacher["headers"])


async def test_submission_limit_holds_and_failed_attempts_cost_nothing(
    client, classroom
):
    q1, _ = classroom.qids
    student = classroom.student
    await _set_usage(student["email"], submissions_made_balance_monthly=1)
    url = f"/api/submissions/{classroom.qpid}"

    # A rejected submission must not use up the allowance
    bad = await client.post(
        url,
        json={"answers": [{"qid": 999_999, "student_answer": "x"}]},
        headers=student["headers"],
    )
    assert bad.status_code == 400
    assert (await _usage(client, student))["submissions_made_balance"] == 1

    good = await client.post(
        url,
        json={"answers": [{"qid": q1, "student_answer": "Polymorphism"}]},
        headers=student["headers"],
    )
    assert good.status_code == 201
    usage = await _usage(client, student)
    assert usage["submissions_made_balance"] == 0
    assert usage["total_submissions_made"] == 1

    # Next paper: nothing left this month
    second_paper = (
        await client.post(
            "/api/papers/", json=paper_payload(), headers=classroom.teacher["headers"]
        )
    ).json()
    response = await client.post(
        f"/api/submissions/{second_paper['qpid']}",
        json={"answers": []},
        headers=student["headers"],
    )
    assert response.status_code == 402


async def test_tokens_of_simultaneous_evaluations_are_all_charged(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    room, teacher = classroom, classroom.teacher
    second = await register(client, "student")
    await client.post(
        "/api/auth/associations",
        params={"s_email": second["email"]},
        headers=teacher["headers"],
    )
    await _submit(client, room, {q1: "Polymorphism", q2: "Waiting"})
    await _submit(client, room, {q1: "Lyon", q2: "Dark"}, student=second)

    async def slow(_kwargs):
        await asyncio.sleep(0.05)

    fake_llm.during_call = slow
    before = await _usage(client, teacher)

    first, other = await asyncio.gather(
        client.post(
            f"/api/evaluations/{room.qpid}/{room.student['email']}",
            headers=teacher["headers"],
        ),
        client.post(
            f"/api/evaluations/{room.qpid}/{second['email']}",
            headers=teacher["headers"],
        ),
    )

    assert first.status_code == other.status_code == 200
    spent = first.json()["tokens_used"] + other.json()["tokens_used"]
    assert spent == 400
    after = await _usage(client, teacher)
    assert before["llm_tokens_balance"] - after["llm_tokens_balance"] == spent
    assert after["total_llm_tokens_used"] - before["total_llm_tokens_used"] == spent

    await client.delete("/api/auth/", headers=second["headers"])


# --------------------------------------------------------------------------
# Getting around the rules
# --------------------------------------------------------------------------


async def test_old_token_is_useless_after_the_email_is_registered_again(client):
    first = await register(client, "teacher")
    email = first["email"]
    assert (
        await client.delete("/api/auth/", headers=first["headers"])
    ).status_code == 204

    # Someone else signs up with the same address
    response = await client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "a-different-password",
            "full_name": "Second Owner",
            "user_type": "teacher",
        },
    )
    assert response.status_code == 201

    assert (
        await client.get("/api/auth/me", headers=first["headers"])
    ).status_code == 401
    response = await client.post(
        "/api/papers/", json=paper_payload(), headers=first["headers"]
    )
    assert response.status_code == 401

    login = await client.post(
        "/api/auth/login",
        data={"username": email, "password": "a-different-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    await client.delete("/api/auth/", headers=headers)


async def test_student_cannot_retry_after_reading_feedback_even_after_a_reset(
    client, classroom, fake_llm
):
    q1, _ = classroom.qids
    room, student, teacher = classroom, classroom.student, classroom.teacher
    own = f"/api/submissions/{room.qpid}/{student['email']}"
    await _submit(client, room, {q1: "Lyon"})
    await client.post(f"/api/evaluations/{room.qpid}", headers=teacher["headers"])
    # The student has now been able to read the feedback
    assert (await client.get(own, headers=student["headers"])).json()["evaluated"]

    await client.delete(f"/api/evaluations/{room.qpid}", headers=teacher["headers"])

    assert (await client.delete(own, headers=student["headers"])).status_code == 403
    # Only the teacher can allow another attempt
    assert (await client.delete(own, headers=teacher["headers"])).status_code == 204


async def test_closed_paper_is_not_readable_by_students_who_did_not_answer(
    client, classroom
):
    response = await client.patch(
        f"/api/papers/{classroom.qpid}",
        json={"is_closed": True},
        headers=classroom.teacher["headers"],
    )
    assert response.json()["status"] == "closed"

    response = await client.get(
        f"/api/papers/{classroom.qpid}", headers=classroom.student["headers"]
    )
    assert response.status_code == 403
    assert "Which OOP principle" not in response.text


async def test_student_cannot_tell_which_answers_are_graded_yet(client, classroom):
    q1, q2 = classroom.qids
    room, student, teacher = classroom, classroom.student, classroom.teacher
    await _submit(client, room, {q1: "Polymorphism", q2: "Processes wait forever"})
    await client.patch(
        f"/api/evaluations/{room.qpid}/{student['email']}/{q1}",
        json={"marks_obtained": 5},
        headers=teacher["headers"],
    )

    seen = (
        await client.get(
            f"/api/submissions/{room.qpid}/{student['email']}",
            headers=student["headers"],
        )
    ).json()

    assert seen["updated_at"] is None
    assert {a["updated_at"] for a in seen["answers"]} == {None}
    assert {a["status"] for a in seen["answers"]} == {"pending"}


# --------------------------------------------------------------------------
# Hostile or broken input is answered with 4xx, never 500
# --------------------------------------------------------------------------

HUGE = 2**40
ASTRONOMICAL = 10**25


@pytest.mark.parametrize("number", [0, -1, HUGE, ASTRONOMICAL])
async def test_out_of_range_ids_are_rejected(client, classroom, number):
    teacher, student = classroom.teacher["headers"], classroom.student["headers"]
    email = classroom.student["email"]
    requests = [
        client.get(f"/api/papers/{number}", headers=teacher),
        client.patch(f"/api/papers/{number}", json={"title": "x"}, headers=teacher),
        client.delete(f"/api/papers/{number}", headers=teacher),
        client.get(f"/api/submissions/{number}", headers=teacher),
        client.post(f"/api/submissions/{number}", json={}, headers=student),
        client.get(f"/api/submissions/{number}/{email}", headers=teacher),
        client.post(f"/api/evaluations/{number}", headers=teacher),
        client.delete(f"/api/evaluations/{number}", headers=teacher),
        client.post(f"/api/evaluations/{number}/{email}", headers=teacher),
        client.patch(
            f"/api/evaluations/{classroom.qpid}/{email}/{number}",
            json={"marks_obtained": 1},
            headers=teacher,
        ),
    ]
    for response in await asyncio.gather(*requests):
        assert response.status_code == 422, response.request.url


async def test_out_of_range_numbers_in_bodies_and_queries(client, classroom):
    teacher, student = classroom.teacher["headers"], classroom.student["headers"]
    question = {"question_text": "Q", "marks_assigned": 1}

    for sort_order in (HUGE, ASTRONOMICAL, -1):
        response = await client.post(
            "/api/papers/",
            json=paper_payload(questions=[{**question, "sort_order": sort_order}]),
            headers=teacher,
        )
        assert response.status_code == 422

    for qid in (HUGE, ASTRONOMICAL, 0):
        response = await client.post(
            f"/api/submissions/{classroom.qpid}",
            json={"answers": [{"qid": qid, "student_answer": "x"}]},
            headers=student,
        )
        assert response.status_code == 422
        response = await client.patch(
            f"/api/papers/{classroom.qpid}",
            json={"questions": [{"qid": qid}]},
            headers=teacher,
        )
        assert response.status_code == 422

    for skip in (HUGE, ASTRONOMICAL, -1):
        response = await client.get(
            "/api/papers/", params={"skip": skip}, headers=teacher
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "start_date",
    [
        "9999-12-31T23:59:59-05:00",
        "0001-01-01T00:00:00+05:00",
        "1850-06-01T00:00:00Z",
        "not a date",
    ],
)
async def test_absurd_dates_are_rejected(client, classroom, start_date):
    headers = classroom.teacher["headers"]
    response = await client.post(
        "/api/papers/", json=paper_payload(start_date=start_date), headers=headers
    )
    assert response.status_code == 422
    response = await client.patch(
        f"/api/papers/{classroom.qpid}",
        json={"start_date": start_date},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad", ["nul\x00byte", "lone\ud800surrogate"])
async def test_text_the_database_cannot_store_is_rejected(client, classroom, bad):
    teacher, student = classroom.teacher["headers"], classroom.student["headers"]
    q1, _ = classroom.qids
    question = {"question_text": "Q", "marks_assigned": 1}

    def body(payload):
        # httpx refuses to encode lone surrogates itself, so send raw JSON
        return {
            "content": json.dumps(payload).encode("ascii"),
            "headers": {"Content-Type": "application/json"},
        }

    def post(url, payload, auth):
        extra = body(payload)
        return client.post(
            url, content=extra["content"], headers={**auth, **extra["headers"]}
        )

    def patch(url, payload, auth):
        extra = body(payload)
        return client.patch(
            url, content=extra["content"], headers={**auth, **extra["headers"]}
        )

    responses = [
        await post("/api/papers/", paper_payload(title=bad), teacher),
        await post(
            "/api/papers/",
            paper_payload(questions=[{**question, "model_answer": bad}]),
            teacher,
        ),
        await patch(f"/api/papers/{classroom.qpid}", {"title": bad}, teacher),
        await post(
            f"/api/submissions/{classroom.qpid}",
            {"answers": [{"qid": q1, "student_answer": bad}]},
            student,
        ),
        await post(
            "/api/auth/signup",
            {
                "email": "clean@example.com",
                "password": "secure_password_123!",
                "full_name": bad,
                "user_type": "student",
            },
            {},
        ),
        await post(
            "/api/auth/signup",
            {
                "email": "clean2@example.com",
                "password": bad + "long-enough",
                "full_name": "Name",
                "user_type": "student",
            },
            {},
        ),
    ]
    for response in responses:
        assert response.status_code == 422, response.request.url


async def test_nul_bytes_in_urls_and_login(client, classroom):
    teacher = classroom.teacher["headers"]
    nul_email = "a%00b@example.com"

    response = await client.post(
        "/api/auth/login", data={"username": "a\x00b@example.com", "password": "x"}
    )
    assert response.status_code == 401
    response = await client.post(
        "/api/auth/login",
        data={"username": classroom.teacher["email"], "password": "pw\x00pw"},
    )
    assert response.status_code == 401

    for method, url in [
        ("GET", f"/api/submissions/{classroom.qpid}/{nul_email}"),
        ("DELETE", f"/api/submissions/{classroom.qpid}/{nul_email}"),
        ("POST", f"/api/evaluations/{classroom.qpid}/{nul_email}"),
        ("DELETE", f"/api/evaluations/{classroom.qpid}/{nul_email}"),
        ("POST", f"/api/auth/associations?s_email={nul_email}"),
        ("DELETE", f"/api/auth/associations?s_email={nul_email}"),
    ]:
        response = await client.request(method, url, headers=teacher)
        assert response.status_code == 422, (method, url)


@pytest.mark.parametrize("email", ["st/udent@example.com", "st\\udent@example.com"])
async def test_emails_that_cannot_appear_in_a_url_are_refused(client, email):
    response = await client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "secure_password_123!",
            "full_name": "Slash",
            "user_type": "student",
        },
    )
    assert response.status_code == 422


async def test_email_with_plus_and_dots_works_end_to_end(client, classroom, fake_llm):
    # Characters that need URL-encoding must still round-trip
    email = "sam.o+quiz@example.com"
    password = "secure_password_123!"
    await client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": password,
            "full_name": "Sam",
            "user_type": "student",
        },
    )
    login = await client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    teacher = classroom.teacher["headers"]
    await client.post(
        "/api/auth/associations", params={"s_email": email}, headers=teacher
    )
    await _submit(
        client, classroom, {classroom.qids[0]: "Polymorphism"}, student={"headers": headers}
    )

    encoded = "sam.o%2Bquiz%40example.com"
    response = await client.get(
        f"/api/submissions/{classroom.qpid}/{encoded}", headers=teacher
    )
    assert response.status_code == 200
    assert response.json()["s_email"] == email
    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{encoded}", headers=teacher
    )
    assert response.status_code == 200
    assert response.json()["evaluated"] is True

    await client.delete("/api/auth/", headers=headers)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


async def test_development_secret_is_random_and_kept_between_starts(
    tmp_path, monkeypatch
):
    from app import config

    monkeypatch.chdir(tmp_path)
    first = config._load_or_create_dev_secret()
    assert len(first) >= 32
    assert config._load_or_create_dev_secret() == first  # survives a restart

    (tmp_path / ".dev_secret_key").unlink()
    assert config._load_or_create_dev_secret() != first  # never a fixed value


async def test_production_refuses_to_start_without_a_secret(monkeypatch):
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="")

    assert (
        Settings(
            _env_file=None, ENVIRONMENT="production", SECRET_KEY="x" * 40
        ).SECRET_KEY
        == "x" * 40
    )


async def test_scheduled_paper_opens_at_its_start_time(client, classroom):
    # Guards the time zone handling: "now" in another zone is still now
    ist = timezone(timedelta(hours=5, minutes=30))
    just_passed = (datetime.now(ist) - timedelta(minutes=1)).isoformat()
    soon = (datetime.now(ist) + timedelta(minutes=5)).isoformat()
    headers = classroom.teacher["headers"]

    opened = await client.post(
        "/api/papers/", json=paper_payload(start_date=just_passed), headers=headers
    )
    waiting = await client.post(
        "/api/papers/", json=paper_payload(start_date=soon), headers=headers
    )

    assert opened.json()["status"] == "open"
    assert waiting.json()["status"] == "scheduled"
