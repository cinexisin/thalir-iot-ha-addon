"""
Thalir IoT HA Add-on — main entry point.

Lifecycle:
  1. On first boot: lockdown HA admin user, generate token, sync to cloud
  2. Always: advertise mDNS, run gateway bridge (LoRa<->MQTT)
  3. Background: heartbeat to Thalir Cloud every 5 min
"""
import logging
import os
import signal
import sys
import time
from pathlib import Path

from . import __version__
from . import lockdown
from . import mdns_advertise
from . import cloud_sync
from . import gateway_bridge


LOG_LEVEL = os.environ.get("THALIR_LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("thalir.main")

# Persistent state file (lives in HA's share/ which we mapped in config.yaml)
STATE_DIR = Path("/share/thalir_iot")
STATE_FILE = STATE_DIR / "state.json"


def ensure_first_boot_done():
    """Run lockdown + cloud sync ONCE on first boot.

    Subsequent boots skip — state.json records that init has completed.
    Dealer can force re-init by deleting /share/thalir_iot/state.json and restarting.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if STATE_FILE.exists():
        log.info("First-boot init already completed — skipping lockdown")
        return _load_state()

    log.info("First boot detected — running lockdown sequence")

    # 1. Lock down HA admin
    creds = lockdown.run()  # returns {'username', 'password', 'token', 'farm_id'}

    # 2. Push to Thalir Cloud (if cloud sync enabled)
    if os.environ.get("THALIR_CLOUD_SYNC", "true").lower() == "true":
        cloud_sync.register_customer(
            customer_name=os.environ.get("THALIR_CUSTOMER_NAME", ""),
            customer_phone=os.environ.get("THALIR_CUSTOMER_PHONE", ""),
            customer_language=os.environ.get("THALIR_CUSTOMER_LANG", "en"),
            ha_admin_token=creds["token"],
            farm_id=creds["farm_id"],
        )
    else:
        log.warning("Cloud sync disabled — token NOT pushed to cloud")

    _save_state(creds)
    log.info("First-boot init complete")
    return creds


def _save_state(creds: dict):
    import json
    sanitized = {k: v for k, v in creds.items() if k != "password"}
    STATE_FILE.write_text(json.dumps(sanitized, indent=2))
    STATE_FILE.chmod(0o600)


def _load_state() -> dict:
    import json
    return json.loads(STATE_FILE.read_text())


def main():
    log.info("=" * 60)
    log.info(f"Thalir IoT Add-on v{__version__}")
    log.info("=" * 60)

    # First-boot init
    state = ensure_first_boot_done()
    farm_id = state.get("farm_id")
    log.info(f"farm_id={farm_id}")

    # Start mDNS advertisement (so Heltec gateway can find broker)
    mdns = mdns_advertise.start(farm_id=farm_id)

    # Start gateway bridge (LoRa<->MQTT)
    bridge = gateway_bridge.start(
        farm_id=farm_id,
        mode=os.environ.get("THALIR_GATEWAY_MODE", "auto"),
    )

    # Heartbeat to cloud every 5 min
    def shutdown_handler(signum, frame):
        log.info("Shutting down…")
        mdns.stop()
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    last_heartbeat = 0
    while True:
        now = time.time()
        if now - last_heartbeat > 300:  # 5 min
            try:
                cloud_sync.heartbeat(farm_id=farm_id)
            except Exception as e:
                log.warning(f"Heartbeat failed (cloud unreachable): {e}")
            last_heartbeat = now
        time.sleep(5)


if __name__ == "__main__":
    main()
