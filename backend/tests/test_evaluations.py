"""End-to-end tests of the evaluation endpoints, with a fake LLM."""

import json

import groq
import httpx
import pytest

from tests.conftest import register

pytestmark = pytest.mark.asyncio


def _rate_limit_error():
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return groq.RateLimitError(
        "rate limited", response=httpx.Response(429, request=request), body=None
    )


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
    response = await client.get("/api/auth/usage", headers=user["headers"])
    assert response.status_code == 200
    return response.json()


async def test_evaluate_submission_grades_every_answer(client, classroom, fake_llm):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes block each other waiting for resources."})
    fake_llm.reply = json.dumps({"score": 4, "feedback": "Well done."})
    fake_llm.total_tokens = 150
    before = await _usage(client, classroom.teacher)

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}",
        headers=classroom.teacher["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["evaluated"] is True
    assert float(data["total_marks_obtained"]) == 8.0
    assert [a["status"] for a in data["answers"]] == ["success", "success"]
    assert [a["feedback"] for a in data["answers"]] == ["Well done.", "Well done."]
    assert data["graded_count"] == 2
    assert data["failed_count"] == 0
    assert data["tokens_used"] == 300
    assert data["message"] is None

    # The teacher's monthly token balance is charged for both calls
    after = await _usage(client, classroom.teacher)
    assert before["llm_tokens_balance"] - after["llm_tokens_balance"] == 300
    assert after["total_llm_tokens_used"] - before["total_llm_tokens_used"] == 300


async def test_llm_cannot_award_more_than_the_question_is_worth(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids  # worth 5 and 10 marks
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Something"})
    # 8 is a valid mark for the 10-mark question but not for the 5-mark one
    fake_llm.reply = json.dumps({"score": 8, "feedback": "Outstanding!"})

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}",
        headers=classroom.teacher["headers"],
    )

    data = response.json()
    by_qid = {a["qid"]: a for a in data["answers"]}
    # The off-scale score is not cut down to full marks: the answer is left
    # for the teacher to look at.
    assert by_qid[q1]["status"] == "failed"
    assert float(by_qid[q1]["marks_obtained"]) == 0.0
    assert by_qid[q2]["status"] == "success"
    assert float(by_qid[q2]["marks_obtained"]) == 8.0
    assert data["evaluated"] is False
    assert float(data["total_marks_obtained"]) == 8.0
    assert "outside 0 to 5" in data["message"]


async def test_blank_and_skipped_answers_score_zero_without_llm_calls(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    # q2 is not sent at all; q1 is whitespace only
    submission = await _submit(client, classroom, {q1: "   "})
    assert len(submission["answers"]) == 2

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}",
        headers=classroom.teacher["headers"],
    )

    data = response.json()
    assert fake_llm.calls == []
    assert data["evaluated"] is True
    assert float(data["total_marks_obtained"]) == 0.0
    assert data["tokens_used"] == 0
    assert all(a["status"] == "success" for a in data["answers"])


async def test_failed_answer_is_not_marked_evaluated_and_can_be_retried(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})

    def flaky(kwargs):
        if "Polymorphism" in kwargs["messages"][1]["content"]:
            return json.dumps({"score": 5, "feedback": "Correct."})
        return "this is not json"

    fake_llm.reply = flaky
    url = f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}"

    response = await client.post(url, headers=classroom.teacher["headers"])
    data = response.json()
    assert response.status_code == 200
    assert data["evaluated"] is False
    assert data["graded_count"] == 1
    assert data["failed_count"] == 1
    assert "could not be graded" in data["message"]
    by_qid = {a["qid"]: a for a in data["answers"]}
    assert by_qid[q1]["status"] == "success"
    assert by_qid[q2]["status"] == "failed"
    assert float(by_qid[q2]["marks_obtained"]) == 0.0
    assert float(data["total_marks_obtained"]) == 5.0

    # Second run: only the failed answer is sent to the LLM again.
    fake_llm.calls.clear()
    fake_llm.reply = json.dumps({"score": 7, "feedback": "Mostly right."})
    response = await client.post(url, headers=classroom.teacher["headers"])
    data = response.json()
    assert len(fake_llm.calls) == 1
    assert data["evaluated"] is True
    assert float(data["total_marks_obtained"]) == 12.0


