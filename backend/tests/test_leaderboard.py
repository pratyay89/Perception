"""Per-paper and overall class leaderboards."""

import pytest

from tests.conftest import paper_payload, register

pytestmark = pytest.mark.asyncio


async def _join_class(client, room, name: str) -> dict:
    student = await register(client, "student", name=name)
    response = await client.post(
        "/api/auth/associations",
        params={"s_email": student["email"]},
        headers=room.teacher["headers"],
    )
    assert response.status_code == 200, response.text
    return student


async def _submit(client, qpid: int, qids: list[int], student: dict) -> None:
    response = await client.post(
        f"/api/submissions/{qpid}",
        json={"answers": [{"qid": qid, "student_answer": "x"} for qid in qids]},
        headers=student["headers"],
    )
    assert response.status_code == 201, response.text


async def _grade(client, room, qpid: int, student: dict, marks: dict[int, float]):
    """The teacher marks every answer by hand, which evaluates the submission."""
    for qid, mark in marks.items():
        response = await client.patch(
            f"/api/evaluations/{qpid}/{student['email']}/{qid}",
            json={"marks_obtained": mark},
            headers=room.teacher["headers"],
        )
        assert response.status_code == 200, response.text


async def _paper_board(client, qpid: int, user: dict):
    return await client.get(f"/api/leaderboard/papers/{qpid}", headers=user["headers"])


async def test_paper_leaderboard_ranks_evaluated_submissions(client, classroom):
    q1, q2 = classroom.qids
    alice = classroom.student
    bob = await _join_class(client, classroom, "Bob")
    cara = await _join_class(client, classroom, "Cara")
    dev = await _join_class(client, classroom, "Dev")
    for student in (alice, bob, cara, dev):
        await _submit(client, classroom.qpid, classroom.qids, student)

    await _grade(client, classroom, classroom.qpid, alice, {q1: 4, q2: 8})  # 12
    await _grade(client, classroom, classroom.qpid, bob, {q1: 5, q2: 10})  # 15
    await _grade(client, classroom, classroom.qpid, cara, {q1: 2, q2: 10})  # 12
    # Dev's submission is not evaluated, so Dev is not ranked yet

    response = await _paper_board(client, classroom.qpid, classroom.teacher)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "CS Fundamentals Quiz"
    assert data["pending_count"] == 1
    entries = data["entries"]
    assert [e["full_name"] for e in entries] == ["Bob", "Cara", "Test Student"]
    # Equal marks share a rank
    assert [e["rank"] for e in entries] == [1, 2, 2]
    assert [float(e["marks_obtained"]) for e in entries] == [15, 12, 12]
    assert [e["percentage"] for e in entries] == [100.0, 80.0, 80.0]
    # The teacher sees every email
    assert all(e["s_email"] for e in entries)
    assert not any(e["is_you"] for e in entries)


async def test_students_see_names_but_only_their_own_email(client, classroom):
    q1, q2 = classroom.qids
    bob = await _join_class(client, classroom, "Bob")
    for student in (classroom.student, bob):
        await _submit(client, classroom.qpid, classroom.qids, student)
        await _grade(client, classroom, classroom.qpid, student, {q1: 1, q2: 1})

    response = await _paper_board(client, classroom.qpid, bob)

    assert response.status_code == 200, response.text
    by_name = {e["full_name"]: e for e in response.json()["entries"]}
    assert by_name["Bob"]["is_you"] is True
    assert by_name["Bob"]["s_email"] == bob["email"]
    assert by_name["Test Student"]["is_you"] is False
    assert by_name["Test Student"]["s_email"] is None


async def test_paper_leaderboard_access(client, classroom):
    outsider = await register(client, "student")
    other_teacher = await register(client, "teacher")

    assert (await _paper_board(client, classroom.qpid, outsider)).status_code == 403
    assert (
        await _paper_board(client, classroom.qpid, other_teacher)
    ).status_code == 403
    assert (await _paper_board(client, 999_999, classroom.teacher)).status_code == 404

    # A class member cannot see the leaderboard of a draft
    response = await client.post(
        "/api/papers/",
        json=paper_payload(title="Draft", is_published=False),
        headers=classroom.teacher["headers"],
    )
    draft = response.json()["qpid"]
    assert (await _paper_board(client, draft, classroom.student)).status_code == 403
    assert (await _paper_board(client, draft, classroom.teacher)).status_code == 200

    # Unauthenticated
    response = await client.get(f"/api/leaderboard/papers/{classroom.qpid}")
    assert response.status_code == 401


async def test_class_leaderboard_ranks_by_overall_percentage(client, classroom):
    q1, q2 = classroom.qids
    alice = classroom.student
    bob = await _join_class(client, classroom, "Bob")
    await _join_class(client, classroom, "Idle")  # never evaluated: not listed

    response = await client.post(
        "/api/papers/",
        json=paper_payload(title="Second Quiz"),
        headers=classroom.teacher["headers"],
    )
    second = response.json()
    s1, s2 = [q["qid"] for q in second["questions"]]

    # Alice: 15/15 and 3/15 -> 18/30 = 60%
    await _submit(client, classroom.qpid, classroom.qids, alice)
    await _grade(client, classroom, classroom.qpid, alice, {q1: 5, q2: 10})
    await _submit(client, second["qpid"], [s1, s2], alice)
    await _grade(client, classroom, second["qpid"], alice, {s1: 1, s2: 2})
    # Bob: 12/15 on the only paper evaluated -> 80%
    await _submit(client, classroom.qpid, classroom.qids, bob)
    await _grade(client, classroom, classroom.qpid, bob, {q1: 2, q2: 10})

    response = await client.get(
        "/api/leaderboard", headers=classroom.teacher["headers"]
    )

    assert response.status_code == 200, response.text
    boards = response.json()
    assert len(boards) == 1
    board = boards[0]
    assert board["t_email"] == classroom.teacher["email"]
    assert board["papers_count"] == 2
    entries = board["entries"]
    assert [e["full_name"] for e in entries] == ["Bob", "Test Student"]
    assert [e["rank"] for e in entries] == [1, 2]
    assert [e["percentage"] for e in entries] == [80.0, 60.0]
    assert [e["papers_evaluated"] for e in entries] == [1, 2]
    assert [float(e["marks_obtained"]) for e in entries] == [12, 18]
    assert [float(e["total_marks"]) for e in entries] == [15, 30]

    # The student gets the same table, with other emails hidden
    response = await client.get("/api/leaderboard", headers=alice["headers"])
    entries = response.json()[0]["entries"]
    assert [(e["full_name"], e["is_you"]) for e in entries] == [
        ("Bob", False),
        ("Test Student", True),
    ]
    assert entries[0]["s_email"] is None
    assert entries[1]["s_email"] == alice["email"]


async def test_class_leaderboard_for_students_without_a_class(client):
    loner = await register(client, "student")
    response = await client.get("/api/leaderboard", headers=loner["headers"])
    assert response.status_code == 200
    assert response.json() == []


async def test_class_leaderboard_of_a_teacher_without_papers(client):
    teacher = await register(client, "teacher", name="New Teacher")
    response = await client.get("/api/leaderboard", headers=teacher["headers"])
    assert response.status_code == 200
    assert response.json() == [
        {
            "t_email": teacher["email"],
            "teacher_name": "New Teacher",
            "papers_count": 0,
            "entries": [],
        }
    ]
