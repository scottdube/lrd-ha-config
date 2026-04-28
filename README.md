# home-assistant

Home Assistant configuration, automations, integrations, and adjacent maker work for the LRD smart home.

**HA host:** NUC @ 192.168.11.155, IoT VLAN, HA OS 17.2 / Core 2026.4.1
**Network:** UDM SE, WireGuard for remote access, Nabu Casa as backup remote
**Canonical config repo:** [`scottdube/lrd-ha-config`](https://github.com/scottdube/lrd-ha-config) (this repo)
**Public blueprints:** [`scottdube/lrd-ha-blueprints`](https://github.com/scottdube/lrd-ha-blueprints)

---

## What's in this project

This project covers all Home Assistant work — configuration, automations, blueprints, dashboards, and integrations — plus adjacent hardware/maker work that's part of the HA ecosystem (ESP32-S3 voice satellites, custom enclosures).

**What's NOT here:** Network infrastructure (firewalls, VLANs, ADRs about zones, cross-site routing) lives in a separate `network-docs` project. HA is a *consumer* of network policy, not a contributor to it. This project references network decisions (e.g., ADR-008 governing HA NUC placement) but doesn't own them.

---

## Repository structure

This repo IS `/config` on the NUC. Studio Code Server commits and pushes from there directly. The Mac clone (used by Cowork) mirrors via standard pull/push.

```
home-assistant/
├── README.md                    # this file
├── configuration.yaml           # HA root config (entry point)
├── automations.yaml             # all automations
├── scripts.yaml                 # scripts
├── scenes.yaml                  # scenes
├── config/
│   └── templates.yaml           # template sensors (included from configuration.yaml)
├── docs/
│   ├── current-state.md         # active working notes / open threads
│   ├── ha-chat-index.md         # index of past Claude chats by topic
│   ├── device-inventory.md      # hardware inventory and pairing state
│   ├── decisions/               # lightweight ADRs
│   └── reference/               # screenshots, external docs, manuals
├── blueprints/                  # custom blueprints (current versions, see LRD/)
├── packages/                    # HA packages (presence, etc.)
├── integrations/                # per-integration notes (forks, quirks, configs)
├── pool/                        # pool scripts, data schema, future predictive-heating analysis
│   ├── scripts/                 # temp_logger.py invoked via shell_command
│   ├── docs/                    # CSV schema, known-bad ranges
│   └── analysis/                # future notebooks/models
├── voice-satellites/            # ESPHome configs, enclosures, per-unit notes
│   ├── esphome/                 # voice-garage.yaml + future unit configs
│   ├── docs/                    # per-unit build notes
│   └── enclosures/              # CAD pointers / STL exports
├── custom_components/           # HACS-installed integrations (gitignored — large, reinstallable)
├── www/                         # frontend resources / community Lovelace cards (gitignored)
├── tts/                         # TTS audio cache (gitignored)
└── scratch/                     # in-progress / experimental work (e.g., cleanup-plan.md)
```

**Dashboards:** managed in the HA UI (storage-based, in `.storage/`), not as YAML in this repo. `.storage/` is gitignored as runtime state.

**Runtime data files (gitignored):** `pool_temp_log.csv`, `home-assistant.log*`, `*.db*`, etc. See `.gitignore`.

---

## Conventions

**Blueprint versioning.** Blueprints use semver (`v1.8.0`) tracked in the file header changelog. Bump version on every change. Don't reuse versions.

**Blueprint changelog format.** Top of each blueprint file, newest version first:
```yaml
# v1.8.0 - Switch→valve domain migration for waterfall.
# v1.7.0 - Heater set-and-hold logic.
# v1.6.0 - Waterfall independence.
# ...
```

**Decision records (ADRs).** Lightweight format: Context / Decision / Consequences. Numbered sequentially. Don't be formal — capture intent so future-you doesn't re-debate solved problems.

**Integration notes.** One markdown file per integration in `integrations/`. Capture which version/fork, known issues, your specific config, and a link to the upstream repo or HACS page. This is the file you grep at 11pm when something breaks.

**Scratch is not gitignored.** Work-in-progress is committed too — git is the safety net. Promote files out of `scratch/` when they stabilize.

---

## Where to start

If you (or future-you, or Cowork) need to get oriented:

1. **`docs/current-state.md`** — what's in flight right now
2. **`docs/ha-chat-index.md`** — past Claude chats by topic
3. **`docs/device-inventory.md`** — what hardware, paired where
4. **`docs/decisions/`** — why things are the way they are

When something breaks: start with `integrations/<name>.md` for the relevant integration.
