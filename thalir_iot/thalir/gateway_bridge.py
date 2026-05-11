"""
LoRa Gateway bridge — connects the Heltec V3 gateway to HA's MQTT broker.

Two modes (auto-detected at start, can be forced via THALIR_GATEWAY_MODE env):

  - serial : gateway plugged into HA box via USB-C, enumerated as /dev/ttyACM0
             Bridge reads JSON lines, forwards them to MQTT.
  - wifi   : gateway is on the same LAN, talks MQTT directly. Bridge does
             nothing — gateway publishes/subscribes to the local Mosquitto.

In v1 we focus on `wifi` mode (gateway speaks MQTT natively, already supported
in firmware v1.7.0). USB-Serial mode is stubbed for v1.1.

Topic schema (under thalir/farms/{farm_id}/):
  +/status         motor1/status, motor2/status, valve1/status, ...
  +/cmd            motor1/cmd (start|stop|toggle)
  +/config         motor1/config (JSON: thresholds, calibration, etc.)
  gateway/status   gateway-level health
"""
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("thalir.bridge")


class GatewayBridge:
    def __init__(self, farm_id: str, mode: str = "auto"):
        self.farm_id = farm_id
        self.mode = mode
        self.actual_mode: Optional[str] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.actual_mode = self._detect_mode()
        log.info(f"Gateway bridge starting in {self.actual_mode!r} mode")

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        log.info("Gateway bridge stopping…")
        self.running = False

    def _detect_mode(self) -> str:
        """Return 'serial' if USB ACM device present, else 'wifi'."""
        if self.mode in ("serial", "wifi"):
            return self.mode
        # auto-detect
        for candidate in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"]:
            if Path(candidate).exists():
                return "serial"
        return "wifi"

    def _run_loop(self):
        if self.actual_mode == "serial":
            self._run_serial()
        else:
            self._run_wifi_passive()

    def _run_serial(self):
        """Read JSON-newline-delimited packets from /dev/ttyACM0, forward to MQTT.

        Stub for v1 — full implementation in v1.1.
        """
        log.warning("Serial mode is stubbed in v1 — gateway should use WiFi/MQTT instead")
        while self.running:
            time.sleep(5)

    def _run_wifi_passive(self):
        """Gateway publishes/subscribes to local Mosquitto directly.

        Nothing for the bridge to do — we just keep alive and log periodically
        for observability. In v1.1 we add a watchdog: if no gateway packet
        in 5 minutes, alert + restart Mosquitto.
        """
        last_log = 0
        while self.running:
            now = time.time()
            if now - last_log > 60:
                log.debug(f"WiFi passive mode: farm_id={self.farm_id}, watching MQTT…")
                last_log = now
            time.sleep(5)


def start(farm_id: str, mode: str = "auto") -> GatewayBridge:
    b = GatewayBridge(farm_id=farm_id, mode=mode)
    b.start()
    return b
