# PPK2 Bench Test — Pool Float C6 — 2026-05-26

Focused procedure for measuring the deployed XIAO ESP32-C6's wake-cycle
energy on the bench, using PPK2 source mode + CSV export + Claude-side
Python analysis. Approximately 60 minutes end-to-end.

Outcome: definitive per-cycle energy and sleep current numbers for the
production cadence decision, recorded in a reproducible CSV for archive.

## Phase 0 — Pre-flight (5 min)

Save the in-progress S3 capture if not already done.

In Power Profiler app: Stop the capture if running. Save / Export →
choose .ppk2 native format → name `s3-baseline-2026-05-25.ppk2` → save
to `~/Documents/ppk2-captures/`. Disconnect PPK2 leads from the S3
DevKitC. Leave PPK2 itself plugged into MacBook.

Confirm float firmware is current. Should be the post-flash YAML with
1-min cadence, DFS + tickless idle, 3-sample median filter on NTC, and
post-connect uptime/wifi instrumentation. No need to flash anything
right now.

## Phase 1 — Float retrieval (5 min)

Retrieve the float from the pool. Dry thoroughly — especially around
the case seal — before opening to prevent water ingress.

## Phase 2 — Bench wiring (15 min)

Open the float case. Remove the two lithium AA cells from the holder.
Identify BAT+ contact (touches positive button-end of AA) and BAT−
contact (touches flat negative end of AA). Leave everything else
connected as deployed: NTC probe wires on the C6, custom 3D-printed
battery holder assembly, tether attachment.

Wire PPK2:

```
PPK2 VOUT  →  BAT+ contact (positive terminal of battery holder)
PPK2 GND   →  BAT- contact (negative terminal of battery holder)
```

Use the included PPK2 jumper wires with small alligator clips or
solder-tinned wire ends to grip the spring contacts cleanly. Verify
polarity twice before powering — reverse polarity at this connection
will likely brick the C6.

USB-C on the C6 must NOT be connected (it isn't in normal deployment,
but worth verifying nothing is plugged in).

## Phase 3 — PPK2 configuration + power up (5 min)

In Power Profiler app:

Mode: Source meter
Supply voltage: 3300 mV
Sampling rate: drag from 100,000 down to **10,000 samples/sec**
View: DATA LOGGER tab (not Scope)
Sample for: forever

The 10 kS/s rate trades fine microsecond-level TX-burst detail for a
10× smaller CSV file. Plenty of resolution for cycle-energy measurement.

Click **Enable power output**.

Verify the C6 boots cleanly:

