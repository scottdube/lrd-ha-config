# Chasing 365 µA on a XIAO ESP32-C6 — it's not what I thought

**TL;DR:** I had a XIAO ESP32-C6 in a battery-powered pool float drawing
~381 µA in deep sleep when I thought it should be ~15 µA. The Seeed
forum had a popular theory about a "voltage trap" when running below
3.5 V, and that's what I went with for a day. Then I broke out a Nordic
PPK2 and a fresh stock C6 and proved myself wrong. The real culprit
was the NTC voltage divider sitting on the 3V3 rail full-time
(~245 µA — about 10× what the passive math predicts) plus a fixed
~74 µA cost just for having the ADC peripheral configured at all. The
fix is moving the divider's reference resistor from 3V3 to a GPIO and
driving it LOW during sleep. That alone gets you back to ~89 µA — a
4× improvement, no hardware change beyond moving one wire. Here's the
bench data and the recipe.

## The project

I built a pool water-temperature sensor float — a XIAO ESP32-C6 with
an NTC thermistor sitting in a sealed case bobbing in my pool,
reporting to Home Assistant every 30 minutes. 2× L91 lithium AA cells
in series for power. I bypassed the SGM6029 buck-boost regulator by
feeding 3V3 directly from the cells (the regulator's quiescent eats
too much current at the L91 voltage range), added a U.FL external
antenna for range, and ran an NTC + 47 kΩ reference resistor divider
on GPIO1 to read water temp.

The thing needs to survive 138 days unattended every summer while I'm
out of state. Sleep current matters a lot.

(Fair question before we go further: why NTC + ADC at all instead of a
DS18B20 or MCP9808? Honest answer is project history. The float case
is a reused commercial pool thermometer whose original PCB had
corroded out but whose NTC probe was still healthy, sealed through
the case wall with an epoxy gasket I didn't want to drill out and
redo. Reusing the NTC kept the one waterproof seal I trusted not to
fail. For a clean-sheet design I'd absolutely start with a digital
sensor and skip most of this. The lessons here still apply if you're
doing any ADC sensing on a low-power C6 build, which is most of the
projects I see in the forum.)

## What I thought was happening

When I measured the deployed float with the PPK2 yesterday, sleep
current came in at 381 µA. The Seeed forum's "BASIC example" thread
says you can hit ~15 µA on a clean setup. So something in my
modifications was costing me 365 µA. The closest existing explanation
I found was a forum discussion about the XIAO ESP32-C6's power
management not entering proper low-power mode below ~3.5 V supply —
"voltage trap" was the term. With L91s at 3.0–3.4 V across their
discharge curve, my supply sits inside the trap range, and the
symptom matched closely enough that I bought it.

I wrote it up in my project notes and moved on. Deployment runtime
math still cleared my 138-day window with margin, so good enough for
the season.

Today some fresh stock C6 boards showed up and I decided to verify
the theory before locking it in for next-season's hardware revision.

## The bench setup

PPK2 in source meter mode at 3300 mV, leads on the 3V3 and GND pins of
a fresh stock C6. No USB, no battery, no modifications. Same power
topology as the modded float, but the board is otherwise untouched.
Then I started adding pieces of the float's design one at a time and
watching the PPK2 trace, changing one variable per test.

*[Insert photo: breadboard with C6 + 47 kΩ resistors + PPK2 clip leads]*

## What actually happened

Here's the table I ended up with. Each row is one change from the row
above:

| Configuration | Sleep current |
|---|---|
| Stock C6, minimal firmware | **15.66 µA** |
| Stock C6, full pool-float firmware (ADC sensors configured, nothing physically wired) | 15.66 µA |
| Add 47 kΩ + 47 kΩ NTC divider, high side on 3V3 | **333.77 µA** |
| Move divider's high side to GPIO2 (driven HIGH on wake, LOW with `gpio_hold_en` during sleep) | **89.51 µA** |
| Remove the second ADC sensor (battery voltage) from firmware | 89.55 µA |
| Lift GPIO1 from the divider entirely (pin floating) | 89.53 µA |
| Change ADC attenuation 12 dB → 6 dB | 89.53 µA |

The first row killed the voltage trap theory immediately. A fresh C6
fed via the 3V3 pin at 3.3 V hits the ~15 µA floor with no problem.
The Seeed forum's 15 µA example reproduces fine at the same supply
voltage where I was supposedly trapped. There is no voltage trap.

So where was my 365 µA going?

## Effect #1 — the NTC divider costs ~10× what the math says

47 kΩ + 47 kΩ across 3.3 V is 94 kΩ. Ohm's law says 35 µA. I expected
the NTC divider to cost me 35 µA, which is small enough to ignore.
The actual measurement was 318 µA above the bare floor. Almost 10×
the passive math.

