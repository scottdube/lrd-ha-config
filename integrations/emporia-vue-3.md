# Emporia Vue 3

Whole-home power monitoring hardware. Two units total — one per panel (Panel A + Panel B). Initial install on stock Emporia cloud firmware; migration to ESPHome (`emporia-vue-local` external component) gated on a successful UART flash. See ADR-009 for the hardware decision and `energy/` sub-project for circuit-level planning and install checklists.

---

## Stack

- **Device:** Emporia Vue 3 (Gen 3, model EMV3A). 16× 50A branch CTs + 2× 200A mains CTs + antenna, all bundled. Phoenix-style plugs on Gen 3 (vs 2.5mm/3.5mm on Gen 2 — cuttable lead-length).
- **MCU:** ESP32 (classic, dual-core). `board: esp32dev` per digiblur's reference ESPHome config. Not ESP32-S3.
- **HA integration (cloud path, never used here):** [`emporia_vue` HACS](https://github.com/magicalyak/emporia_vue) is the cloud-API option for stock-firmware devices. ADR-009 considered it as the initial path but Scott went straight from stock cloud (Emporia web/mobile app only) to ESPHome — the HACS integration was never installed in HA, so there's no cleanup task associated with the cloud→ESPHome transition.
- **HA integration (ESPHome path, planned):** External component `github://emporia-vue-local/esphome@dev` per Discord guidance 2026-05-02 (resolves the ESPHome 2026.4.0 incompatibility that was blocking the `main` branch). Native ESPHome API after flash — fully local, no Emporia account dependency.

---

## Current deployment

| Panel | Unit | Firmware | Mains | Branch CTs wired | Status |
|---|---|---|---|---|---|
| A | Unit #2 (Vue Gen 3, MAC `94:54:C5:6F:41:4C`) | **ESPHome (emporia-vue-panel-a.yaml), 16/16 branch CTs** | Both legs, 200A | 16/16 wired + walk-flip verified (2026-05-14) | **Complete + verified on ESPHome.** Reflashed from cloud 2026-05-12, full locality remap applied (Vue rotated 180° from Panel B, antenna LEFT), all 16 walk-flip tests confirmed 2026-05-14. All six 240V circuits (Pool Subpanel, Water Heater, Air #2 Handler, Air #1 Condenser, Mini Split, Wall Oven) reading correctly with `multiply: 2` filter. Σ(branches) within ±1% of mains, Unmonitored Power = 0 W. L1 voltage 122.2 V, L2 voltage 121.5 V, L2 Phase Angle 180°, frequency 60.2 Hz. Default `calibration: 0.01925` left untuned (L2 ~1.4% low — defer tuning). |
| B | Unit #1 (Vue Gen 3, MAC `94:54:C5:6E:6E:38`) | **ESPHome (emporia-vue-panel-b.yaml), 16/16 branch CTs** | Both legs, 200A | 16/16 wired (12/16 walk-flipped 2026-05-12, 4 pending natural exercise) | **Complete on ESPHome 2026-05-12 evening.** IP 192.168.11.216 on IoT VLAN, RSSI −30 dB. Calibration validated within ±0.33% of multimeter. L2 Phase Angle 180° (correct split-phase). All 16 branch CTs reporting; sum-of-branches matches Total Power within 1 W (Unmonitored Power 29.1 W instantaneous = expected baseline from Whirlpool standby + smokes + Spare slot). All four 240V circuits (slots 1, 2, 9, 10) reading correctly with `multiply: 2` filter. Pending walk-flip: slots 3 (Washer), 13 (Master Bath GFI), 14 (Garage Dedicated GFI), 16 (Summer Kitchen #2) — all reading small non-zero values, not failures, just unexercised loads. |

**Bench bring-up notes (2026-05-12):** Boot log clean. Verified the Vue 3-specific config (variant: vue3, sda 5/scl 18 with strapping warning ignored, calibration 0.01925) initializes without I2C errors. Bench-only artifacts to ignore: L1 Frequency reads `inf Hz` (no voltage zero-crossings), L2 Phase Angle reads `nan` (no reference), L2 Power reads ~4.7 MW (ADC noise floor × calibration on unconnected phase). All resolve to sane values once 240V is applied at the panel.

**Chip confirmed (2026-05-12):** ESP32-D0WD-V3 rev v3.1, 40 MHz crystal, classic dual-core + LP core, 240 MHz, Vref calibration in eFuse. Validates `board: esp32dev` in the ESPHome YAML (NOT esp32s3). esptool v5.2.0 on macOS, HJHYUL CP2102 adapter at `/dev/cu.usbserial-0001`, baud 115200 for handshake. Flash chip: 8 MB SPI (manufacturer 0xA1, device 0x4017, 3.3V strapping).

**Stock firmware backup (2026-05-12):** Two independent full-flash reads, MD5 matched across both → backup is canonical.

- File: `~/Documents/Claude/Projects/home-assistant/emporia_vue3_unit1_9454C56E6E38_stock_backup_001.bin` (paired with `_002.bin`)
- Size: 8,388,608 bytes (exact 8 MB)
- MD5: `dc3ef5c186b5338f261bb1bfeefb85f0`
- SHA-256: `5719873286c44dd5081a8a331dfbfc67c93c7789ef3b683f97219d0152013d46` (verified on `_001.bin` 2026-05-12; `_002.bin` is byte-identical per MD5 match, so same SHA-256)
- Read baud: 230400 (115200 handshake → 230400 transfer, ~6.5 min per read)
- Restore command (if ever needed): `esptool --port /dev/cu.usbserial-0001 --baud 230400 write-flash --flash-size detect 0x0 <backup.bin>` with IO0 grounded during power-up.

Swap plan: flash Unit #1 (bench) with ESPHome. If successful, swap boards in Panel A — CTs stay in place, only the Vue board moves. The Panel A board pulled (cloud firmware, MAC TBD on retrieval) then either stays on cloud as redundant fallback or gets flashed in turn and goes into Panel B.

---

## ESPHome YAML — Vue 3 specifics (verified 2026-05-12 from upstream)

Several settings differ from Vue 2 and from older blog-post examples (including digiblur's 2024 reference). The current canonical Vue 3 config per [emporia-vue-local docs](https://emporia-vue-local.github.io/docs/tutorial/configuration/) and [Discussion #367](https://github.com/emporia-vue-local/esphome/discussions/367):

| Item | Vue 2 | Vue 3 (canonical) |
|---|---|---|
| `external_components source` | `github://emporia-vue-local/esphome@dev` | same |
| `variant` | `vue2` | **`vue3`** |
| `i2c sda` | 21 | **5** (with `ignore_strapping_warning: true`) |
| `i2c scl` | 22 | **18** |
| `calibration` starting point | 0.022 | **0.01925** |
| Status LED pin | 23 | **2** (strapping warning), plus optional `ethernet_led` on GPIO 4 |
| CT filter convention | `*pos` | **`*neg`** for branch CTs (Vue 3 measures opposite polarity by default) |

Pre-existing local secrets reference different keys than upstream examples — match your `secrets.yaml`:
- `key: !secret api_encryption_key` (upstream example uses `api_key`)
- `password: !secret ota_password` (upstream example uses `ota_key`)

## First-flash YAML

`esphome/emporia-vue-panel-b.yaml` — **mains-only** for the first flash. Validates toolchain + Wi-Fi + HA integration. Branch CTs added incrementally via OTA after first boot. No `cir1`..`cir16` defined yet — keeps the initial cycle short and removes one whole class of failure modes for the first OTA validation.

## Flash workflow — first time (BDM still attached)

1. **Push the YAML to the repo + pull on NUC** so the ESPHome dashboard sees the new config.
2. **ESPHome dashboard** (HA → Apps → ESPHome) → find `emporiavue-panel-b` → **Install** → **Manual download** → choose **Modern format (.factory.bin)**. Save to Mac.
3. **Put Vue in bootloader** (IO0 to GND, power-cycle via 3.3V toggle).
4. **Erase flash first** (recommended for clean transition off stock):
   ```
   esptool --port /dev/cu.usbserial-0001 --baud 230400 erase-flash
   ```
5. **Write the firmware** (factory.bin starts at 0x0):
   ```
   esptool --port /dev/cu.usbserial-0001 --baud 230400 write-flash --flash-size detect 0x0 ~/Downloads/emporiavue-panel-b.factory.bin
   ```
6. Power-cycle without IO0 grounded. Vue should boot ESPHome, connect to IoT VLAN Wi-Fi, and appear in HA as `emporiavue-panel-b`.

## Flash workflow — OTA (after first flash)

Subsequent updates go through the ESPHome dashboard's "Install → Wirelessly" path — no BDM, no esptool. The pattern for adding branch CTs:

1. Add a `ct_clamps` block for the next slot to the YAML, plus its `copy` + `total_daily_energy` sensors.
2. Push + pull on NUC.
3. ESPHome dashboard → Install → Wirelessly → wait for compile + upload + reboot (~1 min).
4. Verify the new entity appears in HA and reads sensibly.
5. Walk-flip if needed.
6. Repeat for the next slot.

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

Confirmed on 2026-05-11 attempt #1 with Unit #1 via 3D-printed pogo jig + HJHYUL CP2102 adapter. **Resolved 2026-05-12 with BDM frame** — chip-id succeeded first try after BDM swap, confirming the 3D-printed pogo jig was the contact-reliability bottleneck. Suspect order:

- **Intermittent pad contact** through the 3D-printed jig — pogo pins not landing reliably on the small Vue 3 pads. **Confirmed root cause** (BDM frame fix worked first try).
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
