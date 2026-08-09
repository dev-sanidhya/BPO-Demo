from fastapi.testclient import TestClient

from .conftest import auth


def test_login_and_me(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.get("/me", headers=auth(tokens["agent1"]))
    assert response.status_code == 200
    assert response.json()["role"] == "agent"


def test_agent_cannot_create_conversation(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.post("/conversations", headers=auth(tokens["agent1"]), json={"channel": "voice", "direction": "outbound"})
    assert response.status_code == 403


def test_assignment_is_tenant_scoped_and_agent_lists_only_own_work(client: TestClient, tokens: dict[str, str]) -> None:
    created = client.post("/conversations", headers=auth(tokens["supervisor"]), json={"channel": "web_chat", "direction": "inbound"})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    agent = client.get("/me", headers=auth(tokens["agent1"])).json()
    assigned = client.post(f"/conversations/{conversation_id}/assign", headers=auth(tokens["supervisor"]), json={"user_id": agent["id"]})
    assert assigned.status_code == 200
    own = client.get("/conversations", headers=auth(tokens["agent1"]))
    other = client.get("/conversations", headers=auth(tokens["agent2"]))
    assert [row["id"] for row in own.json()] == [conversation_id]
    assert other.json() == []


def test_agent_presence_is_auditable(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.put("/agents/me/presence", headers=auth(tokens["agent1"]), json={"status": "available"})
    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_client_viewer_cannot_assign_work(client: TestClient, tokens: dict[str, str]) -> None:
    response = client.post("/conversations/missing/assign", headers=auth(tokens["client"]), json={"user_id": "missing"})
    assert response.status_code == 403


def test_qa_evidence_and_review_preserve_automatic_score(client: TestClient, tokens: dict[str, str]) -> None:
    form_response = client.post(
        "/qa/forms",
        headers=auth(tokens["admin"]),
        json={"name": "Pilot Compliance", "questions": [{"label": "Required disclosure delivered", "weight": 100, "fatal": True}]},
    )
    assert form_response.status_code == 201
    form_id = form_response.json()["id"]
    created = client.post("/conversations", headers=auth(tokens["supervisor"]), json={"channel": "voice", "direction": "inbound"})
    conversation_id = created.json()["id"]

    from app.database import SessionLocal
    from app.models import QAQuestion
    from sqlalchemy import select
    with SessionLocal() as db:
        question_id = db.scalar(select(QAQuestion.id).where(QAQuestion.form_id == form_id))

    evaluation = client.post(
        f"/conversations/{conversation_id}/qa/evaluations",
        headers=auth(tokens["supervisor"]),
        json={
            "form_id": form_id,
            "automatic_score": 40,
            "fatal_triggered": True,
            "provider": "local",
            "model": "deterministic-fixture",
            "summary": "Disclosure was incomplete.",
            "answers": [{"question_id": question_id, "passed": False, "score": 40, "confidence": 92, "evidence_quote": "I can skip the disclosure.", "evidence_start_ms": 1200, "evidence_end_ms": 2600, "reasoning": "Required language is absent."}],
        },
    )
    assert evaluation.status_code == 201
    reviewed = client.post(
        f"/qa/evaluations/{evaluation.json()['id']}/reviews",
        headers=auth(tokens["supervisor"]),
        json={"reviewed_score": 55, "reason": "The abbreviated disclosure is acceptable for this pilot."},
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["automatic_score"] == 40
    assert reviewed.json()["reviewed_score"] == 55
