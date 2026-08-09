from fastapi.testclient import TestClient
import asyncio
import io
import socket
import wave
import pytest

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


def test_agent_queue_claim_and_wrap_up_flow(client: TestClient, tokens: dict[str, str]) -> None:
    started = client.post("/public/chat/start", json={"tenant_slug": "aperture-pilot", "widget_key": "pilot-widget-key-change-me", "customer_name": "Queue Customer", "initial_message": "Please help."})
    conversation_id = started.json()["conversation_id"]
    queued = client.get("/work/queued", headers=auth(tokens["agent1"]))
    assert conversation_id in [row["id"] for row in queued.json()]
    assert client.post(f"/conversations/{conversation_id}/claim", headers=auth(tokens["agent1"])).status_code == 200
    wrapped = client.post(f"/conversations/{conversation_id}/wrap-up", headers=auth(tokens["agent1"]), json={"disposition": "resolved", "summary": "Customer question answered."})
    assert wrapped.status_code == 200
    assert wrapped.json()["status"] == "closed"
    assert wrapped.json()["disposition"] == "resolved"


def test_closed_chat_collects_actual_csat_separately_from_predictions(client: TestClient, tokens: dict[str, str]) -> None:
    started = client.post("/public/chat/start", json={"tenant_slug": "aperture-pilot", "widget_key": "pilot-widget-key-change-me", "customer_name": "Survey Customer", "initial_message": "Please confirm my delivery."})
    conversation_id = started.json()["conversation_id"]
    chat_headers = {"X-Chat-Session": started.json()["session_token"]}
    assert client.post(f"/conversations/{conversation_id}/claim", headers=auth(tokens["agent1"])).status_code == 200
    assert client.post(f"/conversations/{conversation_id}/wrap-up", headers=auth(tokens["agent1"]), json={"disposition": "resolved", "summary": "Delivery confirmed."}).status_code == 200

    status_response = client.get(f"/public/chat/{conversation_id}/status", headers=chat_headers)
    assert status_response.json() == {"status": "closed", "actual_csat": None}
    survey = client.post(f"/public/chat/{conversation_id}/survey", headers=chat_headers, json={"csat": 5})
    assert survey.status_code == 201
    assert survey.json() == {"actual_csat": 5, "source": "customer_widget"}

    report = client.get("/reports/summary?channel=web_chat", headers=auth(tokens["client"])).json()
    assert report["actual_csat_count"] == 1
    assert report["average_actual_csat"] == 5
    assert report["predicted_risk_count"] == 0


def test_local_voice_controls_recording_transcript_qa_and_exports(client: TestClient, tokens: dict[str, str]) -> None:
    dialed = client.post("/voice/calls/dial", headers=auth(tokens["agent1"]), json={"phone": "+919999999999", "customer_name": "Voice Customer", "language": "en"})
    assert dialed.status_code == 201
    conversation_id = dialed.json()["conversation"]["id"]
    for action, expected in [("mute", {"muted": True}), ("hold", {"held": True, "state": "held"}), ("resume", {"held": False, "state": "active"}), ("unmute", {"muted": False})]:
        controlled = client.post(f"/voice/calls/{conversation_id}/control", headers=auth(tokens["agent1"]), json={"action": action})
        assert controlled.status_code == 200
        for key, value in expected.items():
            assert controlled.json()[key] == value
    transferred = client.post(f"/voice/calls/{conversation_id}/control", headers=auth(tokens["agent1"]), json={"action": "transfer", "target": "supervisor-desk"})
    assert transferred.json()["transfer_target"] == "supervisor-desk"
    ended = client.post(f"/voice/calls/{conversation_id}/control", headers=auth(tokens["agent1"]), json={"action": "hangup"})
    assert ended.json()["state"] == "ended"
    diagnostics = client.get("/diagnostics", headers=auth(tokens["supervisor"])).json()
    assert diagnostics["jobs"]["succeeded"] >= 1
    transcript = client.get(f"/conversations/{conversation_id}/transcript", headers=auth(tokens["agent1"]))
    assert transcript.status_code == 200
    assert {segment["speaker"] for segment in transcript.json()} == {"agent", "customer"}
    assert any("sorry about the delay" in segment["text"] for segment in transcript.json())
    recording = client.get(f"/conversations/{conversation_id}/recording", headers=auth(tokens["agent1"]))
    assert recording.status_code == 200
    assert recording.content[:4] == b"RIFF"
    evaluations = client.get("/qa/evaluations", headers=auth(tokens["supervisor"])).json()
    evaluation = next(item for item in evaluations if item["conversation_id"] == conversation_id)
    detail = client.get(f"/qa/evaluations/{evaluation['id']}", headers=auth(tokens["supervisor"]))
    assert detail.status_code == 200
    assert detail.json()["answers"]
    assert all(answer["evidence_end_ms"] > answer["evidence_start_ms"] for answer in detail.json()["answers"])
    wrapped = client.post(f"/conversations/{conversation_id}/wrap-up", headers=auth(tokens["agent1"]), json={"disposition": "resolved", "summary": "Order delivery confirmed."})
    assert wrapped.json()["status"] == "closed"
    assert client.get("/reports/export.csv", headers=auth(tokens["client"])).text.startswith("conversation_id,channel")
    assert client.get("/reports/export.pdf", headers=auth(tokens["client"])).content.startswith(b"%PDF-1.4")
    voice_summary = client.get("/reports/summary?channel=voice", headers=auth(tokens["client"])).json()
    chat_summary = client.get("/reports/summary?channel=web_chat", headers=auth(tokens["client"])).json()
    assert voice_summary["conversation_count"] == 1
    assert chat_summary["conversation_count"] == 0
    costs = client.get("/reports/costs", headers=auth(tokens["client"]))
    assert {item["category"] for item in costs.json()["items"]} == {"telephony", "transcription", "inference", "storage"}


