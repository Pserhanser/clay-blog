#!/usr/bin/env bash
# 本地准备的服务器脚本副本。必须单独安装；应用发布不会更新此脚本。
# 专用 authorized_keys: command="/usr/local/lib/hanser-blog/server-deploy.sh",restrict
set -euo pipefail
umask 022

STATE=/home/ubuntu/hanser-blog-ci
REPO="$STATE/application"
ROOT=/var/www/hanser.fireemblem.top
SITE=https://hanser.fireemblem.top
mkdir -p "$STATE"
exec 9>"$STATE/deploy.lock"
flock -n 9 || { echo 'Another blog deployment is running'; exit 1; }
test ! -f "$STATE/DEPLOY_PAUSED" || { echo 'Blog deployment paused'; exit 1; }
test -f "$STATE/ANALYTICS_READY" || { echo 'Private analytics bootstrap is not installed/approved'; exit 1; }
exec > >(tee -a "$STATE/deploy.log") 2>&1

# Accept only a complete commit ID passed by CI, never arbitrary shell input.
REQUEST="${SSH_ORIGINAL_COMMAND:-${1:-}}"
[[ "$REQUEST" =~ ^deploy\ ([0-9a-f]{40})$ ]] || { echo 'Expected deploy <40-character SHA>'; exit 1; }
SHA="${BASH_REMATCH[1]}"
git -C "$REPO" fetch --no-tags origin main
test "$(git -C "$REPO" rev-parse origin/main)" = "$SHA" || { echo 'Refusing stale/non-main commit'; exit 1; }
OLD=$(readlink -f "$ROOT/current")
test -d "$OLD" && test "$(dirname "$OLD")" = "$ROOT/releases"
if test -f "$OLD/site/_release.json" && grep -q "$SHA" "$OLD/site/_release.json"; then
  echo 'This commit is already deployed'; exit 0
fi

BUILD=$(mktemp -d "$STATE/build.XXXXXXXX")
trap 'rm -rf -- "$BUILD"' EXIT
git -C "$REPO" archive "$SHA" | tar -x -C "$BUILD"
# Build resources are capped independently of the existing fefw service.
docker run --rm --memory=1g --memory-swap=2g --cpus=1 \
  --user "$(id -u):$(id -g)" -v "$BUILD:/app" -w /app \
  -e HOME=/tmp -e NPM_CONFIG_CACHE=/tmp/npm-cache \
  -e SITE_URL="$SITE" -e NODE_OPTIONS=--max-old-space-size=768 \
  node:24-bookworm-slim sh -c 'npm ci --include=dev --no-audit --no-fund && npm run build'
test -f "$BUILD/dist/index.html" && test -f "$BUILD/dist/archive/index.html"
printf '{"sha":"%s"}\n' "$SHA" > "$BUILD/dist/_release.json"
NEW="$ROOT/releases/$(date -u +%Y%m%d-%H%M%S)-${SHA:0:12}"
sudo -n install -d -o root -g www-data -m 755 "$NEW"
sudo -n install -d -o root -g www-data -m 755 "$NEW/site"
sudo -n cp -a "$BUILD/dist/." "$NEW/site/"
sudo -n cp -a "$BUILD/server" "$NEW/server"
sudo -n chown -R root:www-data "$NEW"
sudo -n find "$NEW" -type d -exec chmod 755 {} +
sudo -n find "$NEW" -type f -exec chmod 644 {} +

switch_to() {
  sudo -n ln -sfn "$1" "$ROOT/current.new"
  sudo -n mv -Tf "$ROOT/current.new" "$ROOT/current"
}
switch_to "$NEW"
if ! sudo -n systemctl restart hanser-blog-analytics.service; then
  switch_to "$OLD"
  sudo -n systemctl restart hanser-blog-analytics.service || true
  sudo -n rm -rf -- "$NEW"
  echo 'Backend restart failed; previous release restored'
  exit 1
fi
healthy=false
for attempt in 1 2 3 4 5; do
  if curl -fsS --max-time 10 --resolve hanser.fireemblem.top:443:127.0.0.1 "$SITE/_release.json" | grep -q "$SHA" && \
     curl -fsS --max-time 10 --resolve hanser.fireemblem.top:443:127.0.0.1 "$SITE/" -o /dev/null && \
     curl -fsS --max-time 10 --resolve hanser.fireemblem.top:443:127.0.0.1 "$SITE/archive/" -o /dev/null && \
     curl -fsS --max-time 10 --resolve hanser.fireemblem.top:443:127.0.0.1 "$SITE/api/health" -o /dev/null; then
    healthy=true; break
  fi
  sleep 2
done
if test "$healthy" != true; then
  switch_to "$OLD"
  sudo -n systemctl restart hanser-blog-analytics.service
  sudo -n rm -rf -- "$NEW"
  echo "Health check failed; restored $OLD"
  exit 1
fi
# Pruning runs only after a healthy switch. Preserve current and last healthy.
sudo -n python3 /usr/local/lib/hanser-blog/prune-releases.py --root "$ROOT" --previous "$OLD" --apply
echo "Blog release succeeded: $SHA (maximum 3 release directories)"
