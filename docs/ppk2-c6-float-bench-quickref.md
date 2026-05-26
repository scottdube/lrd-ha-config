# PPK2 C6 Float Bench — Quick Reference

Bench-side procedure only. Assumes PPK2 ready, float retrieved and case open.

## Wiring

Remove the 2× lithium AA cells from the holder. Identify BAT+ (touches positive end of cell) and BAT− (touches flat end).

```
PPK2 VOUT  ->  Float BAT+ contact
PPK2 GND   ->  Float BAT- contact
USB-C      =   disconnected on C6
```

Verify polarity twice before powering. Reverse polarity bricks the C6.

## PPK2 Settings

```
Mode:     Source meter
Voltage:  3300 mV
Sample:   10,000 samples/sec (drag slider down from default 100k)
View:     DATA LOGGER tab
Run:      Sample for: forever
```

Click **Enable power output**.

## Verify boot (within 5 seconds)

- Boot spike ~150-250 mA, ~0.5 sec
- WiFi associate plateau ~80-120 mA, 1-3 sec
- Brief TX bursts to ~200-250 mA
- Drop to sleep floor (~15-25 µA — orders of magnitude lower than the S3 DevKitC's 2 mA)

If you see boot-loop (repeated short cycles), it's a brownout. Switch to Ampere meter mode with an external 3.3V supply.

## Capture

Let it run **10 minutes**. At 1-min cadence this collects ~10 complete wake cycles. Watch minimap for cycle-to-cycle consistency.

## Save and export

Stop the capture.

```
Save / Export -> .ppk2 native ->
  ~/Documents/ppk2-captures/c6-float-bench-2026-05-26.ppk2

Save / Export -> CSV -> All ->
  ~/Documents/Claude/Projects/home-assistant/ppk2-c6-float-2026-05-26.csv
```

CSV size at 10 kS/s × 10 min: ~250 MB. The export destination is inside the home-assistant workspace folder — Claude reads it directly.

## Hand off to Claude

Disable PPK2 output. Disconnect leads from BAT contacts.

Tell Claude: **"CSV ready at home-assistant/ppk2-c6-float-2026-05-26.csv"**

Claude runs pandas analysis: wake detection via threshold, per-wake energy / duration / peak / avg, distribution stats, sleep floor mean+stddev, per-cycle totals, cycle-to-cycle variance.

## Cadence decision (Claude returns numbers)

Battery formula:

```
Daily mA-h = (cycles_per_day * wake_mC / 3600) + (sleep_uA / 1000 * 24)
Runtime_days = 2700 / Daily_mAh
```

Target: ≥207 days (1.5× margin over 138-day departure). Claude recommends final cadence.

## Flash production cadence

If cadence change is needed, edit `esphome/pool-water-temp-external.yaml`:

```
deep_sleep:
  id: deep_sleep_main
  run_duration: 40s
  sleep_duration: <X>min
```

MacBook:
```
cd ~/code/home-assistant
git add esphome/pool-water-temp-external.yaml
git commit -m "ADR-015: production cadence <X>min for summer deployment"
git push
```

SCS or SSH:
```
cd /config
git pull
```

ESPHome dashboard → pool-water-temp-external → **Install**. OTA flash works while C6 is still bench-powered (WiFi active during wakes).

## Reassemble and redeploy

Disconnect PPK2. Install **fresh** Energizer L91 lithium AAs (verify polarity at install). Close case, confirm gasket seats, verify NTC wire pass-through undisturbed. Float into pool, reattach dual tether.

## Verify

Watch UniFi for connection events at production cadence. Check HA Developer Tools → States for fresh publishes on:

- `sensor.pool_water_temp_external` (raw)
- `sensor.pool_water_temp_external_filtered` (clean)
- `sensor.pool_water_temp_external_pool_float_uptime` (~2-4 sec)
- `sensor.pool_water_temp_external_pool_float_wifi_signal` (~-86 dBm at pool)

If all four publish at the expected cadence within the hour, deployment is verified. Float ready for summer.
