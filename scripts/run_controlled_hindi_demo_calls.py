"""Ingest controlled synthetic Hindi demo recordings through the normal AI pipeline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import requests


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "artifacts" / "controlled-hindi-demo-calls"
API_URL = os.environ.get("PLATFORM_API_URL", "http://127.0.0.1:18080")
PASSWORD = os.environ.get("DEMO_AGENT_PASSWORD", "PilotTest123!")


def login(email: str) -> str:
    response = requests.post(f"{API_URL}/auth/login", json={"email": email, "password": PASSWORD}, timeout=15)
    response.raise_for_status()
    return response.json()["access_token"]


def request(token: str, method: str, path: str, **kwargs):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=90, **kwargs)
    response.raise_for_status()
    return response


def upload(token: str, path: str, audio_path: Path, data: dict[str, str | int]) -> dict:
    with audio_path.open("rb") as audio:
        response = request(token, "POST" if path.endswith("audio-chunks") else "PUT", path, files={"file": (audio_path.name, audio, "audio/wav")}, data=data)
    return response.json()


def ingest(scenario: str, token: str) -> str:
    scenario_dir = ASSETS / scenario
    manifest = json.loads((scenario_dir / "manifest.json").read_text(encoding="utf-8"))
    label = f"Controlled Hindi demo — {scenario.replace('-', ' ')}"
    response = request(token, "POST", "/voice/calls/dial", json={"phone": f"demo-{scenario}", "customer_name": label, "language": manifest["language"]}).json()
    conversation_id = response["conversation"]["id"]
    upload(token, f"/voice/calls/{conversation_id}/recording", scenario_dir / "demo-call.wav", {"duration_ms": manifest["duration_ms"]})
    for segment in manifest["segments"]:
        upload(
            token,
            f"/voice/calls/{conversation_id}/audio-chunks",
            scenario_dir / segment["file"],
            {"speaker": segment["speaker"], "start_ms": segment["start_ms"]},
        )
    request(token, "POST", f"/voice/calls/{conversation_id}/control", json={"action": "hangup"})
    print(f"{scenario}: {conversation_id}")
    return conversation_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=int, default=45, help="Time to allow the durable QA worker to complete after ingestion.")
    parser.add_argument("--agent", default="agent1@pilot.example", help="Seeded agent identity to use for this sequential batch.")
    parser.add_argument("scenarios", nargs="*", default=["good-resolution", "coaching-needed"], help="Scenario folder names to ingest in sequence.")
    args = parser.parse_args()
    if not ASSETS.is_dir():
        raise SystemExit("Audio assets are missing. Run scripts/generate_controlled_hindi_demo_calls.py first.")
    token = login(args.agent)
    ids = [ingest(name, token) for name in args.scenarios]
    print(f"Waiting {args.wait_seconds}s for durable Groq QA...")
    time.sleep(args.wait_seconds)
    print("Ready to inspect in Supervisor > Conversations and Quality:")
    print("\n".join(ids))


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as error:
        detail = error.response.text if error.response is not None else str(error)
        print(f"Controlled demo ingestion failed: {detail}", file=sys.stderr)
        raise SystemExit(1) from error
