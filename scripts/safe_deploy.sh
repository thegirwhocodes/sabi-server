#!/usr/bin/env bash
# Recreate the Sabi container only when no call is in progress.
#
# Restarting sabi-server severs the AudioSocket of any live call: Asterisk logs
# "Failed to receive frame from AudioSocket" and the learner is hung up on
# mid-lesson. This has now happened twice — Codex cut a 371-second call on Aug 7,
# and I cut a 46-second one on Aug 13 because my check *printed* the channel count
# instead of gating on it, so the `&&` chain ran regardless.
#
# The lesson is that the count has to be parsed and acted on, not displayed.
#
#   ./scripts/safe_deploy.sh              # abort if any call is active
#   ./scripts/safe_deploy.sh --wait 300   # poll up to 5 minutes for the line to clear
#   ./scripts/safe_deploy.sh --force      # deploy anyway; will drop live calls
#
# Run on the server, from /opt/sabi/sabi-server.

set -euo pipefail

WAIT_SECONDS=0
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait) WAIT_SECONDS="${2:?--wait needs seconds}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

active_calls() {
  # "N active calls" — take the integer, defaulting to a nonzero sentinel so an
  # unreadable Asterisk is treated as unsafe rather than as an empty line.
  docker exec sabi-asterisk asterisk -rx "core show channels" 2>/dev/null \
    | awk '/active call/ {print $1; found=1} END {if (!found) print 99}'
}

deadline=$(( $(date +%s) + WAIT_SECONDS ))
while :; do
  calls="$(active_calls)"

  if [[ "$calls" == "0" ]]; then
    break
  fi

  if [[ "$FORCE" == "1" ]]; then
    echo "WARNING: $calls call(s) active — deploying anyway because --force was given."
    echo "         Any learner on the line will be cut off mid-lesson."
    break
  fi

  if [[ $(date +%s) -ge $deadline ]]; then
    echo "REFUSING TO DEPLOY: $calls call(s) active." >&2
    echo "Someone is on the phone with Sabi right now. Wait for the line to clear," >&2
    echo "or re-run with --wait <seconds>, or --force to cut them off deliberately." >&2
    exit 1
  fi

  echo "$calls call(s) active — waiting for the line to clear..."
  sleep 5
done

echo "line clear — recreating sabi"
docker compose up -d --no-deps sabi

sleep 10
docker exec sabi-server python -c "
import gemini_live as g
print('voice:', g.GEMINI_LIVE_VOICE)
print('model:', g.GEMINI_LIVE_MODEL)
print('prompt:', 'G' if 'HOW YOU SOUND' in g.GEMINI_LIVE_TUTOR_PROMPT else 'other')
"
docker ps --filter name=sabi-server --format '{{.Names}} {{.Status}}'
