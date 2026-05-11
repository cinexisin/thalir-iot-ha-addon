# Thalir IoT HA Add-on — Dealer Installation Guide

This is what a dealer does at a customer site once their Home Assistant box
is powered on and accessible.

## Prerequisites at customer site

- Home Assistant OS (or Supervised) installed on a Raspberry Pi / NAS / mini-PC
- HA box is on the customer's home WiFi and has internet access
- Dealer has the Thalir Installer App on their phone

## Installation — 3 steps, ~3 minutes

### 1. Add Thalir add-on repository to Home Assistant

Open the HA web UI on a laptop/phone (one-time access via dealer's laptop only):

- Navigate to **Settings → Add-ons → Add-on Store**
- Click the **three-dot menu (⋮)** in the top-right → **Repositories**
- Paste this URL and click **ADD**:

  ```
  https://github.com/cinexis-hq/thalir-iot-ha-addon
  ```

- Close the repositories dialog. The store now shows **Thalir IoT Add-ons**.

### 2. Install the Thalir IoT add-on

- Scroll to **Thalir IoT Add-ons** section in the store
- Click **Thalir IoT** → **INSTALL**
- Wait ~30 seconds for download

### 3. Configure + start

In the add-on Configuration tab, set:

| Option | Value |
|---|---|
| Customer name | (the customer's name, free text) |
| Customer phone | E.164 format, e.g. `+919900000000` |
| Customer language | `en`, `ta`, `hi`, `kn`, or `te` |
| Gateway mode | `auto` (auto-detects USB-Serial vs WiFi) |
| Cloud sync enabled | `true` |
| Cloud endpoint | `https://thalir-api.cinexis.cloud` |

Then go to **Info** tab → toggle **Start on boot** and **Watchdog** ON →
click **START**.

## What the add-on does on first boot

1. Creates the HA admin user `thalir_admin` with random password
2. Generates long-lived access token, encrypts it, sends to Thalir Cloud
3. Advertises `_thalir-mqtt._tcp.local` mDNS so the gateway can find the broker
4. Pre-installs the Thalir-branded Lovelace dashboard (dealer-only)
5. Heartbeats to cloud every 5 minutes for online status

## Verifying success

- Add-on log should show `Lockdown complete — farm_id=XX-XXXX`
- Within 60 seconds, `https://thalir-api.cinexis.cloud/v1/installs/{farm_id}/heartbeat`
  should respond `{ok: true}`
- The customer's farm shows up in the Dealer Portal automatically.

## Recovery / Re-pairing

If the customer changes their WiFi router or HA box IP changes:

- Open the add-on → toggle Restart
- The mDNS broadcast will refresh and the gateway will re-discover the broker.

If the dealer needs to **fully reset** the install (e.g., reassign to a different
customer):

- Uninstall the add-on from HA
- Delete the file `/share/thalir_iot/state.json` via HA Terminal or SSH add-on
- Reinstall — runs first-boot lockdown again

## Repository structure (for developers)

```
thalir-iot-ha-addon/
├── repository.json           HACS repo metadata
├── thalir_iot/
│   ├── config.yaml           Add-on manifest
│   ├── Dockerfile            Container image
│   ├── run.sh                Entry point
│   ├── thalir/               Python source
│   └── translations/         Multi-language UI
└── README.md                 (this section, plus dev docs)
```

## Support

- Dealer portal: <https://thalir-dealer.cinexis.cloud>
- Issues: open a support ticket in the Dealer Portal, OR `ops@cinexis.cloud`
