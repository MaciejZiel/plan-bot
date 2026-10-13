#!/data/data/com.termux/files/usr/bin/bash
# Install or update plan-bot inside Termux. Safe to run again.
#   bash deploy/termux/install.sh               # Discord and Telegram support
#   WITH_DISCORD=0 bash deploy/termux/install.sh   # Telegram only
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/plan-bot}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/plan-bot"

pkg install -y python clang make libffi openssl

mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$CONFIG_DIR"
python -m venv "$APP_DIR/.venv"

# Android has no prebuilt wheels for aiohttp's C helpers: use the pure-Python fallbacks.
export AIOHTTP_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1 \
       FROZENLIST_NO_EXTENSIONS=1 PROPCACHE_NO_EXTENSIONS=1

"$APP_DIR/.venv/bin/pip" install --upgrade pip
extras=""
if [ "${WITH_DISCORD:-1}" = "1" ]; then extras="[discord]"; fi
"$APP_DIR/.venv/bin/pip" install --upgrade "$SRC_DIR$extras"

if [ ! -f "$CONFIG_DIR/env" ]; then
  cp "$SRC_DIR/deploy/termux/env.example" "$CONFIG_DIR/env"
  chmod 600 "$CONFIG_DIR/env"
  echo "Created $CONFIG_DIR/env: put DISCORD_BOT_TOKEN (or TELEGRAM_BOT_TOKEN) in it before starting."
fi

install -m 755 "$SRC_DIR/deploy/termux/start.sh" "$APP_DIR/start.sh"
mkdir -p "$HOME/.termux/boot"
install -m 755 "$SRC_DIR/deploy/termux/boot-plan-bot" "$HOME/.termux/boot/plan-bot"
"$APP_DIR/.venv/bin/plan-bot" --help >/dev/null
echo "Installed. Start now with: $APP_DIR/start.sh   (it also starts on boot via Termux:Boot)"
