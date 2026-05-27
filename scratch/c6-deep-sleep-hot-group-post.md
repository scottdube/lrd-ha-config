# HOT Small Computers Google Group — post draft

**Subject:** ESP32-C6 deep sleep — I was wrong about the "voltage trap" (and a presentation idea)

---

Hi all,

Sharing a writeup of some bench work I've been doing on the XIAO ESP32-C6,
partly to invite feedback and partly to gauge whether there'd be interest
in me presenting this at a future Small Computers meeting.

**Short version** — I had a XIAO ESP32-C6 in a battery-powered pool float drawing
~381 µA in deep sleep when I expected ~15 µA. The Seeed forum has a
popular theory about a "voltage trap" below 3.5 V supply, and I bought it
for a day. Then I ran a controlled bench experiment with a fresh stock C6
and a Nordic PPK2 and proved myself wrong. The real cause turned out to
be the NTC voltage divider sitting on the 3V3 rail full-time — costing
about 10× what the passive Ohm's-law math predicts — plus a fixed ~74 µA
chip-level cost just for having the ADC peripheral initialized at all.
The fix is moving the divider's reference resistor from 3V3 to a GPIO
that's driven LOW during sleep. Recovers 244 µA. Runtime at 30-min
cadence goes from 287 days to roughly 668 days on a 2× L91 lithium AA
stack. Single wire move plus 8 lines of firmware.

---

**The project**

Battery-powered pool water-temperature sensor — XIAO ESP32-C6, NTC
thermistor + 47 kΩ reference resistor on GPIO1, U.FL external antenna,
deep sleep with WiFi wake every 30 minutes to publish to Home Assistant.
It needs to survive 138 days unattended every summer while I'm in NH.

**The bench setup**

[ATTACH: breadboard photo here]

Fresh stock C6 — no modifications, no soldering on the board. Powered
via the 3V3 pin from a Nordic PPK2 in Source Meter mode at 3.300 V (same
voltage the deployed float sees from its L91 stack). No USB, no battery.
Then I started adding pieces of the float's design one at a time,
watching the PPK2 trace for changes in the sleep-floor current.

**The matrix that told the story**

Sleep current measured in a flat 8–30 s selection between wake events:

- Stock C6, minimal firmware: **15.66 µA**
- Stock C6 + full pool-float firmware (ADC sensors configured, nothing physically wired): 15.66 µA
- Add 47 kΩ + 47 kΩ NTC divider, high side on 3V3: **333.77 µA**
- Move divider's high side to GPIO2 (driven LOW during sleep, gpio_hold_en): **89.51 µA**
- Remove the second ADC sensor from firmware: 89.55 µA
- Lift GPIO1 from the divider entirely (pin floating): 89.53 µA
- Change ADC attenuation 12 dB → 6 dB: 89.53 µA

Three numbers tell the story: 16, 89, 333.

[ATTACH: PPK2 trace showing the 333.77 µA selection — divider on 3V3]

**What's actually going on**

Two independent effects make up the 365 µA delta. First, the NTC voltage
divider sitting on the 3V3 rail costs about 245 µA when the ADC pin is
configured — roughly 10× what passive Ohm's law predicts for a 94 kΩ
resistor stack at 3.3 V. My best read is the ADC's analog frontend at
12 dB attenuation is loading the divider via internal bias circuitry the
passive math doesn't capture, but I'm guessing at the mechanism, not
measuring it directly. If anyone in here with EE chops can pin it down,
I'd love to hear it.

The second effect is the ~74 µA floor that remains after the divider is
GPIO-gated. Same number whether I have 1 or 2 ADC channels configured,
whether the pin is floating or grounded, whether attenuation is 12 dB or
6 dB. Whatever it is, it's chip-level — having the SAR ADC peripheral
initialized in ESP-IDF appears to cost ~74 µA continuously. I haven't
chased it further.

**The fix**

Move the 47 kΩ reference resistor's high side from the 3V3 rail to a
GPIO. I used GPIO2 because it's RTC-capable (the always-on subsystem can
hold its state through deep sleep), and the 20 mA default drive strength
has massive headroom for the 35 µA divider load. In ESPHome it's an
`on_boot` priority-800 lambda that sets GPIO2 to OUTPUT and drives it
HIGH, plus a pre-`deep_sleep.enter` lambda that drives it LOW and calls
`gpio_hold_en` to retain the LOW state through sleep. The divider only
sees voltage during the few seconds per wake cycle when the ADC samples.
The rest of the time it draws zero.

**The presentation idea**

If there's interest, I'd love to walk this through at a Small Computers
meeting — I'm thinking ~15 minutes of talk plus Q&A. The angle I'd take
isn't "ESP32 power tips" (oversaturated topic) but "how a controlled
bench matrix disproved a popular forum theory" — the methodology of
isolating one variable at a time is the reusable part. If the meeting
slot allows it, I'd bring the PPK2 and the breadboard for a live demo —
swap firmwares mid-talk so the audience can watch the 333 → 89 µA jump
on the PPK2 trace in real time. ~30 seconds of stage business with a
big visual payoff.

Would that fit a future meeting? Happy to hold for fall if November or
December works better than the summer slots.

**A real question for the group**

Has anyone here run into something similar with the C6's ADC on deep
sleep — or any of the ESP32 variants, really? And has anyone tried
calling `adc_oneshot_del_unit()` (or the equivalent in newer ESP-IDF
versions) before `deep_sleep.enter` to fully tear down the ADC
peripheral? My read is it should drop the residual ~74 µA, but I haven't
actually tested it. If anyone wants to take that experiment, the bench
setup is reproducible from what I've described above and I'd love to
compare notes.

**Source material**

I've got a fuller writeup with all the PPK2 screenshots and the
diagnostic path I followed — happy to share with anyone who wants more
detail than this post. Just reply or message me directly and I'll send
it along. Otherwise I'll save the full reveal for the meeting.

Thanks for reading.

Scott
