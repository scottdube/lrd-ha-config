# Emporia Vue 3

Whole-home power monitoring hardware. Two units total — one per panel (Panel A + Panel B). Initial install on stock Emporia cloud firmware; migration to ESPHome (`emporia-vue-local` external component) gated on a successful UART flash. See ADR-009 for the hardware decision and `energy/` sub-project for circuit-level planning and install checklists.

---

## Stack

- **Device:** Emporia Vue 3 (Gen 3, model EMV3A). 16× 50A branch CTs + 2× 200A mains CTs + antenna, all bundled. Phoenix-style plugs on Gen 3 (vs 2.5mm/3.5mm on Gen 2 — cuttable lead-length).
- **MCU:** ESP32 (classic, dual-core). `board: esp32dev` per digiblur's reference ESPHome config. Not ESP32-S3.
- **HA integration (cloud path, current):** [`emporia_vue` HACS](https://github.com/magicalyak/emporia_vue), cloud-mediated via Emporia's API. Mature and well-documented.
- **HA integration (ESPHome path, planned):** External component `github://emporia-vue-local/esphome@dev` per Discord guidance 2026-05-02 (resolves the ESPHome 2026.4.0 incompatibility that was blocking the `main` branch). Native ESPHome API after flash — fully local, no Emporia account dependency.

---

## Current deployment (2026-05-11)

| Panel | Unit | Firmware | Mains | Branch CTs wired | Status |
|---|---|---|---|---|---|
| A | Unit #2 (Vue Gen 3) | Emporia cloud | Both legs, 200A | Slot 7 (Pool Subpanel) — others pending this afternoon | Active, reading via cloud |
| B | Unit #1 (Vue Gen 3) | Not flashed; bench | — | — | Held back — flash attempt blocked, BDM frame on order |

Swap plan: flash Unit #1 on the bench once BDM frame arrives. If successful, swap boards in Panel A (CTs stay in place — only the Vue board moves). The board pulled from Panel A then gets flashed (or stays on cloud as a redundant fallback) and goes into Panel B.

---

## Flashing — workflow for macOS

### Install esptool

```
brew install esptool
```

`pipx install esptool` or a venv install both work as alternatives. Verify:

```
esptool version
```

### Identify USB-TTL serial port

With nothing plugged in:

```
ls /dev/cu.*
```

Plug in the USB-TTL adapter, run again. On Scott's MacBook the HJHYUL CP2102 adapter (Amazon B0FJRTL572) enumerates as `/dev/cu.usbserial-0001`. Always use `cu.*`, never `tty.*`, on macOS.

### Wiring — the Vue-specific gotcha

Per digiblur's wiring map for Gen 3 (NOT crossed like normal ESP32 flashes):

| USB-TTL adapter | Vue 3 pad |
|---|---|
| 3.3V | 3.3V |
| GND | GND |
| TXD | TXD |
| RXD | RXD |
| RST | (leave disconnected — this is the CP2102's own reset, not the target's) |

### Bootloader entry sequence

The Vue has no auto-reset circuit (no DTR/RTS-driven EN/IO0 toggle), so esptool's auto-reset trick does not work. Must be manual:

1. Jumper IO0 to GND **first**.
2. Apply 3.3V to the Vue **while IO0 is still grounded** (either plug in 3.3V last, or toggle a power switch).
3. Run the esptool command immediately after.
4. IO0 can be released after the chip is in bootloader mode.

### Verify connection

```
esptool --port /dev/cu.usbserial-0001 --baud 115200 chip-id
```

Expected: `Chip is ESP32-...` + MAC address. If `Failed to connect to Espressif device: No serial data received`, see Known failure modes below.

### Flash ESPHome firmware (planned, after `esptool chip-id` is reliable)

Build the firmware with the ESPHome dashboard or CLI using the YAML at `esphome/emporia-vue-panel-a.yaml` (TBD — not yet created; will be templated from digiblur's reference config + ADR-009 Discord guidance), then:

```
esptool --port /dev/cu.usbserial-0001 --baud 460800 write-flash --flash-size detect 0x0 emporiavue3.bin
```

Modern `esptool` accepts hyphens (`write-flash`, `--flash-size`). The older `esptool.py` syntax with underscores still parses but is deprecated.

---

## Known failure modes

### 1. "No serial data received" — most common

Confirmed on 2026-05-11 attempt #1 with Unit #1 via 3D-printed pogo jig + HJHYUL CP2102 adapter. Suspect order:

- **Intermittent pad contact** through the 3D-printed jig — pogo pins not landing reliably on the small Vue 3 pads. **Most likely root cause.** Fix: BDM frame (on order 2026-05-11) for rigid, square pin landing.
- **CP2102 internal 3.3V LDO undersized.** The CP2102 internal regulator output is rated nominal (Silicon Labs CP2102 datasheet); ESP32 boot current can exceed this. Workaround: 100–470 µF bulk cap across 3.3V/GND right at the Vue pads, or external 3.3V bench supply with adapter providing only GND/TXD/RXD.
- **Bootloader sequence wrong.** IO0 must be at GND *before* power-up, not after. Re-test the sequence under any failure.
- **RX/TX crossed.** Standard ESP32 wiring crosses them; Vue does not. Easy reflex error.
- **Adapter voltage selector at 5V.** HJHYUL B0FJRTL572 is fixed 3.3V on the VCC pin, but the title implies "compatible with both 3.3V and 5V logic levels." Confirm jumper position if any.

Sanity check before BDM arrives: plug the HJHYUL adapter into a known-good ESP32 dev board (Scott has an ESP32 Dev Module and a Xiao ESP32-C6) and run `chip-id`. Passing on those isolates the Vue contact reliability as the issue. Failing on those points to the adapter or driver.

### 2. Permissions / driver

macOS Sequoia and later ships a built-in CP210x driver. If `/dev/cu.usbserial-0001` enumerates after plugging in, the driver is working. Permission errors would manifest as access denied on the port, not "No serial data received."

### 3. ESPHome 2026.4.0 incompatibility on `main`

Historical: the `emporia-vue-local/esphome` `main` branch was broken by ESPHome 2026.4.0. Resolution per Discord 2026-05-02: use the `@dev` branch as the external_components source. Set the sensor variant explicitly (Vue 2 vs Vue 3) in YAML. Track upstream merge — switch back to `main` once the fix is released.

---

## Hardware inventory for the flash bench

| Item | Notes |
|---|---|
| Vue 3 Unit #1 (target) | Held back from panel install; on bench for flash attempts |
| Vue 3 Unit #2 (Panel A) | Stock cloud firmware; eligible for in-place swap after Unit #1 flash succeeds |
| HJHYUL CP2102 USB-TTL adapter | Amazon B0FJRTL572. CP2102 chipset, 5-pin header (3.3V/RST/TXD/RXD/GND). 3.3V fixed on VCC pin. |
| 3D-printed pogo jig | Used 2026-05-11; suspected source of contact reliability issue |
| BDM frame | Ordered 2026-05-11. Expected use: replace the 3D-printed jig for rigid pin placement on the Vue pads. |
| Macbook + Homebrew esptool | Flashing host. USB-TTL adapter enumerates as `/dev/cu.usbserial-0001`. |

---

## Reference material

- **Decision context:** `docs/decisions/009-whole-home-power-monitoring.md` (ADR-009)
- **Install checklists:** `energy/docs/install-checklist-panel-a.md`, `energy/docs/install-checklist-panel-b.md` — full per-CT circuit assignments and walk-flip protocol
- **Energy sub-project README:** `energy/README.md`
- **digiblur tutorial (companion to the video):** https://digiblur.com/2025/03/14/how-to-esphome-emporia-vue-gen3-esp32-home-assistant/
- **digiblur YouTube video Scott referenced:** https://www.youtube.com/watch?v=Z52y1Gm4VAg
- **emporia-vue-local ESPHome component:** https://github.com/emporia-vue-local/esphome
- **Vue 3 community config thread:** https://github.com/emporia-vue-local/esphome/discussions/264
- **esptool troubleshooting:** https://docs.espressif.com/projects/esptool/en/latest/troubleshooting.html

---

## Past chat references

Inline in this conversation (2026-05-11): esptool install, USB-TTL identification, "No serial data received" troubleshooting, BDM-frame pivot decision. Add chat URL to `docs/ha-chat-index.md` once persisted to claude.ai.
