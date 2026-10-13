#!/data/data/com.termux/files/usr/bin/bash
# Run plan-bot in the foreground (a supervisor or Termux:Boot keeps it alive).
# Config comes from environment variables, loaded from $PLAN_BOT_ENV_FILE.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/plan-bot}"
ENV_FILE="${PLAN_BOT_ENV_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/plan-bot/env}"

if [ ! -r "$ENV_FILE" ]; then
  echo "missing $ENV_FILE (copy deploy/termux/env.example there)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] && [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
  echo "set DISCORD_BOT_TOKEN (or TELEGRAM_BOT_TOKEN) in $ENV_FILE" >&2
  exit 1
fi

# One instance per database: the scheduler lives inside the process.
LOCK="$APP_DIR/plan-bot.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  old="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "plan-bot is already running (pid $old)" >&2
    exit 1
  fi
fi
echo $$ >"$LOCK/pid"
trap 'rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || true' EXIT

cd "$APP_DIR"
"$APP_DIR/.venv/bin/plan-bot" migrate
# Not `exec`: the EXIT trap must run to release the lock. SIGTERM is forwarded.
"$APP_DIR/.venv/bin/plan-bot" run &
child=$!
trap 'kill -TERM "$child" 2>/dev/null' TERM INT
wait "$child" || status=$?
wait "$child" 2>/dev/null || true
exit "${status:-0}"
