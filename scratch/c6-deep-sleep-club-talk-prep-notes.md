# Speaker Prep — Chasing 365 µA on a XIAO ESP32-C6

**Venue:** Hands-On Tech / Small Computers (The Villages)
**Audience:** ESP32 / Arduino / IoT / Home Assistant makers — project-oriented, technically literate
**Length target:** 10–15 minutes + Q&A
**Source material:** `scratch/c6-deep-sleep-article-draft.md` (full article)

Read this before walking up. Future-you will not remember the lambda block.

---

## The story in one breath (if I forget everything else)

I had a pool float with a XIAO ESP32-C6 measuring water temp. Sleep current
should have been 15 µA. It was 381. I followed a popular Seeed forum theory
("voltage trap below 3.5 V") for a day and wrote it into my notes. Then I
broke out a PPK2 and a fresh stock C6 and proved myself wrong with a
controlled bench experiment. Real cause was the NTC voltage divider sitting
on the 3V3 rail full-time costing 10× what the math predicts, plus a fixed
~74 µA chip-level ADC bias. Fix is moving the divider's reference resistor
from 3V3 to a GPIO that goes LOW during sleep. 287 days of runtime becomes
668 days, single wire move plus 8 lines of firmware. The forum was wrong;
the bench told the truth.

That's the whole talk in 100 words. Everything else is texture and proof.

---

## The three numbers that anchor the entire story

**15 / 89 / 333.** If I'm getting lost mid-talk, anchor back to these.

- **15 µA** — bare stock C6, no peripherals, what we should hit
- **89 µA** — same C6 with the fix applied (GPIO-gated divider)
- **333 µA** — same C6 with the broken design (divider on 3V3)

Three rows of the bench matrix told the entire story. The other rows are
just "did I check ___?" — pin floating, ADC channel count, attenuation.
None of them moved the needle. The 333 → 89 jump is the win.

---

## Slide-by-slide talking points

### Slide 1 — Title

Open warm. "I want to walk you through a project where I followed a popular
piece of internet wisdom down the wrong path, then dug myself out with a
bench experiment. Pool float, ESP32-C6, deep sleep current."

### Slide 2 — The project

The constraint is 138 days unattended. Float drifts in the pool while I'm
in NH. Every microamp matters because cell capacity is finite. Battery is
2× L91 lithium AAs, ~3500 mAh, in series for 3.0–3.4 V across discharge.

Optional aside if it lands: "I built this because the OmniLogic in-pool
temp probe reads `unknown` whenever the filter pump is off, which is most
of the night. Independent sensor closes the gap."

### Slide 3 — The symptom

Two big numbers. The amber 381 is what I measured on the deployed float.
The teal 15 is what the Seeed forum's BASIC example says you can hit.

"Where's the missing 365 µA?"

### Slide 4 — The wrong theory

Walk through honestly. The forum thread is real, the math nearly fit, the
symptom matched. I bought it.

Important: don't be defensive about being wrong. The audience respects
honesty. Self-correction is the credibility move.

### Slide 5 — The bench setup

The methodology slide. "One variable per test" is the line to deliver.
This is what made the matrix possible.

Fresh stock C6 means no modifications — exact same hardware anyone in the
room could buy. PPK2 in Source Meter mode means it's both the power source
AND the current meter — sources 3.3 V and measures every microamp going in.

### Slide 6 — The matrix (the heart of the talk)

This is the slide to slow down on. Walk down the table row by row:

- Row 1 (15.66 µA): "Stock C6, minimal firmware. This kills the voltage
  trap theory right here."
- Row 2 (15.66 µA): "Same board, but now with the full pool float firmware
  loaded — ADC sensors configured, lambdas in place. Nothing wired up yet.
  Still 15. So the firmware alone isn't the problem."
- Row 3 (333.77 µA): "Now I add just the resistor divider. The thing on
  the deployed float that reads the NTC temperature. Boom — 10× jump."
- Row 4 (89.51 µA): "The fix — I'll explain in two slides. Recover 244 µA."
- Rows 5–7: "I tried three more things to drop the last 74 µA. Nothing
  moved it."

