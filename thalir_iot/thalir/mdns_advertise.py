"""
Advertise _thalir-mqtt._tcp.local via mDNS so the Heltec V3 gateway can find us.

The Heltec gateway boots, joins WiFi, and queries for `_thalir-mqtt._tcp.local`.
It picks the first responder and connects to that IP:port for MQTT.

TXT records advertise:
  farm_id=TF-A1B2          (so gateway knows which farm it's joining)
  broker_port=1883
  proto_version=1
"""
import logging
import socket
from zeroconf import IPVersion, ServiceInfo, Zeroconf

log = logging.getLogger("thalir.mdns")


def _get_local_ip() -> str:
    """Best-effort: find the IP this HA box uses on the LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class MdnsAdvertiser:
    """Advertises BOTH services the gateway hosts:
       - _thalir-mqtt._tcp on 1883 (for the Heltec gateway board)
       - _thalir._tcp     on 8124 (for the Farmer app's LAN fallback)
    """
    def __init__(self, farm_id: str, mqtt_port: int = 1883, http_port: int = 8124,
                 addon_version: str = "1.2.0"):
        self.farm_id = farm_id
        self.mqtt_port = mqtt_port
        self.http_port = http_port
        self.addon_version = addon_version
        self.zc = None
        self.services = []

    def start(self):
        ip = _get_local_ip()
        self.zc = Zeroconf(ip_version=IPVersion.V4Only)

        # 1. MQTT broker (for the gateway board)
        mqtt_info = ServiceInfo(
            type_="_thalir-mqtt._tcp.local.",
            name=f"Thalir-{self.farm_id}._thalir-mqtt._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=self.mqtt_port,
            properties={
                "farm_id": self.farm_id,
                "broker_port": str(self.mqtt_port),
                "proto_version": "1",
                "product": "thalir-iot",
            },
            server=f"thalir-{self.farm_id.lower()}.local.",
        )

        # 2. LAN fallback HTTP (for the Farmer app)
        http_info = ServiceInfo(
            type_="_thalir._tcp.local.",
            name=f"Thalir-{self.farm_id}._thalir._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=self.http_port,
            properties={
                "farm_id": self.farm_id,
                "version": self.addon_version,
                "product": "thalir-gateway",
                "ping_path": "/v1/customer/ping",
            },
            server=f"thalir-{self.farm_id.lower()}.local.",
        )

        for svc in (mqtt_info, http_info):
            try:
                self.zc.register_service(svc)
                self.services.append(svc)
                log.info(f"Advertising mDNS {svc.type} on {ip}:{svc.port}")
            except Exception as e:
                log.warning(f"mDNS register failed for {svc.type}: {e}")

    def stop(self):
        if not self.zc: return
        for svc in self.services:
            try: self.zc.unregister_service(svc)
            except Exception: pass
        try: self.zc.close()
        except Exception: pass
        self.services = []


def start(farm_id: str, mqtt_port: int = 1883, http_port: int = 8124,
          addon_version: str = "1.2.0") -> MdnsAdvertiser:
    """Convenience: start advertising and return the advertiser object."""
    a = MdnsAdvertiser(farm_id=farm_id, mqtt_port=mqtt_port,
                       http_port=http_port, addon_version=addon_version)
    a.start()
    return a
