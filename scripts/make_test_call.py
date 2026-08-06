#!/usr/bin/env python3
"""
Originate a fully self-contained test call with zero SIP trunk, zero
softphone, and zero second party.

Asterisk answers itself on the 'autotest' extension (asterisk/conf/
extensions.conf), plays bundled demo audio to stand in for customer speech,
records the call, and routes it through the realtime-assist ARI tap exactly
like a real call would be. Use this to prove the whole pipeline — recording,
QA scoring, real-time assist, dashboard — end-to-end without any telephony
infrastructure beyond the asterisk container itself.
"""
import argparse
import os
import sys
import time

import requests

ARI_URL = os.environ.get("ARI_URL", "http://localhost:8088/ari")
ARI_USER = os.environ.get("ARI_USER", "asterisk")
ARI_PASSWORD = os.environ.get("ARI_PASSWORD", "changeme_ari_password")


def originate_test_call(hold_seconds: float) -> str:
    auth = (ARI_USER, ARI_PASSWORD)

    resp = requests.post(
        f"{ARI_URL}/channels",
        auth=auth,
        # ARI requires an explicit extension+context (or `app`) even when
        # the endpoint string is a fully-qualified Local channel — passing
        # only `endpoint` returns 400 "Application or extension must be
        # specified". Confirmed against a live Asterisk 20 instance.
        params={
            "endpoint": "Local/autotest@internal",
            "extension": "autotest",
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
    print(f"Originated test call. Asterisk channel id: {channel_id}")
    print("(the call's UNIQUEID / calls.call_id in Postgres may differ slightly "
          "from this ARI channel id for Local channels with two legs — check "
          "the 'calls' table for the most recent row if they don't match)")

    print(f"Holding the call open for {hold_seconds:.0f}s so realtime-assist "
          f"has time to produce at least one chunked prompt...")
    time.sleep(hold_seconds)

    try:
        requests.delete(f"{ARI_URL}/channels/{channel_id}", auth=auth, timeout=10)
    except requests.RequestException:
        pass  # likely already hung up on its own after Playback finished

    return channel_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=20.0,
        help="How long to keep the test call open before hanging up (default: 20s, "
             "enough for one 10-15s realtime-assist chunk to fire).",
    )
    args = parser.parse_args()

    try:
        originate_test_call(args.hold_seconds)
    except requests.RequestException as exc:
        print(f"Failed to reach Asterisk ARI at {ARI_URL}: {exc}", file=sys.stderr)
        print("Is 'docker compose up asterisk' running? Try scripts/setup_extensions.sh first.",
              file=sys.stderr)
        sys.exit(1)

    print("Done. Check:")
    print("  - the shared 'recordings' volume for a new .wav file")
    print("  - the 'calls' table in Postgres for a new row")
    print("  - the 'qa_scores' table a few seconds later (qa-scoring worker picks it up async)")
    print("  - the realtime-assist websocket / agent-ui for a live prompt during the hold window")


if __name__ == "__main__":
    main()