### Slide 7 — First surprise

The "voltage trap is dead" punchline. One big number on the slide. Pause.

This is the moment the audience realizes the forum was wrong, and that the
matrix structure was the point of the methodology.

### Slide 8 — Effect #1 (the divider costs 10× the math)

Show the math: 47 kΩ + 47 kΩ across 3.3 V = 35 µA by Ohm's law. Bench
measured 318 µA above the floor. That's an order of magnitude off.

**Be careful here**: I do NOT know the exact mechanism. My best read is
something in the ADC pin's input frontend is loading the divider, but I
haven't measured it directly. If a real EE in the room knows, I want to
hear it. Hold loosely.

### Slide 9 — Effect #2 (ADC subsystem bias)

The four 89 µA tests. Same number every time. Whatever this is, it's
chip-level — independent of channels, attenuation, pin connections.

My READ is that initializing the ADC peripheral in ESP-IDF keeps some
reference circuit biased. Untested but plausible — `adc_oneshot_del_unit()`
before sleep would test it. I didn't try.

### Slide 10 — The fix (the slide I'll forget by next fall)

**See the dedicated lambda explanation below — read it before walking up.**

High-level: move the 47 kΩ reference resistor's top end from the 3V3 rail
to GPIO2. GPIO2 is software-controllable. Drive it HIGH at the start of a
wake cycle so the divider is powered while the ADC samples. Then drive it
LOW just before deep sleep and "freeze" it there with `gpio_hold_en`.
During sleep, the divider sees 0 V on top and 0 V on bottom — no voltage
across it, no current, no 245 µA waste.

Eight lines of firmware. One wire move. 244 µA recovered.

### Slide 11 — Runtime impact

287 days → 668 days. 2.3× more deployment runtime.

"For context, my unattended window is 138 days. The original design clears
that with margin. The fix doubles that margin." Reassuring framing —
nothing was broken in deployment, the fix is a bonus.

### Slide 12 — Takeaways + Q&A

Read each takeaway briefly. Land on the last one: facts are solid,
explanations are inferred, be honest about the difference.

"Questions?"

---

## The lambda explanation (for slide 10 — read every time before presenting)

In ESPHome, the YAML config file is mostly **declarative** — I describe
what sensors I want, what schedule to follow, what to publish to Home
Assistant. ESPHome figures out the C++ underneath. Sometimes I need to do
something the YAML can't express directly — that's where lambdas come in.

A **lambda** is a small block of C++ code I drop into the YAML as an escape
hatch. The word comes from programming theory and just means "small
anonymous function" — a chunk of code attached to an event ("when the
device boots", "before deep sleep") rather than to a name I'd call from
elsewhere. ESPHome compiles the lambda into the firmware along with the
rest of the YAML.

The two lambdas in this fix:

**On wake** — runs in the `on_boot` block at "priority 800", which means
"very early in the boot sequence, before other components initialize":

| Line | Plain English |
|---|---|
| `gpio_hold_dis((gpio_num_t)2);` | Release the "freeze" we put on GPIO2 right before the last sleep. If we don't release it, the pin stays locked and we can't change its state. |
| `gpio_reset_pin((gpio_num_t)2);` | Clear any leftover configuration on the pin. Fresh start. |
| `gpio_set_direction((gpio_num_t)2, GPIO_MODE_OUTPUT);` | Tell the chip "I'm going to drive this pin, not read from it." |
| `gpio_set_level((gpio_num_t)2, 1);` | Set the pin HIGH — about 3.3 V. This is now the power source for the top of the resistor divider. The ADC can sample a real voltage on GPIO1. |

**Before sleep** — runs at the end of the wake script, just before
`deep_sleep.enter`:

| Line | Plain English |
|---|---|
| `gpio_set_level((gpio_num_t)2, 0);` | Drop the pin to LOW — 0 V. The divider's top side is now grounded; no voltage across the divider; no current flows. |
| `gpio_hold_en((gpio_num_t)2);` | "Freeze" the pin in this LOW state so the chip can't reset it during deep sleep. Without this, current would leak again. |

