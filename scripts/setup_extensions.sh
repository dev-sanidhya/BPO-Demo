#!/usr/bin/env bash
# Extensions 1001 (agent) and 1002 (customer) are already defined statically
# in asterisk/conf/pjsip.conf — nothing to provision at runtime. This script
# just waits for Asterisk's ARI to come up and prints everything you need to
# register a real softphone (Zoiper, Linphone, MicroSIP) against them for
# manual two-party testing, alongside scripts/make_test_call.py for fully
# automated no-softphone testing.
set -euo pipefail

ARI_URL="${ARI_URL:-http://localhost:8088/ari}"
ARI_USER="${ARI_USER:-asterisk}"
ARI_PASSWORD="${ARI_PASSWORD:-changeme_ari_password}"

echo "Waiting for Asterisk ARI at ${ARI_URL} ..."
for i in $(seq 1 30); do
  if curl -sf -u "${ARI_USER}:${ARI_PASSWORD}" "${ARI_URL}/asterisk/info" > /dev/null 2>&1; then
    echo "Asterisk is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Timed out waiting for Asterisk. Is 'docker compose up asterisk' running?" >&2
    exit 1
  fi
  sleep 2
done

echo
echo "Registered PJSIP endpoints:"
curl -sf -u "${ARI_USER}:${ARI_PASSWORD}" "${ARI_URL}/endpoints" | python3 -m json.tool || true

cat <<'EOF'

------------------------------------------------------------------
Manual two-party test (softphone) — Zoiper / Linphone / MicroSIP:

  Agent softphone (extension 1001, WebRTC):
    Use the browser agent-ui at http://localhost:${AGENT_UI_PORT:-8080}
    instead of a desktop softphone — 1001 is configured for WebRTC only.

  Customer softphone (extension 1002, plain SIP/UDP):
    Server:    localhost  (or your host's LAN IP)
    Port:      5060
    Username:  1002
    Password:  changeme1002  (see asterisk/conf/pjsip.conf)
    Transport: UDP

  Dial 1001 from the 1002 softphone (or vice versa via the agent-ui) to
  place a real two-party internal call — no SIP trunk required.

Automated single-party test (no softphone needed at all):
  python3 scripts/make_test_call.py
------------------------------------------------------------------
EOF
