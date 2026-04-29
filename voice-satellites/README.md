# Voice Satellites

ESP32-S3 voice assistant satellites — build notes, enclosures, and per-unit deployment context. The actual ESPHome firmware configs live at `/config/esphome/` (repo path: `esphome/`), not in this folder.

The HA voice pipeline itself (STT/TTS/conversation agent) is documented in `docs/decisions/003-voice-pipeline.md`.

---

## Structure

```
voice-satellites/
├── README.md          ← this file
├── docs/              ← per-unit build notes, debugging logs, deployment notes
└── enclosures/        ← Fusion 360 / STL / STEP files or pointers to where they live
    └── README.md
```

ESPHome firmware configs:

```
esphome/                ← at repo root, mounts to /config/esphome on the NUC
├── voice-garage.yaml
└── (future: voice-kitchen.yaml, voice-bedroom.yaml, etc.)
```

This split is intentional. ESPHome's dashboard insists configs live at `/config/esphome/` and rejects symlink workarounds via path-traversal validation. So firmware lives where ESPHome wants it; this folder owns the surrounding context that ESPHome doesn't care about.

---

## Current state

**Deployed:** 1 unit (garage). Wired, flashed, paired to HA. Recovered 2026-04-28 after an Ollama conversation-agent reference left the device stuck in `voice_assistant.on_error` (red LED). Pipeline restored to HA Cloud.

**Pipeline:** HA Cloud STT/TTS, Davis voice (High quality). On-device wake word (microWakeWord). See ADR-003 for canonical-vs-experimental agent options (HA Cloud canonical; Ollama and OpenAI both supported as alternatives but expect drift to break things if not actively monitored).

**Hardware on hand:** 6× ESP32-S3 N16R8, 5× MAX98357A, 5× INMP441. Five more units to build.

**Planned locations:** kitchen, master bedroom, lanai, ?, ?

---

## Open issues

- **Sporadic audio quality** on garage unit. Suspected I2S clock drift on ESP32-S3 with esp-idf driver. Next step: test fixed MCLK pin on MAX98357A.
- **"Hey Nabu" wake word latency** — server-side openWakeWord adds latency vs on-device. Decision: accept for now, microWakeWord on-device path is the real fix; revisit later.
- **Pipeline drift risk.** A pipeline pointing at a removed/offline conversation agent (e.g. an Ollama server that's down) puts every assigned satellite into a tight error retry loop on the device. Worth a periodic audit of pipeline assignments.

---

## ESPHome dashboard wiring (for context)

The ESPHome Builder app reads from `/config/esphome/` directly — no symlink, no special wiring needed. The repo's `esphome/` folder maps to `/config/esphome/` on the NUC because the repo IS `/config`.

`secrets.yaml` resolution: ESPHome looks for `secrets.yaml` in the same directory as the config file, NOT by walking up to `/config/`. The fix used on the NUC: a symlink at `/config/esphome/secrets.yaml -> /config/secrets.yaml` so all secrets live in one canonical file. The symlink itself isn't tracked in git.

If `/config/esphome/secrets.yaml` ever goes missing on the NUC (e.g., after a backup restore), recreate with:

```
ln -s /config/secrets.yaml /config/esphome/secrets.yaml
```

---

## Per-unit naming convention

Each satellite gets:
- ESPHome config: `esphome/voice-<location>.yaml` (repo path; lives at `/config/esphome/voice-<location>.yaml` on the NUC)
- Hostname: `voice-<location>` (e.g., `voice-garage`)
- Friendly name in HA: `Voice <Location>` (title-cased)
- Static IP: reserve in UniFi DHCP

Example for garage: config `voice-garage.yaml`, hostname `voice-garage`, IP `192.168.11.229`, friendly name `Voice Garage`.

---

## Related references

- `docs/decisions/003-voice-pipeline.md` — pipeline choice rationale
- `docs/current-state.md` — voice satellites in-flight section
- `docs/device-inventory.md` — physical inventory (TBD; populate as units deploy)
- `esphome/voice-<location>.yaml` — actual firmware configs