async def test_force_regrades_answers_that_already_have_a_mark(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    url = f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}"

    await client.post(url, headers=classroom.teacher["headers"])
    fake_llm.calls.clear()

    # Without force nothing is sent again
    await client.post(url, headers=classroom.teacher["headers"])
    assert fake_llm.calls == []

    fake_llm.reply = json.dumps({"score": 2, "feedback": "Second opinion."})
    response = await client.post(
        url, params={"force": "true"}, headers=classroom.teacher["headers"]
    )
    assert len(fake_llm.calls) == 2
    assert float(response.json()["total_marks_obtained"]) == 4.0


async def test_rate_limit_stops_the_run_and_keeps_progress(client, classroom, fake_llm):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    fake_llm.reply = _rate_limit_error()

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}",
        headers=classroom.teacher["headers"],
    )

    data = response.json()
    assert response.status_code == 200
    assert data["evaluated"] is False
    assert data["pending_count"] == 2
    assert "rate limit" in data["message"].lower()
    # Nothing was marked as failed: the answers are simply still pending
    assert all(a["status"] == "pending" for a in data["answers"])


async def test_evaluation_requires_an_api_key(client, classroom, monkeypatch):
    from app.config import settings
    from app.utils.evaluator import EvaluationService

    q1, _ = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism"})
    monkeypatch.setattr(EvaluationService, "client", None)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}",
        headers=classroom.teacher["headers"],
    )

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


async def test_evaluation_is_refused_when_token_balance_is_spent(
    client, classroom, fake_llm
):
    from app.auth.model import UserUsage
    from app.database import AsyncSessionLocal

    q1, _ = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism"})
    async with AsyncSessionLocal() as session:
        usage = await session.get(UserUsage, classroom.teacher["email"])
        usage.llm_tokens_balance_monthly = 0
        await session.commit()

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}",
        headers=classroom.teacher["headers"],
    )

    assert response.status_code == 402
    assert fake_llm.calls == []


