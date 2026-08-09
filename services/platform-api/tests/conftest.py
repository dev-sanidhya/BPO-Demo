import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PLATFORM_JWT_SECRET", "test-secret-not-for-production-123456")
    monkeypatch.setenv("PLATFORM_SEED_ADMIN_PASSWORD", "PilotTest123!")
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    import app.main
    importlib.reload(app.main)
    with TestClient(app.main.app) as test_client:
        yield test_client


@pytest.fixture()
def tokens(client: TestClient) -> dict[str, str]:
    result = {}
    for name, email in {
        "admin": "admin@pilot.example",
        "supervisor": "supervisor@pilot.example",
        "agent1": "agent1@pilot.example",
        "agent2": "agent2@pilot.example",
        "client": "client@pilot.example",
    }.items():
        response = client.post("/auth/login", json={"email": email, "password": "PilotTest123!"})
        assert response.status_code == 200
        result[name] = response.json()["access_token"]
    return result


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