The `(gpio_num_t)2` syntax is a **type cast** — required by the ESP-IDF
API. `gpio_num_t` is a special data type ESP-IDF uses to refer to GPIO
pins, and the cast tells the compiler "treat the number 2 as a gpio_num_t
identifier." It's pedantic but the API requires it.

The whole point: GPIO2 acts like a switch on the top of the resistor
divider. It's powered only during the few seconds per wake cycle when the
firmware reads the temperature, then dark for the rest of the time. The
divider exists physically but draws zero current most of the time.

Why GPIO2 specifically? On the ESP32-C6, pins 0–7 are "RTC-capable" — they
can be controlled by the always-on RTC subsystem, which is what stays
powered during deep sleep. GPIO2 is in that range, easy to wire on the
breadboard, and free in our pin assignment. Its default drive strength is
20 mA per the Espressif datasheet — the divider only draws 35 µA, so we
have 500× headroom. No drive-strength concerns.

---

## Anticipated audience questions

**Q: Why didn't you just use a DS18B20 / MCP9808 in the first place?**
A: Fair question. The float case is a reused commercial pool thermometer
whose original PCB had corroded but whose NTC probe and waterproof
pass-through gasket were still healthy. Reusing the NTC kept the one seal
I trusted. For a clean-sheet design, I'd absolutely start with a digital
sensor and skip most of this story.

**Q: Have you tried `adc_oneshot_del_unit()` to kill the last 74 µA?**
A: Not yet. It's the obvious next experiment. If anyone in the room wants
to take it, the bench setup is reproducible from the article. I'd love to
hear the result.

**Q: How sure are you about the "ADC frontend loading" explanation?**
A: Not very. The measurement is unambiguous — 333 µA when the divider's
on 3V3, 89 µA when GPIO-gated, 15 µA with no divider. Why the divider
costs 10× the passive math when connected to an ADC pin, I'm guessing.
If a real EE wants to explain it, I'll update the article.

**Q: Did you try lower ADC attenuation?**
A: Tested 6 dB vs 12 dB. Same 89 µA both ways. Attenuation doesn't move it.

**Q: What's the PPK2 cost?**
A: $179 on Amazon. Paid for itself in one afternoon of this debug — without
it I'd never have resolved the 15 / 89 / 333 µA distinctions cleanly. For
any low-power ESP32 / nRF / battery work, it's the right tool.

**Q: Is the deployed float fixed?**
A: Not yet. It's running the old design with the 287-day projection,
which still clears my 138-day window with margin. The fix lands at the
next maintenance pull or next-season hardware rework. I didn't want to
risk a mid-season firmware change.

**Q: Can I get this code / YAML / wiring diagram?**
A: Yes — happy to share via the club's GitHub member pages or email.
Repo is `scottdube/lrd-ha-config` on GitHub, ESPHome firmware in
`esphome/pool-water-temp-external.yaml`, ADR write-up in
`docs/decisions/025-pool-float-v2-hardware-revision.md`.

---

## Things I might fumble mid-talk

- "It's an ADC voltage divider issue" is the punchline of Effect #1. Don't
  say "voltage divider sensor" — say "voltage divider" or "resistor divider."
- The fix isn't about reducing the resistor values — adding bigger resistors
  doesn't help and might cause ADC accuracy issues. The fix is gating WHEN
  current flows through the divider, not how much.
- `gpio_hold_en` and `gpio_hold_dis` — easy to mix up which one is which.
  Mnemonic: `en` = ENABLE the hold (freeze in current state), `dis` =
  DISABLE the hold (release the freeze). Use on wake (release), use before
  sleep (freeze).
- The 74 µA residual is the ADC SUBSYSTEM bias, not the divider. Don't
  conflate the two.

---

## Closing

If the talk runs short, end on takeaway #4 ("Hold your conclusions
loosely") and pivot to questions. The methodology — controlled matrix
with one variable per test — is the most reusable thing I have to offer
this audience. The specific bug is just the example.

Good luck, future me.
