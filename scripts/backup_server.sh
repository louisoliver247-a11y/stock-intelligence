#!/bin/bash
# Root-owned local database/configuration backup for the dedicated VPS deployment.
set -euo pipefail
umask 077
target=/var/backups/stock-intelligence
install -d -m 700 "$target"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
runuser -u postgres -- pg_dump -Fc stock_intelligence > "$target/$stamp.dump"
test -s "$target/$stamp.dump"
tar -czf "$target/$stamp-config.tar.gz" -C / \
  opt/stock-intelligence/.env \
  etc/stock-intelligence \
  etc/systemd/system/stock-intelligence-api.service \
  etc/systemd/system/stock-intelligence-worker.service \
  etc/systemd/system/stock-intelligence-redis.service \
  usr/local/lsws/conf/vhosts/trading.caselawindia.io/vhost.conf
printf 'Stock Intelligence backup completed: %s\n' "$stamp"