async def test_evaluate_whole_paper(client, classroom, fake_llm):
    q1, q2 = classroom.qids
    second = await register(client, "student")
    await client.post(
        "/api/auth/associations",
        params={"s_email": second["email"]},
        headers=classroom.teacher["headers"],
    )
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    await _submit(client, classroom, {q1: "Lyon", q2: ""}, student=second)
    fake_llm.reply = json.dumps({"score": 3, "feedback": "Fair."})

    response = await client.post(
        f"/api/evaluations/{classroom.qpid}", headers=classroom.teacher["headers"]
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["submission_count"] == 2
    assert data["evaluated_count"] == 2
    # 3 written answers go to the LLM; the blank one is graded locally
    assert len(fake_llm.calls) == 3
    assert data["graded_count"] == 4
    totals = {
        s["s_email"]: float(s["total_marks_obtained"]) for s in data["submissions"]
    }
    assert totals == {classroom.student["email"]: 6.0, second["email"]: 3.0}

    # The paper list now reports both submissions as evaluated
    papers = (
        await client.get("/api/papers/", headers=classroom.teacher["headers"])
    ).json()
    paper = next(p for p in papers if p["qpid"] == classroom.qpid)
    assert (paper["submission_count"], paper["evaluated_count"]) == (2, 2)

    # A second run has nothing left to do
    fake_llm.calls.clear()
    await client.post(
        f"/api/evaluations/{classroom.qpid}", headers=classroom.teacher["headers"]
    )
    assert fake_llm.calls == []

    await client.delete("/api/auth/", headers=second["headers"])


async def test_evaluate_paper_without_submissions(client, classroom, fake_llm):
    response = await client.post(
        f"/api/evaluations/{classroom.qpid}", headers=classroom.teacher["headers"]
    )
    assert response.status_code == 400
    assert "no submissions" in response.json()["detail"]


async def test_reset_evaluation(client, classroom, fake_llm):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    await client.post(
        f"/api/evaluations/{classroom.qpid}", headers=classroom.teacher["headers"]
    )

    response = await client.delete(
        f"/api/evaluations/{classroom.qpid}", headers=classroom.teacher["headers"]
    )
    assert response.status_code == 200

    detail = (
        await client.get(
            f"/api/submissions/{classroom.qpid}/{classroom.student['email']}",
            headers=classroom.teacher["headers"],
        )
    ).json()
    assert detail["evaluated"] is False
    assert float(detail["total_marks_obtained"]) == 0.0
    for answer in detail["answers"]:
        assert answer["status"] == "pending"
        assert answer["feedback"] is None
    # The student's text survives a reset
    assert detail["answers"][0]["student_answer"] == "Polymorphism"


async def test_teacher_can_override_a_mark(client, classroom, fake_llm):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    base = f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}"
    await client.post(base, headers=classroom.teacher["headers"])  # 1 + 1 marks

    response = await client.patch(
        f"{base}/{q2}",
        json={"marks_obtained": 9.5, "feedback": "Better than the AI thought."},
        headers=classroom.teacher["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()
    by_qid = {a["qid"]: a for a in data["answers"]}
    assert float(by_qid[q2]["marks_obtained"]) == 9.5
    assert by_qid[q2]["feedback"] == "Better than the AI thought."
    assert float(data["total_marks_obtained"]) == 10.5

    # More than the question is worth is rejected
    response = await client.patch(
        f"{base}/{q2}",
        json={"marks_obtained": 10.5},
        headers=classroom.teacher["headers"],
    )
    assert response.status_code == 400

    response = await client.patch(
        f"{base}/{q2}",
        json={"marks_obtained": -1},
        headers=classroom.teacher["headers"],
    )
    assert response.status_code == 422


async def test_teacher_can_grade_by_hand_without_the_llm(client, classroom):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    base = f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}"

    first = await client.patch(
        f"{base}/{q1}", json={"marks_obtained": 5}, headers=classroom.teacher["headers"]
    )
    assert first.json()["evaluated"] is False  # one answer is still pending

    second = await client.patch(
        f"{base}/{q2}", json={"marks_obtained": 6}, headers=classroom.teacher["headers"]
    )
    assert second.json()["evaluated"] is True
    assert float(second.json()["total_marks_obtained"]) == 11.0


async def test_only_the_owning_teacher_can_evaluate(client, classroom, fake_llm):
    q1, _ = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism"})
    other_teacher = await register(client, "teacher")
    base = f"/api/evaluations/{classroom.qpid}"
    student_url = f"{base}/{classroom.student['email']}"

    for headers in (other_teacher["headers"], classroom.student["headers"]):
        assert (await client.post(base, headers=headers)).status_code == 403
        assert (await client.post(student_url, headers=headers)).status_code == 403
        assert (await client.delete(base, headers=headers)).status_code == 403
        assert (await client.delete(student_url, headers=headers)).status_code == 403
        response = await client.patch(
            f"{student_url}/{q1}", json={"marks_obtained": 5}, headers=headers
        )
        assert response.status_code == 403
    assert fake_llm.calls == []

    await client.delete("/api/auth/", headers=other_teacher["headers"])


async def test_evaluate_unknown_submission(client, classroom, fake_llm):
    response = await client.post(
        f"/api/evaluations/{classroom.qpid}/nobody@example.com",
        headers=classroom.teacher["headers"],
    )
    assert response.status_code == 404


async def test_student_sees_marks_only_after_evaluation_is_complete(
    client, classroom, fake_llm
):
    q1, q2 = classroom.qids
    await _submit(client, classroom, {q1: "Polymorphism", q2: "Processes wait forever."})
    base = f"/api/evaluations/{classroom.qpid}/{classroom.student['email']}"
    own = f"/api/submissions/{classroom.qpid}/{classroom.student['email']}"

    # Half graded: the teacher set one mark by hand
    await client.patch(
        f"{base}/{q1}",
        json={"marks_obtained": 5, "feedback": "Right."},
        headers=classroom.teacher["headers"],
    )
    hidden = (await client.get(own, headers=classroom.student["headers"])).json()
    assert hidden["evaluated"] is False
    assert float(hidden["total_marks_obtained"]) == 0.0
    assert all(a["feedback"] is None for a in hidden["answers"])
    assert all(float(a["marks_obtained"]) == 0.0 for a in hidden["answers"])

    await client.post(base, headers=classroom.teacher["headers"])
    shown = (await client.get(own, headers=classroom.student["headers"])).json()
    assert shown["evaluated"] is True
    assert float(shown["total_marks_obtained"]) == 6.0
    assert shown["answers"][0]["feedback"] == "Right."

    papers = (
        await client.get("/api/papers/", headers=classroom.student["headers"])
    ).json()
    paper = next(p for p in papers if p["qpid"] == classroom.qpid)
    assert paper["attempted"] is True and paper["evaluated"] is True
    assert float(paper["marks_obtained"]) == 6.0
