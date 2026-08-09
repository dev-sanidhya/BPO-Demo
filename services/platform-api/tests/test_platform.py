from fastapi.testclient import TestClient
import asyncio

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


def test_web_chat_routes_through_unified_conversation_and_isolates_agents(client: TestClient, tokens: dict[str, str]) -> None:
    started = client.post("/public/chat/start", json={"tenant_slug": "aperture-pilot", "widget_key": "pilot-widget-key-change-me", "customer_name": "Riya Customer", "language": "hi-en", "initial_message": "Namaste, mujhe order update chahiye."})
    assert started.status_code == 201
    conversation_id = started.json()["conversation_id"]
    chat_headers = {"X-Chat-Session": started.json()["session_token"]}

    agent1 = client.get("/me", headers=auth(tokens["agent1"])).json()
    claimed = client.post(f"/conversations/{conversation_id}/claim", headers=auth(tokens["agent1"]))
    assert claimed.status_code == 200
    assert claimed.json()["assigned_user_id"] == agent1["id"]
    assert client.get("/conversations", headers=auth(tokens["agent2"])).json() == []

    reply = client.post(f"/conversations/{conversation_id}/messages", headers=auth(tokens["agent1"]), json={"content": "Namaste Riya, main status check kar raha hoon."})
    assert reply.status_code == 201
    customer_reply = client.post(f"/public/chat/{conversation_id}/messages", headers=chat_headers, json={"content": "Theek hai, thank you."})
    assert customer_reply.status_code == 201
    timeline = client.get(f"/public/chat/{conversation_id}/messages", headers=chat_headers)
    assert [message["sender_type"] for message in timeline.json()] == ["customer", "agent", "customer"]


def test_realtime_events_use_header_subprotocol_and_authorized_audience(client: TestClient, tokens: dict[str, str]) -> None:
    with client.websocket_connect("/realtime", subprotocols=["bpo-realtime", tokens["supervisor"]]) as supervisor_ws:
        started = client.post("/public/chat/start", json={"tenant_slug": "aperture-pilot", "widget_key": "pilot-widget-key-change-me", "customer_name": "Live Customer", "initial_message": "I need help."})
        event = supervisor_ws.receive_json()
        assert event == {"type": "conversation.queued", "conversation_id": started.json()["conversation_id"], "channel": "web_chat"}


def test_realtime_hub_never_broadcasts_assigned_event_to_other_agent() -> None:
    from app.models import Role, User
    from app.realtime import RealtimeHub

    class FakeSocket:
        def __init__(self) -> None:
            self.events: list[dict] = []

        async def send_json(self, event: dict) -> None:
            self.events.append(event)

    async def scenario() -> tuple[list[dict], list[dict], list[dict]]:
        hub = RealtimeHub()
        agent1 = User(id="agent-1", tenant_id="tenant-1", email="a1@example.com", display_name="A1", password_hash="x", role=Role.AGENT)
        agent2 = User(id="agent-2", tenant_id="tenant-1", email="a2@example.com", display_name="A2", password_hash="x", role=Role.AGENT)
        supervisor = User(id="supervisor-1", tenant_id="tenant-1", email="s@example.com", display_name="S", password_hash="x", role=Role.SUPERVISOR)
        socket1, socket2, supervisor_socket = FakeSocket(), FakeSocket(), FakeSocket()
        await hub.connect(agent1, socket1)
        await hub.connect(agent2, socket2)
        await hub.connect(supervisor, supervisor_socket)
        await hub.publish("tenant-1", {"type": "assist.prompt", "conversation_id": "call-1"}, assigned_user_id="agent-1")
        return socket1.events, socket2.events, supervisor_socket.events

    agent1_events, agent2_events, supervisor_events = asyncio.run(scenario())
    assert len(agent1_events) == 1
    assert agent2_events == []
    assert len(supervisor_events) == 1
