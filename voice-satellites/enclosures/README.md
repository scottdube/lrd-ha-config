# Voice Satellite Enclosures

Custom enclosures for the ESP32-S3 voice satellite units.

## Current design

**Garage unit:** "Golf-ball-on-tee" design. Sphere top houses the speaker and PCB; tapered base houses the mic and provides vertical standoff. Designed in Fusion 360.

**Hardware fits:**
- ESP32-S3 dev board (esp32-s3-devkitc-1, 16MB flash, 8MB PSRAM octal)
- MAX98357A I2S amplifier
- INMP441 I2S microphone
- M3 heat-set inserts: **4.91mm OD, 4.5mm hole** (verified)

**Status:** prototyping in alt-color PLA before final print.

## Where the CAD lives

**TODO:** add Fusion 360 cloud project link or local export path here.

If exporting STL/STEP for archival, drop them in this folder named `voice-satellite-<variant>-v<n>.stl` (e.g., `voice-satellite-golfball-v3.stl`). Don't commit binary CAD source files (Fusion `.f3d`) — keep those in Fusion cloud and link from here.

## Print settings (golf-ball-on-tee, garage)

**TODO:** capture once final tuned. Rough notes from prototyping: layer height, walls, infill, supports for sphere overhang.

## Future variants

Each location may need a variant for mounting style:
- **Wall-mount** (kitchen, lanai)
- **Tabletop / shelf** (master bedroom — same as garage)
- **Hidden** (?)

Document variant decisions per location as they're built.
