#!/bin/bash
set -e

# Use writable defaults for Pterodactyl/Docker environments. /opt and /data are
# often mounted read-only in this runtime, so keep Hermes state under the
# container's writable home instead.
: "${DATA_DIR:=/home/container/data}"
: "${HERMES_ROOT:=/home/container/hermes}"
: "${HERMES_HOME:=/home/container/.hermes}"

mkdir -p "${DATA_DIR}" "${HERMES_ROOT}" "${HERMES_HOME}"

# Refuse links before seeding directories/stamps. Config and .env are seeded
# by the preparation worker only after interrupted PM publication is recovered.
for path in "${HERMES_HOME}" "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/.env" "${HERMES_HOME}/profiles" \
            "${HERMES_HOME}/.install_method" "${HERMES_HOME}/auth.json"; do
  if [ -L "$path" ]; then
    echo "[template-config-migrate] ERROR: refusing symlinked Hermes path: $path" >&2
    exit 1
  fi
done

# Create the directories Hermes expects before the admin server starts.
mkdir -p "${HERMES_HOME}/cron" "${HERMES_HOME}/sessions" "${HERMES_HOME}/logs" \
         "${HERMES_HOME}/memories" "${HERMES_HOME}/skills" "${HERMES_HOME}/platforms/pairing" \
         "${HERMES_HOME}/hooks" "${HERMES_HOME}/cache/images" "${HERMES_HOME}/cache/audio" \
         "${HERMES_HOME}/workspace" "${HERMES_HOME}/skins" "${HERMES_HOME}/plans" \
         "${HERMES_HOME}/home"

# Stamp the install method as "docker" so hermes treats this as an immutable
# container image, not a pip checkout.
printf 'docker\n' > "${HERMES_HOME}/.install_method"

# PM now owns optional dependencies.
unset HERMES_LAZY_INSTALL_TARGET

# Bootstrap OAuth tokens from env var.
if [ ! -f "${HERMES_HOME}/auth.json" ] && [ -n "${HERMES_AUTH_JSON_BOOTSTRAP}" ]; then
  printf '%s' "${HERMES_AUTH_JSON_BOOTSTRAP}" > "${HERMES_HOME}/auth.json"
  chmod 600 "${HERMES_HOME}/auth.json"
fi

rm -f "${HERMES_HOME}/gateway.pid" "${HERMES_HOME}/gateway.lock" "${HERMES_HOME}/gateway.sock"

exec "${HERMES_ROOT}/wrapper-venv/bin/python" -E -s /app/server.py