I don't have a clean explanation for why. My best read is that the
ADC pin's input frontend at 12 dB attenuation is somehow loading the
divider — maybe bias circuitry in the SAR ADC's analog frontend that
isn't modeled by passive Ohm's-law math — but I'm guessing at the
mechanism, not measuring it directly. If anyone with actual EE
chops can pin down what's really going on, I'd love to hear it.
What I can say from the bench is that changing attenuation from 12 dB
to 6 dB didn't move the number (both produce the same total when the
divider is connected), and what did move it was eliminating the pin's
exposure to a continuous voltage during sleep — which is where the
fix comes from.

*[Insert PPK2 screenshot: the 333.77 µA selection trace from when the divider was on 3V3]*

## Effect #2 — ADC subsystem bias, ~74 µA, fixed cost

Even with the divider GPIO-gated and reading 0 V during sleep, current
sits at ~89 µA — about 74 µA above the bare 15 µA floor. I tried
lifting GPIO1 from the divider so it floated. Same 89 µA. I removed
the second ADC sensor from firmware. Same 89 µA. I changed attenuation
to 6 dB. Same 89 µA.

The only thing that got me back to the bare floor was a configuration
where no ADC sensor was declared in the firmware at all. So my read —
which I'm holding loosely — is that having the C6's ADC subsystem
initialized in ESP-IDF costs about 74 µA of continuous bias,
independent of channels, attenuation, or pin state. That looks
chip-level to me, not a board or design issue I can chase with
another resistor move. Open to other interpretations of the same data.

My guess is you could eliminate it by calling `adc_oneshot_del_unit()`
before deep sleep and re-initializing on the next wake — I haven't
actually tried that, so it's the next experiment if anyone here wants
to take it. For 138-day deployments, ~89 µA is already plenty.

## The fix — one wire + 8 lines of firmware

Move the NTC reference resistor's high side from the 3V3 pin/rail to
GPIO2 (or any other RTC-capable GPIO — they're 0–7 on the C6). The
divider only sees voltage when GPIO2 is driven HIGH, which firmware
does briefly during each wake cycle while the ADC samples, then drops
back to LOW for sleep.

In your ESPHome `on_boot` priority-800 lambda:

```
gpio_hold_dis((gpio_num_t)2);
gpio_reset_pin((gpio_num_t)2);
gpio_set_direction((gpio_num_t)2, GPIO_MODE_OUTPUT);
gpio_set_level((gpio_num_t)2, 1);
```

Just before `deep_sleep.enter` in your wake script:

```
gpio_set_level((gpio_num_t)2, 0);
gpio_hold_en((gpio_num_t)2);
```

`gpio_hold_en` retains the LOW state through deep sleep so GPIO2 stays
at 0 V. `gpio_hold_dis` in the boot lambda releases the hold before
re-driving HIGH on the next wake. GPIO2's default drive strength is
20 mA per the C6 datasheet — the 35 µA divider load is roughly 500×
under the limit, so VOH is essentially equal to VDD and ADC accuracy
isn't affected.

*[Insert PPK2 screenshot: the 89.51 µA selection trace from after the GPIO-gated fix — the "after" picture]*

For my deployment, that single change recovers 244 µA of the 365 µA I
was losing — 73 % of the dominant cost. Runtime at 30-min cadence
improves from 287 days to about 668 days on the same L91 stack. That's
2.3× more deployment runtime than the modified-but-unfixed design,
with zero hardware change to the C6 itself beyond moving one wire.

## Why I'm posting this

The forum thread that anchored me on "voltage trap below 3.5 V" is
still out there, still pointing the next person who hits this same
symptom at the wrong answer. If you've got a modded C6 with way more
sleep current than the BASIC example shows, my first suspect would be
the ADC pin loading a continuously-powered divider, not the supply
voltage. The mechanism was non-obvious to me because the passive math
is off by an order of magnitude from what the bench actually shows,
but the fix itself was trivial once we figured out where to look.

If anyone tries the `adc_oneshot_del_unit()` approach to kill the last
74 µA, I'd love to hear what you find. I'm not chasing it myself this
season but it's the obvious next experiment.

One meta-takeaway from the debugging side: I was wrong because the
forum theory was authoritative-sounding and the math matched closely
enough to be plausible. The bench matrix only became possible because
the PPK2 resolves sub-µA differences in deep sleep cleanly. A
multimeter would never have shown me the 15 / 89 / 333 µA progression
that pulled the real story out. If you're doing low-power ESP32 work
seriously, the PPK2 paid for itself in a single afternoon for me.
