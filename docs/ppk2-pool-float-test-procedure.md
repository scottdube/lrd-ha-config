# PPK2 Bench Test Procedure — Pool Float Power Characterization

Step-by-step procedure for using the Nordic Power Profiler Kit II (PPK2)
to measure the XIAO ESP32-C6's actual sleep and wake current draw, in
both real-deployment configuration (supply at BAT) and isolated-ESP32
configuration (supply at 3V3 pad).

Output of this procedure: four current-vs-time captures (.ppk2 files)
plus exported CSV data, sufficient to compute an exact battery-life
budget at any chosen sleep cadence.

Audience: first-time PPK2 user. Workflow runs on MacBook with the
XIAO ESP32-C6 pool-float firmware (`esphome/pool-water-temp-external.yaml`)
already installed.

---

## Section 1 — Required materials

Hardware:
- Nordic PPK2 (NRF-PPK2)
- USB-C to Micro-USB cable (PPK2 uses Micro-USB-B on the host side)
- XIAO ESP32-C6, with the pool-float firmware already flashed
- Solderless breadboard (or some way to stably hold the XIAO)
- 4–6 male-to-male jumper wires (included with PPK2; pull a few extras
  from your bench if you have them)
- The XIAO ESP32-C6 must NOT be connected to USB-C during measurement
- 2× lithium primary AA cells DISCONNECTED for this procedure (PPK2
  supplies power in source mode; batteries are not used at the bench)

Software (install on MacBook BEFORE bench session):
- nRF Connect for Desktop (from nordicsemi.com — universal binary,
  installs to /Applications)
- Power Profiler app (installed from inside nRF Connect for Desktop
  launcher)

Reference info to have on hand:
- The XIAO ESP32-C6 pinout (BAT+, BAT−, GND, 3V3 pad locations on the
  bottom side of the board)
- The firmware's current sleep cadence (`sleep_duration: 10min` per
  current YAML — for this test it makes sense to temporarily shorten
  to e.g. 2 min so you don't wait 10 min between wakes)

---

## Section 2 — Pre-flight (do this first)

Step 2.1 — Verify software is installed:

On MacBook, open Applications → nRF Connect for Desktop. The launcher
window appears with a list of apps. Confirm that **Power Profiler** is
in the installed list. If it's not, click Install on its row.

Step 2.2 — Optionally shorten the sleep duration in the firmware for
faster iteration. With a 10-minute sleep, you wait 10 minutes between
each wake capture. Editing YAML is the cleanest path:

```
cd ~/code/home-assistant
```
(MacBook terminal — replace `sleep_duration: 10min` with `sleep_duration: 2min`
in `esphome/pool-water-temp-external.yaml`, commit, push)

```
git add esphome/pool-water-temp-external.yaml
git commit -m "test: temporary 2-min sleep for PPK2 bench characterization"
git push
```

Then on SCS:

```
cd /config
git pull
```

Flash the XIAO via ESPHome dashboard at this point. Remember to revert
the cadence to production value (10/15/30/45/60 min, whatever you decide
post-measurement) before redeploying the float.

Step 2.3 — Ensure the XIAO is UNPLUGGED from USB-C. PPK2 in source mode
will be the only power source. Two power sources at once (USB + PPK2)
will at best confuse measurements and at worst back-feed the onboard
SGM6029 buck-boost.

---

## Section 3 — Bench wiring (Capture set A — supply at BAT)

The XIAO ESP32-C6 has these pads on the bottom side:
- BAT+ (battery positive)
- BAT− (battery negative / GND)
- 3V3 (regulator output rail)

The PPK2 has these terminals on the side connector strip:
- VIN (used in ampere meter mode; we are NOT using this mode)
- VOUT (used in source mode — PPK2 supplies power out of this pin)
- GND
- A 10-pin logic-analyzer header (optional, ignored for now)

Step 3.1 — Wire connections for Capture set A:

```
PPK2 VOUT ─────── XIAO BAT+ pad
PPK2 GND  ─────── XIAO BAT− pad (or GND pad)
```

Use two of the included jumper wires. Make sure the jumpers are seated
firmly in the PPK2 header strip; loose connections cause measurement
noise.

