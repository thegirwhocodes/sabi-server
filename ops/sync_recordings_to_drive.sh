#!/usr/bin/env bash
# Nightly: copy Sabi call audio + call records to Naomi's Google Drive, then
# free server disk by moving files older than RETENTION_DAYS. rclone `move`
# deletes a local file only after the upload is verified (size + MD5), so
# nothing leaves the server unless it is safely in Drive.
#
# Remote: "gdrive" (rclone, scope drive.file, account naomi.ivie04@gmail.com),
# folder "Sabi Call Recordings/shared_audio". Config: /root/.config/rclone/rclone.conf
# Cron: /etc/cron.d/sabi-recordings  (02:30 Lagos / 01:30 UTC)
set -euo pipefail

SRC="$(docker volume inspect -f '{{.Mountpoint}}' sabi-server_shared_audio)"
DEST="gdrive:Sabi Call Recordings/shared_audio"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
LOG=/var/log/sabi-recordings-sync.log
STAMP=/var/lib/sabi-recordings-last-success

# Files the running server needs locally, regenerated or reused every call.
KEEP_LOCAL=(--exclude "thinking_*.wav" --exclude "rt_greeting_*.wav" \
            --exclude "sabi_realtime_greeting.wav" --exclude "sabi_greeting_static.wav")

{
  echo "=== $(date -u +%FT%TZ) start (retention ${RETENTION_DAYS}d)"
  # 1. Back up everything older than 2 minutes (skips files still being written).
  rclone copy "$SRC" "$DEST" --min-age 2m --checksum --transfers 4 --stats-one-line --stats 0
  # 2. Free disk: move (verify, then delete local) anything older than retention.
  rclone move "$SRC" "$DEST" --min-age "${RETENTION_DAYS}d" --checksum "${KEEP_LOCAL[@]}" --stats-one-line --stats 0
  # 3. Confirm every remaining local file is also in Drive.
  rclone check "$SRC" "$DEST" --one-way --min-age 2m "${KEEP_LOCAL[@]}"
  date -u +%FT%TZ > "$STAMP"
  echo "=== $(date -u +%FT%TZ) ok; local $(du -sh "$SRC" | cut -f1); disk $(df -h / | awk 'NR==2{print $5}')"
} >> "$LOG" 2>&1