def test_inbound_voice_can_be_rejected_or_accepted_from_the_shared_queue(client: TestClient, tokens: dict[str, str]) -> None:
    first = client.post("/voice/calls/simulate-inbound", headers=auth(tokens["supervisor"]), json={"phone": "+919111111111", "customer_name": "Inbound One", "language": "en"})
    first_id = first.json()["conversation"]["id"]
    assert client.post(f"/voice/calls/{first_id}/reject", headers=auth(tokens["agent1"])).json()["state"] == "rejected"
    second = client.post("/voice/calls/simulate-inbound", headers=auth(tokens["supervisor"]), json={"phone": "+919222222222", "customer_name": "Inbound Two", "language": "en"})
    second_id = second.json()["conversation"]["id"]
    queued = client.get("/work/queued", headers=auth(tokens["agent1"])).json()
    assert second_id in [item["id"] for item in queued]
    assert client.post(f"/conversations/{second_id}/claim", headers=auth(tokens["agent1"])).status_code == 200
    assert client.get(f"/voice/calls/{second_id}", headers=auth(tokens["agent1"])).json()["session"]["state"] == "active"


def test_strict_local_voice_finalization_attempts_no_network_egress(client: TestClient, tokens: dict[str, str], monkeypatch) -> None:
    def reject_connect(*_args, **_kwargs):
        raise AssertionError("strict-local processing attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", reject_connect)
    dialed = client.post("/voice/calls/dial", headers=auth(tokens["agent1"]), json={"phone": "+919333333333", "customer_name": "Local Privacy", "language": "en"})
    assert dialed.status_code == 201
    conversation_id = dialed.json()["conversation"]["id"]
    ended = client.post(f"/voice/calls/{conversation_id}/control", headers=auth(tokens["agent1"]), json={"action": "hangup"})
    if ended.status_code != 200:
        from app.models import DurableJob
        with SessionLocal() as db:
            failure = db.query(DurableJob).order_by(DurableJob.created_at.desc()).first()
            pytest.fail(f"{ended.text}; durable failure: {failure.last_error if failure else 'missing job'}")
    diagnostics = client.get("/diagnostics", headers=auth(tokens["supervisor"])).json()
    assert diagnostics["privacy"]["mode"] == "local"
    assert diagnostics["privacy"]["customer_content_egress"] is False
    assert diagnostics["privacy"]["provider"] == "local_rules"
    assert diagnostics["privacy"]["data_retention"] == "deployment-local"


