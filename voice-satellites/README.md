# Voice Satellites

ESP32-S3 voice assistant satellites — ESPHome configs, custom enclosures, and per-unit notes.

The HA voice pipeline itself (STT/TTS/conversation agent) is documented in `docs/decisions/003-voice-pipeline.md`. This folder is about the *physical* satellites: hardware, ESPHome firmware, and printed enclosures.

---

## Structure

```
voice-satellites/
├── README.md          ← this file
├── esphome/           ← per-unit ESPHome YAML configs
│   └── voice-garage.yaml
├── docs/              ← per-unit build notes, debugging logs, deployment notes
└── enclosures/        ← Fusion 360 / STL / STEP files or pointers to where they live
    └── README.md
```

---

## Current state

**Deployed:** 1 unit (garage). Wired, flashed, paired to HA.

**Pipeline:** HA Cloud STT/TTS, Davis voice (High quality). On-device wake word (microWakeWord). OpenAI tested but reverted due to billing and quality issues — see ADR-003.

**Hardware on hand:** 6× ESP32-S3 N16R8, 5× MAX98357A, 5× INMP441. Five more units to build.

**Planned locations:** kitchen, master bedroom, lanai, ?, ?

---

## Open issues

- **Sporadic audio quality** on garage unit. Suspected I2S clock drift on ESP32-S3 with esp-idf driver. Next step: test fixed MCLK pin on MAX98357A.
- **"Hey Nabu" wake word latency** — server-side openWakeWord adds latency vs on-device. Decision: accept for now, microWakeWord on-device path is the real fix; revisit later.

---

## ESPHome dashboard wiring

The ESPHome Builder add-on hardcodes its working directory to `/config/esphome/` (no configurable path option as of 2026-04-28). To make the dashboard see configs in their new home here, a symlink lives on the NUC:

```
/config/esphome -> /config/voice-satellites/esphome
```

Recreate with: `ln -s /config/voice-satellites/esphome /config/esphome` if it gets lost (e.g., after restoring from backup). The symlink itself is on disk only — it's not in git, so don't expect to see it in repo state.

---

## Per-unit naming convention

Each satellite gets:
- ESPHome config: `voice-satellites/esphome/voice-<location>.yaml`
- Hostname: `voice-<location>` (e.g., `voice-garage`)
- Friendly name in HA: `Voice <Location>` (title-cased)
- Static IP: reserve in UniFi DHCP

Example for garage: config `voice-garage.yaml`, hostname `voice-garage`, IP `192.168.11.229`, friendly name `Voice Garage`.

---

## Related references

- `docs/decisions/003-voice-pipeline.md` — pipeline choice rationale
- `docs/current-state.md` — voice satellites in-flight section
- `docs/device-inventory.md` — physical inventory (TBD; populate as units deploy)
