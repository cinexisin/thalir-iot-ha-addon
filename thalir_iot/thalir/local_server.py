"""
Thalir IoT add-on — LAN fallback HTTP server.

When the phone is on the same WiFi as the gateway, it hits THIS server
(discovered via mDNS) before falling back to the cloud. Lets motors keep
working through WAN outages — which are common in rural Indian farms.

Endpoints (same shape as the cloud, so the phone-side code is uniform):
  GET  /v1/customer/motors
  POST /v1/customer/motor/<id>/start
  POST /v1/customer/motor/<id>/stop

Auth:
  HTTP header `Authorization: Bearer <local_token>`
  The token is minted in the CLOUD at user-login time and pushed to:
    - the agent (via the existing WebSocket — frame type "set_local_token")
    - the phone (via a fetch from cloud during bootstrap)
  Both sides cache it. Compromise of the LAN token can't be used against
  the cloud (it's only accepted by the local server).

mDNS:
  Advertised as `_thalir._tcp.local` with TXT records:
    farm_id=TF-XXXX
    version=1.2.0
  Phone uses NSD (Android) / Bonjour (iOS) to discover the gateway IP.
"""

import json
import logging
import os
import threading
import time
import http.server
import socketserver
import secrets

log = logging.getLogger("thalir.local_server")


# ============================================================ shared state

# The token the phone presents in Authorization: Bearer <token>.
# Set by the cloud relay over the WebSocket via a `set_local_token` frame.
# Until set, all requests get 503.
_local_token = None
_local_token_lock = threading.Lock()


def set_local_token(token: str):
    """Called by agent.py when the cloud sends a fresh local-bearer token."""
    global _local_token
    with _local_token_lock:
        _local_token = token
    log.info(f"local-token set (len={len(token)})")


def get_local_token():
    with _local_token_lock:
        return _local_token


# ============================================================ HA local proxy
# Reuse agent.py's HA REST helpers so we don't duplicate the entity resolver.
from . import agent as _agent


def _list_motors():
    _agent._refresh_entity_cache()
    motors = []
    for d in sorted(set(_agent._entity_cache["switch"].keys()) | {"motor1", "motor2"}):
        _, sw = _agent._ha_state(_agent._resolve_switch(d))
        _, st = _agent._ha_state(_agent._resolve_sensor(d, "status"))
        _, cu = _agent._ha_state(_agent._resolve_sensor(d, "current"))
        _, si = _agent._ha_state(_agent._resolve_sensor(d, "signal"))
        rec = _agent._build_motor_record(d, sw, st, cu, si)
        # Match cloud's wire shape
        motors.append({
            "id": d,
            "name": d.replace("motor", "Motor "),
            "state": rec["state"],
            "current_a": rec["current_a"],
            "signal_dbm": rec["signal_dbm"],
            "farm_id": os.environ.get("THALIR_FARM_ID", ""),
            "online": True,
        })
    return motors


def _motor_action(device, action):
    entity = _agent._resolve_switch(device)
    service = "turn_on" if action == "start" else "turn_off"
    status, _ = _agent._ha_service("switch", service, {"entity_id": entity})
    return status in (200, 201), {"status": status, "entity_id": entity}


# ============================================================ HTTP handler

class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ThalirGateway/1.2"

    def log_message(self, fmt, *args):
        # Pipe stdlib logging into ours
        log.info("LAN %s - %s" % (self.client_address[0], fmt % args))

    def _check_auth(self):
        token = get_local_token()
        if not token:
            self._json(503, {"error": "not_paired"})
            return False
        h = self.headers.get("Authorization", "")
        if not h.startswith("Bearer "):
            self._json(401, {"error": "no_token"})
            return False
        sent = h[7:].strip()
        if not secrets.compare_digest(sent, token):
            self._json(401, {"error": "invalid_token"})
            return False
        return True

    def _json(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Thalir-Gateway", "1")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/v1/customer/motors":
            if not self._check_auth(): return
            motors = _list_motors()
            self._json(200, {
                "installation": {"farm_id": os.environ.get("THALIR_FARM_ID", ""), "status": "active"},
                "motors": motors,
                "agent_online": True,
                "source": "lan",
            })
        elif self.path == "/v1/customer/ping":
            # Public liveness — used by phone to confirm "yes I'm a Thalir gateway"
            self._json(200, {
                "farm_id": os.environ.get("THALIR_FARM_ID", ""),
                "version": os.environ.get("THALIR_ADDON_VERSION", "1.2.0"),
                "service": "thalir-gateway",
            })
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        # /v1/customer/motor/<id>/start or /stop
        parts = self.path.strip("/").split("/")
        if len(parts) == 5 and parts[:3] == ["v1", "customer", "motor"] and parts[4] in ("start", "stop"):
            if not self._check_auth(): return
            device = parts[3]
            ok, info = _motor_action(device, parts[4])
            if not ok:
                self._json(502, {"ok": False, "error": "ha_call_failed", **info})
                return
            self._json(200, {"ok": True, "action": parts[4], "device": device, "transport": "lan", **info})
        else:
            self._json(404, {"error": "not_found"})


class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_singleton = None


def start(port: int = 8124):
    """Spin up the local HTTP server in a daemon thread."""
    global _singleton
    if _singleton is not None:
        return _singleton
    server = _ThreadedServer(("0.0.0.0", port), _Handler)
    th = threading.Thread(target=server.serve_forever, daemon=True, name="thalir-lan-http")
    th.start()
    log.info(f"LAN HTTP server listening on :{port}")
    _singleton = server
    return server


def stop():
    global _singleton
    if _singleton:
        try: _singleton.shutdown()
        except Exception: pass
        _singleton = None