def test_external_voice_uses_provider_output_and_preserves_actual_csat_boundary(client: TestClient, tokens: dict[str, str], monkeypatch) -> None:
    from app.ai import Analysis, Transcription, Usage
    from app.database import SessionLocal
    from app.models import Tenant
    from app.config import get_settings
    import app.external_voice as external_voice

    class FakeGroq:
        def __init__(self, _settings):
            pass

        def transcribe(self, _audio_path, model, language):
            assert model == "whisper-large-v3"
            assert language == "hi-en"
            return Transcription(
                text="Mera order late hai. Delivery kal scheduled hai.",
                language="Hindi",
                duration_seconds=20,
                request_id="asr-test",
                words=[],
                segments=[
                    {"text": "Mera order late hai.", "start_ms": 0, "end_ms": 5000, "avg_logprob": -0.1, "no_speech_prob": 0},
                    {"text": "Delivery kal scheduled hai.", "start_ms": 6000, "end_ms": 11000, "avg_logprob": -0.1, "no_speech_prob": 0},
                ],
            )

        def analyze(self, transcript, questions, script, knowledge, language, live=False):
            assert transcript and questions and script and knowledge
            assert language == "hi-en"
            assert live is False
            return Analysis(
                payload={
                    "detected_language": "hi-en",
                    "summary": "Customer asked about a delayed order and was given tomorrow's delivery commitment.",
                    "predicted_dissatisfaction_risk": 24,
                    "assists": [{"event_type": "next_best_action", "title": "Confirm in writing", "content": "Send the promised delivery update.", "evidence_segment_index": 1}],
                    "qa_answers": [{"question_id": item["id"], "passed": True, "score": 90, "confidence": 88, "evidence_segment_index": min(index, 1), "reasoning": "Supported by the transcript."} for index, item in enumerate(questions)],
                },
                usage=Usage(500, 200),
                request_id="llm-test",
            )

    monkeypatch.setattr(get_settings(), "groq_api_key", "fake-test-key")
    monkeypatch.setattr(external_voice, "GroqAI", FakeGroq)
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.slug == "aperture-pilot").one()
        tenant.ai_mode = "external"
        db.commit()

    dialed = client.post("/voice/calls/dial", headers=auth(tokens["agent1"]), json={"phone": "1003", "customer_name": "Hinglish Customer", "language": "hi-en"})
    assert dialed.status_code == 201
    assert dialed.json()["session"]["provider"] == "groq_external"
    conversation_id = dialed.json()["conversation"]["id"]
    fixture = io.BytesIO()
    with wave.open(fixture, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000)
    uploaded = client.put(f"/voice/calls/{conversation_id}/recording", headers=auth(tokens["agent1"]), files={"file": ("call.wav", fixture.getvalue(), "audio/wav")})
    assert uploaded.status_code == 200, uploaded.text
    ended = client.post(f"/voice/calls/{conversation_id}/control", headers=auth(tokens["agent1"]), json={"action": "hangup"})
    if ended.status_code != 200:
        from app.models import DurableJob
        with SessionLocal() as db:
            failure = db.query(DurableJob).order_by(DurableJob.created_at.desc()).first()
            pytest.fail(f"{ended.text}; durable failure: {failure.last_error if failure else 'missing job'}")
    transcript = client.get(f"/conversations/{conversation_id}/transcript", headers=auth(tokens["agent1"])).json()
    assert [item["text"] for item in transcript] == ["Mera order late hai.", "Delivery kal scheduled hai."]
    evaluations = client.get("/qa/evaluations", headers=auth(tokens["supervisor"])).json()
    evaluation = next(item for item in evaluations if item["conversation_id"] == conversation_id)
    assert evaluation["provider"] == "groq"
    report = client.get("/reports/summary?channel=voice", headers=auth(tokens["client"])).json()
    assert report["actual_csat_count"] == 0
    assert report["predicted_risk_count"] == 1


def test_admin_can_configure_the_pilot_and_create_an_agent(client: TestClient, tokens: dict[str, str]) -> None:
    updated = client.put("/configuration/pilot", headers=auth(tokens["admin"]), json={"campaign_name": "Retail Care", "queue_name": "Retail Priority", "script_content": "Greet, verify the order, acknowledge the concern, resolve it, and recap every next step clearly.", "required_steps": ["Verify order", "Recap resolution"], "knowledge_title": "Retail delivery policy", "knowledge_content": "Confirm the revised delivery date and send written confirmation to the customer before wrap-up.", "qa_form_name": "Retail Care QA"})
    assert updated.status_code == 200
    created = client.post("/users", headers=auth(tokens["admin"]), json={"email": "new.agent@pilot.example", "display_name": "New Pilot Agent", "role": "agent", "password": "NewPilot123!"})
    assert created.status_code == 201
    configured = client.get("/configuration", headers=auth(tokens["admin"])).json()
    assert configured["campaigns"][0]["name"] == "Retail Care"
    assert configured["queues"][0]["name"] == "Retail Priority"
    assert any(item["email"] == "new.agent@pilot.example" for item in configured["users"])
    login = client.post("/auth/login", json={"email": "new.agent@pilot.example", "password": "NewPilot123!"})
    assert login.status_code == 200
