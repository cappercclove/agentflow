#!/usr/bin/env bash
# Back up the AgentFlow SQLite database, then prune copies older than 14 days.
#
# The database is in WAL mode and the app keeps writing to it, so a plain `cp`
# can capture a torn page. SQLite's online backup API reads through the WAL and
# produces a consistent single-file copy.
#
# The copy is made by a throwaway container from the app image (same Python, no
# extra pull). The app runs as a non-root user inside that image and the database
# belongs to it, so the backup directory has to be chown'ed to the same uid/gid,
# which means this script is meant to run as root -- as root's cron job does:
#   30 3 * * * /opt/agentflow/deploy/backup.sh >> /var/log/agentflow-backup.log 2>&1
#
# Local run against a different layout: AF_VOLUME / AF_BACKUP_DIR / AF_RETAIN_DAYS.
set -euo pipefail

VOLUME="${AF_VOLUME:-agentflow_agentflow-data}"
IMAGE="${AF_IMAGE:-agentflow-agentflow:latest}"
DB_NAME="${AF_DB_NAME:-workflows.db}"
BACKUP_DIR="${AF_BACKUP_DIR:-/var/backups/agentflow}"
RETAIN_DAYS="${AF_RETAIN_DAYS:-14}"

stamp="$(date +%Y%m%d-%H%M%S)"
out="$DB_NAME.$stamp.db"

fail() { echo "backup: $*" >&2; exit 1; }

docker volume inspect "$VOLUME" >/dev/null 2>&1 || fail "docker volume $VOLUME not found"
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "docker image $IMAGE not found"
mkdir -p "$BACKUP_DIR"

app_ids="$(docker run --rm --entrypoint id "$IMAGE" | sed -E 's/uid=([0-9]+).*gid=([0-9]+).*/\1:\2/')"
if [ "$(id -u)" = 0 ]; then
  chown "$app_ids" "$BACKUP_DIR"
elif [ ! -w "$BACKUP_DIR" ]; then
  fail "$BACKUP_DIR is not writable by uid $(id -u); run as root or set AF_BACKUP_DIR"
fi

docker run --rm \
  -v "$VOLUME:/data" \
  -v "$BACKUP_DIR:/backups" \
  --entrypoint python "$IMAGE" -c '
import sqlite3, sys

src_path, dst_path, name = sys.argv[1], sys.argv[2], sys.argv[3]
src, dst = sqlite3.connect(src_path), sqlite3.connect(dst_path)
try:
    with dst:
        src.backup(dst)
    check = dst.execute("pragma integrity_check").fetchone()[0]
    flows = dst.execute("select count(*) from workflows").fetchone()[0]
    runs = dst.execute("select count(*) from executions").fetchone()[0]
finally:
    src.close()
    dst.close()
if check != "ok":
    print("backup: integrity_check returned %s" % check, file=sys.stderr)
    raise SystemExit(1)
print("backup: %s ok (workflows=%d executions=%d)" % (name, flows, runs))
' "/data/$DB_NAME" "/backups/$out" "$out" || fail "backup of $VOLUME failed"

find "$BACKUP_DIR" -name "$DB_NAME.*.db" -type f -mtime +"$RETAIN_DAYS" -delete

# Fixed name for the newest copy so a restore is one command. Stop the app first,
# or the running connection keeps the old pages in the WAL:
#   docker compose -f /opt/agentflow/docker-compose.yml down
#   docker run --rm -v agentflow_agentflow-data:/data -v "$BACKUP_DIR:/backups" \
#     --entrypoint cp agentflow-agentflow:latest /backups/latest.db /data/workflows.db
#   docker compose -f /opt/agentflow/docker-compose.yml up -d
cp -f "$BACKUP_DIR/$out" "$BACKUP_DIR/latest.db"

used="$(du -sh "$BACKUP_DIR" | cut -f1)"
echo "backup: $BACKUP_DIR now holds $(find "$BACKUP_DIR" -name "$DB_NAME.*.db" | wc -l) copies, $used"
