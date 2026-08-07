#!/usr/bin/env python3
"""
Originate a test call that plays a REAL customer service call recording
(asterisk/test-audio/real-call-sample.wav — see that folder's README for
provenance) instead of Asterisk's own generic demo audio. Same no-trunk,
no-softphone, self-contained mechanism as make_test_call.py, but with
actual call-center dialogue content — proves transcription, QA scoring,
and the coaching-nudge decision against genuine speech, not just
"Congratulations, you installed Asterisk."
"""
import argparse
import os
import sys
import time

import requests

ARI_URL = os.environ.get("ARI_URL", "http://localhost:8088/ari")
ARI_USER = os.environ.get("ARI_USER", "asterisk")
ARI_PASSWORD = os.environ.get("ARI_PASSWORD", "changeme_ari_password")


def originate_real_call_test(hold_seconds: float) -> str:
    auth = (ARI_USER, ARI_PASSWORD)

    resp = requests.post(
        f"{ARI_URL}/channels",
        auth=auth,
        params={
            "endpoint": "Local/realcalltest@internal",
            "extension": "realcalltest",
            "context": "internal",
        },
        timeout=10,
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("message", resp.text)
        except ValueError:
            detail = resp.text
        raise requests.HTTPError(f"{resp.status_code} from Asterisk ARI: {detail}", response=resp)
    channel = resp.json()
    channel_id = channel["id"]
    print(f"Originated real-call test. Asterisk channel id: {channel_id}")

    print(f"Holding the call open for {hold_seconds:.0f}s while the real call "
          f"recording plays — realtime-assist should produce several chunks "
          f"of genuine transcript during this window...")
    time.sleep(hold_seconds)

    try:
        requests.delete(f"{ARI_URL}/channels/{channel_id}", auth=auth, timeout=10)
    except requests.RequestException:
        pass  # likely already hung up on its own if the recording finished first

    return channel_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=60.0,
        help="How long to keep the call open (default: 60s — enough for ~5 "
             "chunks of the real call recording; the full recording is ~131s).",
    )
    args = parser.parse_args()

    try:
        originate_real_call_test(args.hold_seconds)
    except requests.RequestException as exc:
        print(f"Failed to reach Asterisk ARI at {ARI_URL}: {exc}", file=sys.stderr)
        print("Is 'docker compose up asterisk' running?", file=sys.stderr)
        sys.exit(1)

    print("Done. Check:")
    print("  - the 'transcripts' table in Postgres for several real chunks of call-center dialogue")
    print("  - the 'qa_scores' table a few seconds later for a content-aware score")
    print("  - the 'realtime_prompts' table / agent-ui live assist panel for any coaching nudges")


if __name__ == "__main__":
    main()
