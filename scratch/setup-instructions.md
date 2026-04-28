# Setup Instructions

How to land this scaffolding into a Cowork project. **Read once, throw away when setup is done** — this doc isn't part of the long-term project.

---

## What you're starting with

A folder of starter docs:

```
home-assistant/
├── README.md
├── docs/
│   ├── ha-chat-index.md
│   ├── current-state.md
│   ├── device-inventory.md          # has gaps to fill
│   └── decisions/
│       ├── 001-omnilogic-local-vs-cloud.md
│       ├── 002-heater-set-and-hold.md
│       ├── 003-voice-pipeline.md
│       └── 004-waterfall-valve-domain.md
├── integrations/
│   └── omnilogic.md                 # template for the others
├── blueprints/                      # empty — populate from /config
├── automations/                     # empty — populate from /config
├── packages/                        # empty — populate from /config
├── voice-satellites/                # empty — populate from ESPHome
├── dashboards/                      # empty — populate from /config
└── scratch/                         # empty
```

---

## Step 1: Decide the repo strategy

**Inference:** Two reasonable options here. Pick one before starting.

### Option A — Use this scaffolding alongside `lrd-ha-config`
Your existing `lrd-ha-config` repo is the live HA configuration (mirror of `/config`). The new `home-assistant` project becomes a **superset** that includes the live config plus the docs/decisions/notes around it.

- Pros: one home, everything together
- Cons: bigger repo, mixes "live config" with "documentation about config"

### Option B — Two repos
Keep `lrd-ha-config` as the live config mirror. Make a separate `home-assistant-docs` repo for the documentation/decisions/index work. Connect both to Cowork.

- Pros: cleaner separation, smaller live-config repo
- Cons: two places to look

**My suggestion:** Option A. Cowork works best with one connected source per project, and you've explicitly said you want one home. Drop the doc structure into `lrd-ha-config` as a `docs/` and `decisions/` overlay on top of what's already there.

---

## Step 2: Land the files in your repo

If you're going with Option A:

```bash
# In Studio Code Server terminal, on the NUC
cd /config

# These directories will be created if they don't exist; merged if they do
# Copy from /mnt/user-data/outputs (download to your Mac first, then upload via SCS)
# Or pull the files into /config directly via the SCS file editor

# Once files are in /config:
git status                            # see what's new
git add docs/ integrations/ scratch/  # add new directory trees
git add README.md                     # if you don't have one yet (or update existing)
git commit -m "docs: add project structure, ADRs, integration notes"
git push origin main
```

**What about the empty folders?** They have no files yet so git won't track them. Either:
- Add a `.gitkeep` to each: `touch blueprints/.gitkeep automations/.gitkeep voice-satellites/.gitkeep`
- Or just populate them as you go (recommended)

If the live config already has a `blueprints/` or `automations/` folder structure, the new structure should mirror what's already there — don't create parallel directories.

---

## Step 3: Connect to Cowork

In Cowork:

1. Create a new project named `home-assistant`
2. Connect the `scottdube/lrd-ha-config` GitHub repo
3. Pin these files to the project (or add as starting context):
   - `README.md`
   - `docs/current-state.md`
   - `docs/ha-chat-index.md`
   - `docs/device-inventory.md`

These are the files Cowork should always have in mind. Everything else is reachable but doesn't need to be foreground.

---

## Step 4: Fill the gaps

The skeleton has placeholders. Walk through these in order:

### 4a. Device inventory (highest value, biggest gap)
Open `docs/device-inventory.md` and fill in everything marked `?`. This will take 30-60 minutes but pays back forever. Pull node IDs from Z-Wave JS UI, model numbers from the devices, locations from your head.

### 4b. Live config files
Copy current versions of:
- Blueprints from `/config/blueprints/automation/LRD/` → `blueprints/`
- `automations.yaml` → `automations/`
- Packages from `/config/packages/` → `packages/`
- Dashboards from `/config/dashboards/` (or wherever they live) → `dashboards/`

If `lrd-ha-config` is already mirroring `/config`, this is already done — just verify the structure matches the README.

### 4c. Voice satellite ESPHome configs
Export the `voice-garage` config from ESPHome dashboard → save as `voice-satellites/esphome/voice-garage.yaml`.

### 4d. Integration notes (one per integration)
Use `integrations/omnilogic.md` as a template. Create:
- `integrations/midea-ac-lan.md`
- `integrations/zwave-js.md`
- `integrations/weatherflow.md`
- `integrations/unifi-protect.md`
- `integrations/nabu-casa.md`
- ...

Each one captures: which version/fork, how it's configured, known issues, your specific quirks.

---

## Step 5: Establish the working rhythm

Going forward, when you start a Cowork session about HA:

1. Cowork should already have `current-state.md` in context. If it doesn't, paste a link.
2. After any significant decision, update `current-state.md`. Keep "in flight" honest — move things to "recently completed" when done.
3. After any architectural choice, write a 1-page ADR. Don't be formal. The point is "future-me knows why this is the way it is."
4. After any new integration or major version bump, update the relevant `integrations/<name>.md`.

This is overhead. But based on your chat history, you're doing this informally already (per-blueprint changelogs, the network-docs project's ADRs). Formalizing it just means future-you can find the answers.

---

## Step 6: Decide on Cowork connectors beyond GitHub

GitHub is the must-have. Optional adds:

- **Google Drive** — if HA-related screenshots, network diagrams, device manuals live there
- **Granola** — only if you discuss HA in meetings (probably not)
- **Box** — same as Drive

Add them only if there's actual content in those services that's HA-relevant. Don't add for completeness.

---

## When to delete this file

When you've:
- Got the repo connected to Cowork
- Filled in `device-inventory.md`
- Imported live configs from `/config`
- Created at least 3 integration notes

…then this file has done its job. Delete it from `scratch/` (or wherever you put it) and don't look back.
