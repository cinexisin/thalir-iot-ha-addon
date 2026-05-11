# Thalir IoT — Home Assistant Add-on

The single one-click installable add-on that ships in every Thalir IoT customer kit.

## What it does

When the dealer (or the Installer App) installs this add-on on a customer's
Home Assistant box, the add-on:

1. **Locks HA down** — creates a single admin user `thalir_admin` with a random
   password, deletes the default `homeassistant` user, generates a long-lived
   access token, sends the token + password securely to Thalir Cloud
   (`api.cinexis.cloud`) where it's stored encrypted.
   The customer **never sees** an HA login or admin URL.
2. **Advertises mDNS** — broadcasts `_thalir-mqtt._tcp.local` so the Thalir IoT
   Gateway (Heltec V3) can discover the broker without hardcoded IPs.
3. **Bridges the LoRa gateway** — accepts the gateway via either
   USB-Serial (`/dev/ttyACM0`) or MQTT over WiFi. Translates LoRa packets
   to MQTT topics under `thalir/farms/{farm_id}/...`.
4. **Pre-builds the Thalir dashboard** — installs a Lovelace YAML config so
   the moment the customer's first motor pairs, a branded "Thalir IoT" dashboard
   appears (visible only to dealer/support — customer uses our app instead).
5. **Pre-installs Mosquitto broker** (HA official add-on, dependency).
6. **Generates a per-customer farm_id** and stores it in HA `.storage` for
   the gateway to discover via mDNS-TXT records.

## Repository structure

```
ha-addon/
├── README.md               (this file)
├── config.yaml             HA add-on manifest
├── Dockerfile              Container image
├── run.sh                  Start script
├── thalir/                 Python package
│   ├── __init__.py
│   ├── main.py             Entry point
│   ├── lockdown.py         Locks HA admin, generates token
│   ├── mdns_advertise.py   Broadcasts _thalir-mqtt._tcp.local
│   ├── gateway_bridge.py   LoRa↔MQTT bridge (Serial + WiFi modes)
│   ├── cloud_sync.py       Pushes token + farm_id to Thalir Cloud
│   └── lovelace_template.yaml  Pre-built dashboard
├── translations/           Multi-language UI strings (en/ta/hi/kn/te)
└── rootfs/                 Files baked into the container
```

## Installation flow (dealer experience)

1. Customer's HA OS box is running, dealer has Installer App on phone.
2. App prompts: "Install Thalir IoT add-on" → tap once.
3. App uses HA Supervisor API to add the Thalir HACS repository and install
   the add-on. (Behind the scenes: `POST /supervisor/addons/install`.)
4. Add-on auto-starts on first boot, runs lockdown sequence (~30 seconds).
5. App polls `api.cinexis.cloud/customer/{id}/health` until green.
6. Done — dealer moves on to pairing motor starters.

## v1 implementation scope (this session)

- `config.yaml` + `Dockerfile` skeleton
- `lockdown.py` with admin-user rotation + token generation
- `mdns_advertise.py` with proper TXT records
- `cloud_sync.py` for posting token to Thalir Cloud
- Stub `gateway_bridge.py` (full LoRa↔MQTT bridge in v1.1)
- Pre-built Lovelace template

## v1.1 scope (post-launch, 1-2 weeks after)

- Full USB-Serial bridge for gateway (current v1: WiFi/MQTT only)
- Customer-language UI strings
- HACS publish (currently sideloaded)
- Auto-OTA from Thalir Cloud

## Cross-project safety

This add-on runs ONLY inside the customer's local HA instance. It does NOT
touch:
- Cinexis Bot infrastructure (separate AWS service)
- Thalir Farmer app (different codebase)
- EKANI CRM (separate Supabase)

It DOES talk outbound to:
- `api.cinexis.cloud` — to register the customer + push their HA token

It does NOT accept inbound from anywhere except the LoRa gateway (LAN).