Step 3.2 — Visual check before powering:
- VOUT goes to BAT+, not to 3V3 (yet — that's capture set B)
- GND is connected; no floating ground
- XIAO USB-C port is unplugged
- No batteries are physically installed

---

## Section 4 — Power up PPK2 and launch software

Step 4.1 — On MacBook, plug the USB-C-to-Micro-USB cable into the PPK2
(Micro-USB end) and into a MacBook port (USB-C end). PPK2 LEDs should
illuminate (a power LED on the board itself).

Step 4.2 — In nRF Connect for Desktop launcher, click Open on Power
Profiler. The Power Profiler window opens with an empty trace area on
the right and a control panel on the left.

Step 4.3 — In the SELECT DEVICE dropdown (top-left of window), pick
the PPK2 (it will be listed as PPK2 with a serial number). The app
connects; you should see voltage and current readouts go from grayed-out
to active.

Step 4.4 — Configure source mode:
- In the control panel, find MODE
- Select **Source meter** (NOT Ampere meter)
- Set supply voltage to **3300 mV** (3.3V)
- Leave Sample rate at the default 100 kS/s for now
- Do NOT enable the output yet

Step 4.5 — Enable output:
- Click the **Enable power output** toggle (or "Output on" button —
  exact label depends on the app version)
- PPK2 will start supplying 3.3V to the XIAO
- XIAO red LED behavior: per ADR-015 bench notes, CHG1 LED is OFF when
  no battery and no USB simultaneously present. With PPK2 supplying at
  BAT+ and no USB plugged in, expect CHG1 OFF.
- The XIAO should boot — listen for ESPHome's WiFi associate cycle
  (won't be audible, but the current trace will show the wake spike)

If the XIAO does NOT boot (no current spike on the trace), check:
- VOUT actually wired to BAT+ (not to BAT− or to a GPIO)
- Output is enabled (button toggled)
- Voltage set to 3.3V (not 0V)

---

## Section 5 — Capture A1: sleep current at BAT, 3.3V supply

Goal: steady-state current draw during deep_sleep, 60+ continuous seconds
of stable data.

Step 5.1 — Wait for the XIAO to finish its wake cycle. With production
firmware, this is roughly:
- Boot: ~1 sec
- WiFi associate + API connect: ~5–10 sec
- Publish: ~1 sec
- Sleep entry: instant

After about 15 seconds from output-enable, the current should drop to
the sleep level (low µA range). The trace shows a steep cliff down.

Step 5.2 — Wait an ADDITIONAL 30 seconds after the cliff. This is the
ESP32 post-boot housekeeping window — per Nordic DevZone forum posts on
ESP32-H2 PPK2 measurements, sleep current is not stable until 30+ sec
after entry. Don't trust the first 30 sec of any sleep trace.

Step 5.3 — Start recording. In the Power Profiler app, find the START
button (typically labeled with a play/record icon). Begin recording at
least 60 seconds of post-stabilization sleep data.

Step 5.4 — While recording, use the cursor markers to drop two markers
inside the steady-state region:
- Click in the trace area to drop marker 1
- Move cursor, click again to drop marker 2
- The app displays AVG, MIN, MAX between markers

The AVG reading between markers in the sleep region is your **measured
sleep current at BAT**.

Step 5.5 — Save the capture:
- File menu → Save As → name it `ppk2-A1-bat-sleep-2026-05-26.ppk2`
  (or whatever date)
- The .ppk2 file is the native reloadable format; preserves full
  waveform data for later analysis

Step 5.6 — Export to CSV (optional but recommended for archive):
- File → Export → CSV
- Choose "Selection" if you have markers; otherwise "All"
- Save to the same directory as the .ppk2 file
- CSV is timestamp + current samples, openable in Excel/Sheets

---

## Section 6 — Capture A2: full wake cycle at BAT, 3.3V supply

Goal: full current-vs-time profile of one wake → publish → sleep cycle.

Step 6.1 — Stop the current recording (Stop button). You can keep the
A1 file open or close it; the next capture will be a new window of data.

Step 6.2 — Start a fresh recording. The trace area should now be
clearing/scrolling fresh data. The device is in sleep — current is low.

Step 6.3 — Wait for the next scheduled wake. With your temporary
2-min cadence, this happens within 2 minutes. With 10-min cadence,
you wait up to 10 min — or you can force a reset (press the reset
button on the XIAO, briefly disconnect/reconnect PPK2 output, etc.).

Step 6.4 — When the wake cycle begins, you'll see:
- Sharp spike (~200+ mA) as ESP32 boots and WiFi powers up
- Sustained elevated current (~70–100 mA) during WiFi associate
- Brief lower plateau (~50–80 mA) during API connect + publish
- Sharp drop (back to sleep) when script completes

The whole cycle is 6–40 seconds depending on whether WiFi connects fast
or hits the timeout.

Step 6.5 — Let the recording capture an additional 10+ seconds after
sleep entry to see the cliff and ensure post-sleep stabilization.

Step 6.6 — Drop markers to bracket the full wake cycle from just before
the boot spike to ~30 sec into sleep. Read:
- AVG current across the wake portion (use markers to isolate just the
  active wake, not the sleep tail)
- CHARGE (mC) across the full cycle — this is the per-cycle energy in
  millicoulombs; divide by 3.6 to get mA·h

Step 6.7 — Save as `ppk2-A2-bat-wake-2026-05-26.ppk2` and optionally
export CSV.

---

## Section 7 — Re-wire for Capture set B (supply at 3V3 pad)

Step 7.1 — Disable PPK2 output (toggle off the Enable power output
button). XIAO loses power.

Step 7.2 — Disconnect VOUT jumper from BAT+ pad. Re-route it to the
**3V3 pad** on the XIAO bottom side. GND wire stays where it is.

```
PPK2 VOUT ─────── XIAO 3V3 pad   (changed)
PPK2 GND  ─────── XIAO BAT− pad  (unchanged)
```

Step 7.3 — Visual re-check: VOUT is on the 3V3 pad (NOT the BAT+ pad).
Hitting the wrong pin won't damage the board — both are 3.3V rails —
but the measurement won't be useful.

Step 7.4 — Re-enable PPK2 output at 3.3V. XIAO should boot identically
to before; the regulator (SGM6029) is bypassed but the ESP32 sees the
same supply voltage.

---

## Section 8 — Capture B1: sleep current at 3V3, 3.3V supply

Repeat Section 5 with the new wiring. Save as
`ppk2-B1-3v3-sleep-2026-05-26.ppk2`.

The B1 reading should be **lower than A1** by the SGM6029 quiescent
current (expected ~8–10 µA, inferred from the SGM6029 datasheet and the
schematic-derived model; actual figure is what we're measuring).

If B1 ≈ A1 (no meaningful difference), the regulator quiescent is
unexpectedly low — or something is mis-wired. Worth a re-check.

If A1 − B1 >> 10 µA (say, 30+ µA), the regulator quiescent is higher
than expected — interesting data point but doesn't change the strategy.

---

## Section 9 — Capture B2: full wake cycle at 3V3, 3.3V supply

Repeat Section 6 with the new wiring. Save as
`ppk2-B2-3v3-wake-2026-05-26.ppk2`.

The B2 wake-cycle CHARGE (mC) should be **lower than A2** by the SGM6029
conduction loss during wake — roughly 3–8% of throughput, depending on
load. This is small but real, and it's the kind of data you can only
get with a proper power profiler.

---

## Section 10 — Analysis and battery-life recalculation

Step 10.1 — Open each .ppk2 file in turn, read the AVG current values
(via markers) and record in a worksheet:

| Capture | What it measures | Typical expected | Your measured |
|---|---|---|---|
| A1 sleep BAT | Real-deployment sleep current | ~15 µA | ___ µA |
| A2 wake BAT | Real-deployment wake (mC/cycle) | ~1.4 mC | ___ mC |
| B1 sleep 3V3 | ESP32-only sleep | ~5–7 µA | ___ µA |
| B2 wake 3V3 | ESP32-only wake (mC/cycle) | ~1.3 mC | ___ mC |

(Reference values are inferred from the SGM6029 datasheet + ESP32-C6
datasheet + earlier rough budgets. Yours will be exact.)

Step 10.2 — Compute decomposed quiescents:
- SGM6029 sleep quiescent = A1 − B1 µA
- SGM6029 wake conduction loss = A2 − B2 mC/cycle

Step 10.3 — Plug A1 sleep current and A2 wake CHARGE into the
battery-life formula:

```
Per-cycle energy (mA·h) = A2 charge (mC) / 3.6
Per-cycle sleep energy (mA·h) = A1 (µA) × (cadence_sec − wake_sec) / 3,600,000
Total per-cycle = wake + sleep
Daily mA·h = total per-cycle × (86400 / cadence_sec)
Runtime (days) = battery capacity (mA·h) / daily mA·h
```

Reuse the cadence-vs-runtime table from
`docs/pool-float-wifi-baseline-2026-05-24.md` with the new measured
inputs replacing the estimates. Decide on production cadence with real
margin numbers.

---

## Section 11 — File output: what gets saved, how

Saved files from a session:

`.ppk2` (native format) — Full waveform data + metadata. Reloadable in
Power Profiler later. Use this as the archive format. Save BEFORE
deselecting the device or unplugging PPK2 — there's a known footgun
where re-selecting the device wipes unsaved samples.

`.csv` (exported) — Plain-text timestamp/current samples. Openable in
Excel, Google Sheets, Python pandas, etc. Choose "Selection" to export
just a bracketed region, or "All" for the entire trace. CSV is large
(megabytes per minute of recording at 100 kS/s).

Screenshots (manual) — The Power Profiler window does NOT have a
built-in screenshot button as of the version in current nRF Connect.
For visual records of the trace, use macOS Cmd+Shift+4 → drag-select
the trace area, or Cmd+Shift+5 for the full window. Saved to Desktop
by default.

Workflow recommendation:
- Save each capture as .ppk2 immediately after recording
- Export the same capture's marker-selection region to CSV in the same
  folder
- Cmd+Shift+4 a screenshot of the trace with markers visible for the
  printable record

After session, all files live under `~/Documents/ppk2-pool-float/`
(or wherever you save them). Recommend putting copies into
`docs/ppk2-captures-2026-05-26/` in the home-assistant repo so they're
version-controlled with the project.

---

## Section 12 — Common gotchas

**XIAO doesn't boot when output enabled.** Check VOUT is wired to BAT+
(or 3V3 in capture set B), not to a GPIO. Check Source mode is selected,
not Ampere mode. Check voltage is 3.3V, not 0V.

**Sleep current reads high (>50 µA).** Wait an additional 30+ seconds
after sleep entry — ESP32 post-boot housekeeping. If still high after
60 sec, check for any USB cable accidentally still connected to the
XIAO. Confirm firmware actually entered deep_sleep (the YAML's
`deep_sleep.enter` was called, not blocked by OTA mode flag).

**OTA mode flag prevents sleep.** The pool float firmware has an
`input_boolean.pool_float_ota_mode` gate — if it's ON, the device
won't sleep. Before bench session, set this OFF in HA UI. (Or unplug
WiFi by disabling the network entirely on the bench, which forces
the device to time out the API connection and proceed to sleep anyway.)

**Current spikes peg the scale.** PPK2 auto-ranges; sometimes manual
intervention helps. Try setting the range manually if the trace clips.

**Markers feel finicky.** Click-drag in the trace area to select a
region; the AVG/MIN/MAX/CHARGE numbers in the side panel update live.
Cmd+click on the trace to drop a single marker for delta measurements.

**Long captures fill the buffer.** Default buffer is finite. For
multi-minute captures (like watching multiple wake cycles), enable
"unlimited capture" or stream-to-file mode in the advanced sidebar
(Ctrl+Alt+Shift+A on Linux/Win; on Mac it may be Cmd+Option+Shift+A —
try both).

**Re-selecting the device wipes data.** If you Stop and Disconnect, your
unsaved samples are wiped. Always Save before disconnecting.

---

## Section 13 — Post-session cleanup

After capturing all four files:

Step 13.1 — Disable PPK2 output, disconnect jumpers from XIAO, unplug
PPK2 USB.

Step 13.2 — If you temporarily edited the YAML to a 2-min sleep cadence
for testing, revert it to the production cadence you chose based on the
measurements:

On MacBook:
```
cd ~/code/home-assistant
```
(edit `esphome/pool-water-temp-external.yaml` to your chosen production
cadence)

```
git add esphome/pool-water-temp-external.yaml
git commit -m "ADR-015: set sleep_duration to <X>min based on PPK2 measurements"
git push
```

On SCS:
```
cd /config
git pull
```

Flash the XIAO via ESPHome dashboard.

Step 13.3 — Reinstall the float in the pool with the new cadence.

Step 13.4 — Commit the .ppk2 captures and CSV exports to the repo:

```
cd ~/code/home-assistant
mkdir -p docs/ppk2-captures-2026-05-26
cp ~/Documents/ppk2-pool-float/*.ppk2 docs/ppk2-captures-2026-05-26/
cp ~/Documents/ppk2-pool-float/*.csv docs/ppk2-captures-2026-05-26/
git add docs/ppk2-captures-2026-05-26/
git commit -m "ADR-015: PPK2 bench captures from 2026-05-26 session"
git push
```

Update `docs/pool-float-wifi-baseline-2026-05-24.md` (or create a new
file `docs/pool-float-power-baseline-2026-05-26.md`) with the measured
values replacing the prior estimates.

---

## Section 14 — Quick reference card (single page, can be printed
separately and taken to the bench)

```
WIRING — Capture set A (real deployment)
  PPK2 VOUT  →  XIAO BAT+
  PPK2 GND   →  XIAO BAT−
  XIAO USB-C: unplugged

WIRING — Capture set B (ESP32-isolated)
  PPK2 VOUT  →  XIAO 3V3 pad
  PPK2 GND   →  XIAO BAT−
  XIAO USB-C: unplugged

PPK2 MODE: Source meter
SUPPLY:    3300 mV
SAMPLE:    100 kS/s
OUTPUT:    Enable after wiring verified

CAPTURE SEQUENCE:
  A1 = BAT  + sleep, 60+ sec after stabilization
  A2 = BAT  + full wake cycle
  B1 = 3V3  + sleep, 60+ sec after stabilization
  B2 = 3V3  + full wake cycle

SAVE: .ppk2 immediately after each, then CSV export
NEVER deselect device before saving.

WAIT 30 SEC after sleep entry before trusting current reading.
```
