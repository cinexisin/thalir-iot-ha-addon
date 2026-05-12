"""
Thalir IoT add-on — Cloud Agent (outbound persistent WebSocket).

Architecture:
    Cloud (wss://iot-api.thalir.farm/v1/agent)  ◀── this socket (NAT-pierced)
                                            │
                                            ▼
                       Local HA Supervisor REST API
                       (http://supervisor/core/api  with SUPERVISOR_TOKEN)

The customer's phone never reaches this HA box directly. The phone calls the
Thalir cloud, the cloud routes the request down this socket, this agent calls
HA locally via the Supervisor proxy, and the result is forwarded back.

Result: no port forwarding, no DDNS, no LAN-IP discovery, no manual tokens.

Auth:
    farm_id + agent_secret (both pasted into HA add-on options by the
    Installer App via QR scan, or auto-provisioned on a pre-baked HA OS image).

Re-connect strategy:
    Infinite retry with exponential backoff (1s → 60s, capped). NAT mappings
    are kept alive by the cloud's 25s server-side ping.
"""

import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error

try:
    import websocket  # websocket-client
except ImportError as e:
    raise SystemExit("websocket-client missing — add to Dockerfile pip install list") from e

log = logging.getLogger("thalir.agent")

ADDON_VERSION = os.environ.get("THALIR_ADDON_VERSION", "1.1.0")


# ============================================================ HA local proxy
#
# Two modes:
#   (a) Inside an HA add-on: Supervisor exposes http://supervisor/core/api and
#       SUPERVISOR_TOKEN is auto-injected. No manual token required.
#   (b) Standalone (e.g. dev box on the LAN): set HA_API_URL + HA_TOKEN env vars.
#       Useful before the add-on is published / for bench testing.

_HA_STANDALONE_URL   = os.environ.get("HA_API_URL")
_HA_STANDALONE_TOKEN = os.environ.get("HA_TOKEN")

if _HA_STANDALONE_URL and _HA_STANDALONE_TOKEN:
    HA_API = _HA_STANDALONE_URL.rstrip("/") + "/api"
    HA_TOKEN = _HA_STANDALONE_TOKEN
    log.info(f"agent: HA target = {HA_API} (standalone mode)")
else:
    HA_API = "http://supervisor/core/api"
    HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
    log.info("agent: HA target = supervisor proxy (add-on mode)")


def _ha_request(method: str, path: str, body=None, timeout=8):
    url = f"{HA_API}{path}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        log.warning(f"HA request failed: {e}")
        return 0, None


def _ha_service(domain: str, service: str, payload: dict):
    return _ha_request("POST", f"/services/{domain}/{service}", payload)


def _ha_state(entity_id: str):
    return _ha_request("GET", f"/states/{entity_id}")


# ============================================================ op dispatch

# Maps the wire-level `op` value (sent by the cloud) to the local handler.
# Each handler returns (ok: bool, data: dict).
#
# Keep this small + add ops only as the cloud uses them — the wire format is
# our contract and we don't want stale ops shipping unused.


def _op_motor_start(payload: dict):
    device = payload.get("device_id")
    if not device:
        return False, {"error": "device_id_required"}
    status, _ = _ha_service("switch", "turn_on", {"entity_id": f"switch.{device}"})
    return status in (200, 201), {"status": status}


def _op_motor_stop(payload: dict):
    device = payload.get("device_id")
    if not device:
        return False, {"error": "device_id_required"}
    status, _ = _ha_service("switch", "turn_off", {"entity_id": f"switch.{device}"})
    return status in (200, 201), {"status": status}


def _op_motor_state(payload: dict):
    device = payload.get("device_id")
    if not device:
        return False, {"error": "device_id_required"}
    _, sw = _ha_state(f"switch.{device}")
    _, st = _ha_state(f"sensor.{device}_status")
    _, cu = _ha_state(f"sensor.{device}_current")
    _, si = _ha_state(f"sensor.{device}_signal")
    return True, _build_motor_record(device, sw, st, cu, si)


def _op_motor_list_state(payload: dict):
    devices = payload.get("devices") or ["motor1", "motor2"]
    motors = []
    for d in devices:
        _, sw = _ha_state(f"switch.{d}")
        _, st = _ha_state(f"sensor.{d}_status")
        _, cu = _ha_state(f"sensor.{d}_current")
        _, si = _ha_state(f"sensor.{d}_signal")
        motors.append(_build_motor_record(d, sw, st, cu, si))
    return True, {"motors": motors}


def _op_ha_call(payload: dict):
    """Generic escape hatch — direct HA service call. Use sparingly."""
    domain = payload.get("domain")
    service = payload.get("service")
    if not domain or not service:
        return False, {"error": "domain_and_service_required"}
    data = payload.get("data") or {}
    status, body = _ha_service(domain, service, data)
    return status in (200, 201), {"status": status, "body": body}


