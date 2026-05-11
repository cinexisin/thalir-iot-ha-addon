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
    def __init__(self, farm_id: str, port: int = 1883):
        self.farm_id = farm_id
        self.port = port
        self.zc = None
        self.info = None

    def start(self):
        ip = _get_local_ip()
        log.info(f"Advertising mDNS _thalir-mqtt._tcp.local on {ip}:{self.port}")
        self.zc = Zeroconf(ip_version=IPVersion.V4Only)
        self.info = ServiceInfo(
            type_="_thalir-mqtt._tcp.local.",
            name=f"Thalir-{self.farm_id}._thalir-mqtt._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties={
                "farm_id": self.farm_id,
                "broker_port": str(self.port),
                "proto_version": "1",
                "product": "thalir-iot",
            },
            server=f"thalir-{self.farm_id.lower()}.local.",
        )
        self.zc.register_service(self.info)

    def stop(self):
        if self.zc and self.info:
            self.zc.unregister_service(self.info)
            self.zc.close()


def start(farm_id: str, port: int = 1883) -> MdnsAdvertiser:
    """Convenience: start advertising and return the advertiser object."""
    a = MdnsAdvertiser(farm_id=farm_id, port=port)
    a.start()
    return a
