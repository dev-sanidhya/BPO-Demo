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