- Boot current spike to ~150–250 mA for ~0.5 sec
- WiFi associate plateau ~80–120 mA for 1–3 sec
- Brief publish bursts ~150–250 mA peaks
- Drop to sleep floor (expected ~15–25 µA — orders of magnitude lower
  than the S3 DevKitC's 2 mA floor because the C6 has no parasitic loads)

If you see boot-loop pattern (repeated short cycles every few seconds
without reaching sleep), it's a brownout — switch to Ampere meter mode
with external 3.3V supply.

## Phase 4 — Capture (10 min)

Let the capture run for 10 minutes. At 1-min cadence the float will wake
~10 times. PPK2 captures continuously to disk.

Watch the minimap for cycle-to-cycle consistency. Most cycles should
look identical in width and amplitude. Outliers worth noting.

## Phase 5 — Save and export (5 min)

After 10+ wake cycles captured:

Stop the capture.

Save the native .ppk2 file for archive:

```
Save / Export → .ppk2 format → ~/Documents/ppk2-captures/c6-float-bench-2026-05-26.ppk2
```

Export CSV for Claude-side analysis:

```
Save / Export → CSV → All (full capture, not selection only) → 
~/Documents/Claude/Projects/home-assistant/ppk2-c6-float-2026-05-26.csv
```

The destination path is inside your home-assistant workspace folder —
Claude has direct read access. File size at 10 kS/s × 10 minutes
should be ~250 MB.

Disable PPK2 output. Disconnect PPK2 leads from the float battery
contacts. Leave the float open on the bench for now.

## Phase 6 — Hand off to Claude (analysis runs while you stretch)

Tell Claude: "CSV is at home-assistant/ppk2-c6-float-2026-05-26.csv,
ready for analysis."

Claude will run pandas analysis to compute:

- Wake event detection via current-threshold (e.g., > 5× sleep floor)
- Per-wake metrics: energy (mC), duration (s), peak current (mA), avg current (mA)
- Distribution across all wakes: min, median, p95, max for each metric
- Sleep floor: mean and stddev across sleep regions
- Per-cycle total energy (wake + sleep until next wake)
- Cycle-to-cycle variance

Output: summary table + per-cycle detail.

Expected ballpark values for sanity check:

- Wake duration: ~2-4 sec (faster than S3 — bench has stronger signal)
- Wake energy: ~250-400 mC per cycle
- Peak current: ~250 mA
- Sleep floor: ~15-25 µA

If values are wildly off from these, something's wrong with the setup —
loose wiring, wrong source voltage, etc.

## Phase 7 — Production cadence decision (5 min)

With actual measured numbers, plug into the battery formula:

```
Daily mA·h = (cycles_per_day × wake_mC / 3600) + (sleep_uA / 1000 × 24)
Runtime_days = 2700 / Daily_mAh
```

Where 2700 mAh is the rated capacity of 2× Energizer L91 lithium AA
in series (effective at this load profile).

Target: ≥1.5× margin over the 138-day departure window = ≥207 days runtime.

Likely outcome: 10-min or 15-min cadence wins. Claude recommends final
value based on numbers.

## Phase 8 — Flash production cadence (10 min)

If cadence change is needed (e.g., 1-min → 10-min):

```
cd ~/code/home-assistant
```

Edit `esphome/pool-water-temp-external.yaml`, change
`sleep_duration: 1min` to your chosen production cadence.

```
git add esphome/pool-water-temp-external.yaml
git commit -m "ADR-015: set production cadence to <X> for summer deployment"
git push
```

On SCS or SSH:

```
cd /config
git pull
```

ESPHome dashboard → pool-water-temp-external → Install. OTA flash works
while the C6 is still bench-powered via PPK2 (WiFi is active during
wake windows; flash via the C6's WiFi → API path).

Wait for flash to complete and the device to reboot.

## Phase 9 — Reassemble + redeploy (10 min)

Disable PPK2 output if not already off.

Disconnect PPK2 leads from BAT+/BAT- contacts.

Install fresh 2× Energizer L91 lithium AA cells into the battery holder.
Verify polarity at install (positive end of each AA touches the BAT+
contact on its respective side of the series pair).

Close the float case. Confirm the existing gasket seats properly.
Verify the NTC probe wire pass-through hasn't been disturbed.

Place float in pool. Reattach dual tether (one tether on each side per
the constraint preventing the ladder-pinning we saw earlier).

## Phase 10 — Verify redeployment (5 min, ongoing over next hour)

Watch UniFi events for new connection events at the production cadence
(e.g., at 10-min cadence, expect a new connection every ~10 min).

Check HA Developer Tools → States for:

- `sensor.pool_water_temp_external` — new publishes appearing
- `sensor.pool_water_temp_external_filtered` — should track raw cleanly
- `sensor.pool_water_temp_external_pool_float_uptime` — small values (~2-4 sec)
- `sensor.pool_water_temp_external_pool_float_wifi_signal` — back at deployment RSSI (~-86 dBm)

If all four publish within the expected cadence window, deployment is
verified. Float is ready for summer.

## Quick reference card

Print separately and bring to the bench:

```
PPK2:    Source meter, 3300 mV, 10 kS/s, Data Logger
WIRING:  PPK2 VOUT  -> Float BAT+
         PPK2 GND   -> Float BAT-
         USB-C      = disconnected
CAPTURE: 10 minutes, ~10 wake cycles
SAVE:    .ppk2 to ~/Documents/ppk2-captures/
EXPORT:  CSV to ~/Documents/Claude/Projects/home-assistant/
         filename: ppk2-c6-float-2026-05-26.csv

Then tell Claude: "CSV ready for analysis"
```
