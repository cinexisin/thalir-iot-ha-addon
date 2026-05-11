#!/usr/bin/with-contenv bashio
# Thalir IoT HA Add-on entrypoint

set -e

bashio::log.info "─── Thalir IoT add-on starting ───"

# Read user-configured options
CUSTOMER_NAME="$(bashio::config 'customer_name')"
CUSTOMER_PHONE="$(bashio::config 'customer_phone')"
CUSTOMER_LANG="$(bashio::config 'customer_language')"
GATEWAY_MODE="$(bashio::config 'gateway_mode')"
CLOUD_SYNC="$(bashio::config 'cloud_sync_enabled')"
CLOUD_ENDPOINT="$(bashio::config 'cloud_endpoint')"
LOG_LEVEL="$(bashio::config 'log_level')"

export THALIR_CUSTOMER_NAME="$CUSTOMER_NAME"
export THALIR_CUSTOMER_PHONE="$CUSTOMER_PHONE"
export THALIR_CUSTOMER_LANG="$CUSTOMER_LANG"
export THALIR_GATEWAY_MODE="$GATEWAY_MODE"
export THALIR_CLOUD_SYNC="$CLOUD_SYNC"
export THALIR_CLOUD_ENDPOINT="$CLOUD_ENDPOINT"
export THALIR_LOG_LEVEL="$LOG_LEVEL"
export HASSIO_TOKEN="${SUPERVISOR_TOKEN}"

bashio::log.info "Customer: ${CUSTOMER_NAME:-<unset>} (${CUSTOMER_PHONE:-<unset>}) lang=${CUSTOMER_LANG}"
bashio::log.info "Gateway mode: ${GATEWAY_MODE}"
bashio::log.info "Cloud sync: ${CLOUD_SYNC} → ${CLOUD_ENDPOINT}"

# Hand off to Python main loop
cd /opt/thalir
exec python3 -m thalir.main
