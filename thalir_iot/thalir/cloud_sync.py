"""
Sync customer details + HA token to Thalir Cloud.

After lockdown, we POST the customer's encrypted HA token to
api.cinexis.cloud so the Thalir IoT customer app can talk to HA
indirectly via our cloud (customer never sees HA URL).

All payloads encrypted at rest in Postgres (iot.installations table column
ha_token is pgp_sym_encrypt'd with a master key only HQ holds).
"""
import logging
import os
from typing import Optional

import requests

log = logging.getLogger("thalir.cloud_sync")

DEFAULT_ENDPOINT = "https://iot-api.thalir.farm"


def _endpoint() -> str:
    return os.environ.get("THALIR_CLOUD_ENDPOINT", DEFAULT_ENDPOINT)


def _get_install_secret() -> Optional[str]:
    """
    Read the per-install secret. This is baked into the add-on at install time
    by the Installer App — it's a one-shot token that lets us register a NEW
    customer. After first sync, the cloud trusts the long-lived HA token.

    For now: read from /share/thalir_iot/install_secret if present, else None
    (meaning this is an unregistered install — cloud will create new customer
    record from scratch).
    """
    p = "/share/thalir_iot/install_secret"
    if os.path.exists(p):
        return open(p).read().strip()
    return None


def register_customer(
    customer_name: str,
    customer_phone: str,
    customer_language: str,
    ha_admin_token: str,
    farm_id: str,
) -> dict:
    """One-shot call after lockdown — registers this install with Thalir Cloud."""
    payload = {
        "farm_id": farm_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_language": customer_language,
        "ha_admin_token": ha_admin_token,
        "install_secret": _get_install_secret(),
        "addon_version": os.environ.get("THALIR_ADDON_VERSION", "1.0.0"),
    }
    log.info(f"Registering with Thalir Cloud: {_endpoint()}/v1/installs")
    log.debug(f"  payload (token redacted): { {**payload, 'ha_admin_token': '***'} }")
    try:
        r = requests.post(
            f"{_endpoint()}/v1/installs",
            json=payload,
            timeout=15,
        )
        if r.status_code in (200, 201):
            log.info(f"Cloud registration OK ({r.status_code})")
            return r.json()
        log.warning(f"Cloud registration returned {r.status_code}: {r.text[:200]}")
    except requests.exceptions.RequestException as e:
        log.warning(f"Cloud unreachable during registration: {e}")
        log.warning("Will retry on next heartbeat — local operation continues regardless")
    return {}


def heartbeat(farm_id: str) -> dict:
    """Periodic ping — keeps cloud aware of online status."""
    try:
        r = requests.post(
            f"{_endpoint()}/v1/installs/{farm_id}/heartbeat",
            json={"timestamp": _now_iso()},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return {}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
