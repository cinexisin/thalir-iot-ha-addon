#!/bin/sh
# Thalir IoT HA Add-on entrypoint.
#
# Plain shell (no s6-overlay / bashio) so we run cleanly as PID 1 regardless of
# which HA base image we sit on top of. Add-on options come from Supervisor as
# a JSON file at /data/options.json; we shell them out to env vars for the
# Python main loop.

set -e

echo "─── Thalir IoT add-on starting ───"

OPTS=/data/options.json
if [ ! -f "$OPTS" ]; then
  echo "ERROR: $OPTS missing - is this running under HA Supervisor?"
  exit 1
fi

# Extract options without depending on jq (python3 is always available in the base image).
read_opt() {
  python3 -c "import json,sys; d=json.load(open('$OPTS')); print(d.get('$1', '') if d.get('$1') is not None else '')"
}

CUSTOMER_NAME="$(read_opt customer_name)"
CUSTOMER_PHONE="$(read_opt customer_phone)"
CUSTOMER_LANG="$(read_opt customer_language)"
GATEWAY_MODE="$(read_opt gateway_mode)"
CLOUD_SYNC="$(read_opt cloud_sync_enabled)"
CLOUD_ENDPOINT="$(read_opt cloud_endpoint)"
MQTT_BROKER_PORT="$(read_opt mqtt_broker_port)"
MQTT_USERNAME="$(read_opt mqtt_username)"
MQTT_PASSWORD="$(read_opt mqtt_password)"
LOG_LEVEL="$(read_opt log_level)"

export THALIR_CUSTOMER_NAME="$CUSTOMER_NAME"
export THALIR_CUSTOMER_PHONE="$CUSTOMER_PHONE"
export THALIR_CUSTOMER_LANG="$CUSTOMER_LANG"
export THALIR_GATEWAY_MODE="$GATEWAY_MODE"
export THALIR_CLOUD_SYNC="$CLOUD_SYNC"
export THALIR_CLOUD_ENDPOINT="$CLOUD_ENDPOINT"
export THALIR_MQTT_BROKER_PORT="$MQTT_BROKER_PORT"
export THALIR_MQTT_USERNAME="$MQTT_USERNAME"
export THALIR_MQTT_PASSWORD="$MQTT_PASSWORD"
export THALIR_LOG_LEVEL="$LOG_LEVEL"
export HASSIO_TOKEN="${SUPERVISOR_TOKEN}"

echo "Customer: ${CUSTOMER_NAME:-<unset>} (${CUSTOMER_PHONE:-<unset>}) lang=${CUSTOMER_LANG}"
echo "Gateway mode: ${GATEWAY_MODE}"
echo "Cloud sync: ${CLOUD_SYNC} -> ${CLOUD_ENDPOINT}"
echo "MQTT: ${MQTT_USERNAME}@core-mosquitto:${MQTT_BROKER_PORT}"

# Hand off to Python main loop
cd /opt/thalir
exec python3 -m thalir.main