def _build_motor_record(device, sw, status_sensor, current_sensor, signal_sensor):
    raw_status = (status_sensor or {}).get("state", "").lower() if status_sensor else ""
    if raw_status in ("running", "starting", "stopping", "error"):
        state = raw_status
    elif (sw or {}).get("state") == "on":
        state = "running"
    else:
        state = "stopped"

    def _flt(s):
        try:
            return float(s.get("state")) if s and s.get("state") not in (None, "unavailable", "unknown") else 0.0
        except (ValueError, TypeError):
            return 0.0

    return {
        "id": device,
        "state": state,
        "current_a": _flt(current_sensor),
        "signal_dbm": _flt(signal_sensor),
    }


OPS = {
    "motor_start": _op_motor_start,
    "motor_stop": _op_motor_stop,
    "motor_state": _op_motor_state,
    "motor_list_state": _op_motor_list_state,
    "ha_call": _op_ha_call,
}


# ============================================================ WS client loop

class CloudAgent(threading.Thread):
    def __init__(self, ws_url: str, farm_id: str, agent_secret: str):
        super().__init__(daemon=True, name="cloud-agent")
        self.ws_url = ws_url
        self.farm_id = farm_id
        self.agent_secret = agent_secret
        self._stop_evt = threading.Event()
        self._backoff = 1.0
        self._ws = None

    def stop(self):
        self._stop_evt.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass

    def run(self):
        while not self._stop_evt.is_set():
            try:
                self._connect_and_serve()
            except Exception as e:
                log.warning(f"agent loop error: {e}")
            if self._stop_evt.is_set():
                return
            sleep_for = min(self._backoff, 60.0)
            log.info(f"reconnecting in {sleep_for:.1f}s")
            time.sleep(sleep_for)
            self._backoff = min(self._backoff * 1.7, 60.0)

    def _connect_and_serve(self):
        log.info(f"connecting to {self.ws_url} farm_id={self.farm_id}")
        self._ws = websocket.create_connection(self.ws_url, timeout=15)
        log.info("connection established — sending hello")
        self._ws.send(json.dumps({
            "type": "hello",
            "farm_id": self.farm_id,
            "secret": self.agent_secret,
            "addon_version": ADDON_VERSION,
            "ha_version": _detect_ha_version(),
        }))

        # First frame must be hello_ok or we close.
        first = json.loads(self._ws.recv())
        if first.get("type") != "hello_ok":
            log.error(f"unexpected hello response: {first}")
            raise RuntimeError("hello_failed")

        log.info("authenticated — entering serve loop")
        self._backoff = 1.0  # reset backoff on successful connect

        while not self._stop_evt.is_set():
            try:
                raw = self._ws.recv()
            except websocket.WebSocketConnectionClosedException:
                log.info("server closed connection")
                return
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self._handle_frame(msg)

    def _handle_frame(self, msg):
        t = msg.get("type")
        if t == "ping":
            self._ws.send(json.dumps({"type": "pong", "ts": msg.get("ts")}))
        elif t == "request":
            self._dispatch_request(msg)
        elif t == "close":
            log.info(f"server requested close: {msg.get('reason')}")
            self._ws.close()
        # Unknown frames are ignored to allow protocol evolution.

    def _dispatch_request(self, msg):
        req_id = msg.get("req_id")
        op = msg.get("op", "")
        handler = OPS.get(op)
        if not handler:
            self._send_response(req_id, False, None, error=f"unknown_op:{op}")
            return
        try:
            ok, data = handler(msg)
            self._send_response(req_id, ok, data)
        except Exception as e:
            log.warning(f"op {op} crashed: {e}")
            self._send_response(req_id, False, None, error=str(e))

    def _send_response(self, req_id, ok, data, error=None):
        frame = {"type": "response", "req_id": req_id, "ok": ok, "data": data}
        if error:
            frame["error"] = error
        self._ws.send(json.dumps(frame))

    def publish_event(self, kind: str, device_id: str, state: str = None, **extra):
        """Unsolicited state-change push to the cloud. Called by gateway_bridge
        when a motor state changes locally (so the app gets pushed updates)."""
        if not self._ws:
            return
        try:
            self._ws.send(json.dumps({
                "type": "event",
                "kind": kind,
                "device_id": device_id,
                "state": state,
                "ts": int(time.time() * 1000),
                **extra,
            }))
        except Exception as e:
            log.debug(f"event publish failed: {e}")


# ============================================================ helpers

def _detect_ha_version() -> str:
    """Best-effort: query HA core for its version."""
    try:
        _, info = _ha_request("GET", "/")
        if isinstance(info, dict):
            return info.get("ha_version") or info.get("version") or "unknown"
    except Exception:
        pass
    return "unknown"


_singleton: CloudAgent = None


def start(farm_id: str, agent_secret: str, ws_url: str = None) -> CloudAgent:
    """Start the cloud agent in a background thread. Idempotent."""
    global _singleton
    if _singleton and _singleton.is_alive():
        return _singleton
    url = ws_url or os.environ.get("THALIR_WS_URL") or "wss://iot-api.thalir.farm/v1/agent"
    if not farm_id or not agent_secret:
        log.warning("farm_id or agent_secret missing — agent disabled. "
                    "Set them via add-on options to enable cloud control.")
        return None
    _singleton = CloudAgent(url, farm_id, agent_secret)
    _singleton.start()
    return _singleton


def get() -> CloudAgent:
    return _singleton
