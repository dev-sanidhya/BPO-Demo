"""
One-shot Metabase provisioning: creates the admin account + Postgres
connection on first run, then creates (or reuses) the four starter
questions and dashboard described in dashboard_export.json.

Idempotent by name: re-running this after the stack already has an admin
account logs in with the same credentials rather than re-running setup, and
skips creating any question/dashboard that already exists by name. Safe to
run on every `docker compose up`.

Written against the documented Metabase REST API (see
https://www.metabase.com/docs/latest/api-documentation). Metabase's card/
dashboard endpoint shapes have shifted across versions before (notably the
dashcards endpoint) — this has not been exercised against a live Metabase
instance in this environment; verify against the exact Metabase version
you deploy. See README "What's been verified vs. what needs a live check."
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s metabase-provision %(message)s")
log = logging.getLogger("provision")

METABASE_URL = os.environ.get("METABASE_SITE_URL", "http://metabase:3000").rstrip("/")
ADMIN_EMAIL = os.environ.get("METABASE_ADMIN_EMAIL", "admin@bpo-pilot.local")
ADMIN_PASSWORD = os.environ.get("METABASE_ADMIN_PASSWORD", "ChangeMe123!Pilot")

PG_HOST = os.environ["POSTGRES_HOST"]
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]
PG_DB = os.environ["POSTGRES_DB"]

CONFIG_PATH = Path(__file__).parent / "dashboard_export.json"


def wait_for_metabase() -> None:
    log.info("waiting for Metabase at %s ...", METABASE_URL)
    for i in range(60):
        try:
            resp = requests.get(f"{METABASE_URL}/api/health", timeout=5)
            if resp.status_code == 200:
                log.info("Metabase is up.")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    log.error("Metabase never became healthy, aborting provisioning.")
    sys.exit(1)


def get_or_create_session(config: dict) -> str:
    """Returns a session token, running first-time setup if needed."""
    props = requests.get(f"{METABASE_URL}/api/session/properties", timeout=10).json()
    needs_setup = bool(props.get("setup-token"))

    if needs_setup:
        log.info("no admin account yet, running first-time setup")
        resp = requests.post(
            f"{METABASE_URL}/api/setup",
            json={
                "token": props["setup-token"],
                "user": {
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                    "first_name": "Pilot",
                    "last_name": "Admin",
                    "site_name": config["site_name"],
                },
                "prefs": {"site_name": config["site_name"], "allow_tracking": False},
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    log.info("admin account already exists, logging in")
    resp = requests.post(
        f"{METABASE_URL}/api/session",
        json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_or_create_database(session_token: str, config: dict) -> int:
    headers = {"X-Metabase-Session": session_token}
    dbs = requests.get(f"{METABASE_URL}/api/database", headers=headers, timeout=15).json()
    existing = [d for d in dbs.get("data", dbs if isinstance(dbs, list) else [])
                if d.get("name") == config["database_name"]]
    if existing:
        log.info("database '%s' already connected (id=%s)", config["database_name"], existing[0]["id"])
        return existing[0]["id"]

    log.info("connecting Postgres database '%s'", config["database_name"])
    resp = requests.post(
        f"{METABASE_URL}/api/database",
        headers=headers,
        json={
            "engine": "postgres",
            "name": config["database_name"],
            "details": {
                "host": PG_HOST,
                "port": int(PG_PORT),
                "dbname": PG_DB,
                "user": PG_USER,
                "password": PG_PASSWORD,
                "ssl": False,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_or_create_question(session_token: str, db_id: int, question: dict) -> int:
    headers = {"X-Metabase-Session": session_token}
    cards = requests.get(f"{METABASE_URL}/api/card", headers=headers, timeout=15).json()
    existing = [c for c in cards if c.get("name") == question["name"]]
    if existing:
        log.info("question '%s' already exists (id=%s)", question["name"], existing[0]["id"])
        return existing[0]["id"]

    log.info("creating question '%s'", question["name"])
    resp = requests.post(
        f"{METABASE_URL}/api/card",
        headers=headers,
        json={
            "name": question["name"],
            "display": question.get("display", "table"),
            "visualization_settings": {},
            "dataset_query": {
                "type": "native",
                "native": {"query": question["sql"]},
                "database": db_id,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_or_create_dashboard(session_token: str, name: str) -> int:
    headers = {"X-Metabase-Session": session_token}
    dashboards = requests.get(f"{METABASE_URL}/api/dashboard", headers=headers, timeout=15).json()
    existing = [d for d in dashboards if d.get("name") == name]
    if existing:
        log.info("dashboard '%s' already exists (id=%s)", name, existing[0]["id"])
        return existing[0]["id"]

    log.info("creating dashboard '%s'", name)
    resp = requests.post(
        f"{METABASE_URL}/api/dashboard",
        headers=headers,
        json={"name": name},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def add_cards_to_dashboard(session_token: str, dashboard_id: int, card_ids: list[int]) -> None:
    headers = {"X-Metabase-Session": session_token}
    dashcards = []
    for i, card_id in enumerate(card_ids):
        dashcards.append({
            "id": -(i + 1),  # negative temp ids signal "new card" to this endpoint
            "card_id": card_id,
            "row": (i // 2) * 4,
            "col": (i % 2) * 12,
            "size_x": 12,
            "size_y": 4,
        })
    resp = requests.put(
        f"{METABASE_URL}/api/dashboard/{dashboard_id}/cards",
        headers=headers,
        json={"cards": dashcards},
        timeout=30,
    )
    if resp.status_code >= 400:
        log.warning(
            "adding cards to dashboard failed (status %s) — this endpoint's shape can "
            "differ across Metabase versions, add the questions to the dashboard by "
            "hand in the UI if this happens: %s",
            resp.status_code, resp.text[:500],
        )
        return
    log.info("added %d cards to dashboard %s", len(card_ids), dashboard_id)


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text())

    wait_for_metabase()
    session_token = get_or_create_session(config)
    db_id = get_or_create_database(session_token, config)

    card_ids = [
        get_or_create_question(session_token, db_id, q)
        for q in config["questions"]
    ]

    dashboard_id = get_or_create_dashboard(session_token, config["dashboard_name"])
    add_cards_to_dashboard(session_token, dashboard_id, card_ids)

    log.info("provisioning complete: %s/dashboard/%s", METABASE_URL, dashboard_id)
    log.info("login with %s / (METABASE_ADMIN_PASSWORD from your .env)", ADMIN_EMAIL)


if __name__ == "__main__":
    main()
