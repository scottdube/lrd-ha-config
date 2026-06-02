# HA OS direct-burn install via macOS CLI

Procedure for writing the Home Assistant Operating System image directly to an NVMe SSD via a USB enclosure, using macOS CLI tools only. Avoids Etcher's Gatekeeper issues on macOS Sequoia / Sonoma+.

Used for the SLN HA NUC install 2026-06-XX (NUC10i5FNH + ANYOYO USB 3.2 Gen 2x2 M.2 NVMe enclosure). Documenting for future re-use (SLN re-install, or LRD rebuild if needed).

---

## Hardware assumption

- macOS host (Apple Silicon or Intel)
- USB-to-NVMe enclosure (e.g., ANYOYO USB 3.2 Gen 2x2 M.2 SATA/NVMe enclosure)
- NVMe SSD removed from the target NUC, seated in the enclosure
- USB-C → USB-A cable to the Mac

## Step 1 — Download the HA OS image

From the Mac terminal:

```
cd ~/Downloads
curl -LO https://github.com/home-assistant/operating-system/releases/latest/download/haos_generic-x86-64-NN.M.img.xz
```

Replace `NN.M` with the current version string from `https://github.com/home-assistant/operating-system/releases`. As of 2026-06-02 the latest stable is the 15.x series — check the release page for the live value before downloading.

Verify the download size matches the release page's reported size; the file is ~370 MB compressed.

## Step 2 — Connect the enclosure, identify the target disk

Plug the USB enclosure into the Mac. Then:

```
diskutil list external
```

The NVMe will appear as `/dev/diskN` (where N is typically 2, 3, or 4 — varies by Mac). Identify by **size + media name** (the NVMe model should be visible).

**Triple-check the disk identifier before proceeding.** Writing to the wrong disk wipes that disk's contents. The macOS internal drive is `/dev/disk0` or `/dev/disk1` — never use those.

## Step 3 — Unmount (don't eject)

```
diskutil unmountDisk /dev/diskN
```

Unmount keeps the device node available to `dd`. Eject would remove it.

## Step 4 — Write the image (xz-decompress inline)

```
xz -dc ~/Downloads/haos_generic-x86-64-NN.M.img.xz | sudo dd of=/dev/rdiskN bs=4m
```

Two non-obvious details:

- **`/dev/rdiskN`** (raw device), **not** `/dev/diskN`. The raw device bypasses the buffer cache and is ~10× faster. `bs=4m` on rdiskN writes the ~1.5 GB decompressed image in ~30–90 seconds on USB 3.2 Gen 2x2.
- **`bs=4m`** lowercase `m`. BSD dd (which is what macOS ships) uses lowercase block-size suffixes. GNU dd accepts both `m` and `M`; BSD silently treats `M` as 1 byte and writes for an eternity. Easy way to verify dd is doing real work: watch the activity light on the enclosure.

`dd` on BSD doesn't support `status=progress`. To check progress while `dd` runs: in the same terminal, press **Ctrl+T**. macOS dd sends SIGINFO on Ctrl+T and prints a current-progress line (`14516224000+0 records in, ...`). Doesn't interrupt the operation.

## Step 5 — Eject when done

```
diskutil eject /dev/diskN
```

Wait for the eject to complete (a few seconds), then physically unplug.

## Step 6 — Reinsert NVMe into NUC

Physically reseat the NVMe SSD in the NUC's M.2 slot. Power on the NUC.

HA OS boots, gets DHCP from the network, and is reachable at `http://homeassistant.local:8123` or `http://<assigned-IP>:8123` from a browser on the same network. First boot takes ~2-3 minutes before the web UI is responsive.

## Why CLI and not Etcher

macOS Sequoia / Sonoma+ Gatekeeper started blocking unsigned/unnotarized disk-writing tools by default. Etcher's notarization status has been inconsistent — some users hit "operation not permitted" errors with no clear path to grant the disk-write privilege. CLI bypasses entirely: `dd` is a system binary, no Gatekeeper involvement.

If you ever do try Etcher and hit the block, the workaround is System Settings → Privacy & Security → Full Disk Access → add Etcher. But the CLI path is simpler and one-shot.

## Troubleshooting

**"dd: /dev/rdiskN: Permission denied"** — missing `sudo` on the `dd` command.

**`xz` decompresses but `dd` writes 0 bytes** — verify `bs=4m` is lowercase `m`, not uppercase `M`. Uppercase silently sets bs=1 byte.

**dd hangs at "0+0 records in"** — the disk is mounted. Re-run `diskutil unmountDisk /dev/diskN` first.

**Wrong disk identifier** — always run `diskutil list external` to get the current device node BEFORE typing the `dd` command. Don't reuse a node from a prior session — USB device numbers can change.

**NUC doesn't boot after reinsert** — check that the NVMe is seated correctly in the M.2 slot and the retaining screw is tightened. Older NUC BIOSes may need "Legacy USB" disabled or boot order adjusted to prefer NVMe.

## Related

- LRD ADR-029 (dual-site HA) — referenced this procedure during SLN bootstrap
- network-docs ADR-017 — SLN HA install plan (consumer of this procedure)
