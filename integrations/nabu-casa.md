# Nabu Casa (HA Cloud)

HA Cloud subscription. Provides Cloud STT/TTS, remote access, the Alexa Smart Home bridge currently in production, and a Google Assistant bridge that's enabled but not actively used.

---

## Subscription

- **Service:** Home Assistant Cloud (Nabu Casa)
- **Account:** scott@dubecars.com
- **Status (2026-04-28):** **Trial — expires May 4, 2026.** Decision pending: subscribe (recommended given the dependencies below) or lapse.
- **Instance name:** LRD Home
- **Instance ID:** `ee341ebb55d84283873f2876ba13cba2`
- **HA Core at trial signup:** 2026.4.4
- **Remote URL:** `https://gzrtdlwrcp08lgcwooicdige17ysnam3.ui.nabu.casa`

---

## What we use it for

| Feature | Status | Notes |
|---|---|---|
| Cloud STT | **Active** | Used by LRD Voice Assistant pipeline. American English. |
| Cloud TTS | **Active** | Davis voice, High quality (per ADR-003). Used by voice satellites and any TTS targets. |
| Remote access | **Active — primary path** | Nabu Casa is the primary remote-access method today. WireGuard is available as an alternative path but not currently configured. |
| Alexa Smart Home bridge | **Active** | 18 entities exposed. State reporting enabled. Used for "Alexa, turn on the kitchen lights" style control of HA devices. "Expose new entities" automatically: OFF. |
| Google Assistant bridge | **Enabled but unused** | Toggle is ON in HA Cloud, but the Google Home app side was never linked. No active devices control HA via Google. Worth either finishing the setup or turning the toggle off to reduce surface area. |
| Cloud LLM conversation agent | Not in active use as canonical agent | LRD Voice Assistant pipeline uses **OpenAI Conversation** as the conversation agent today. See ADR-003 (needs sync — OpenAI is back in production with local-first preference). |

---

## Configuration

- HA UI: Settings → Home Assistant Cloud
- **Assist exposure:** 45 entities exposed (cleaned up from earlier 573 figure). "Expose new entities" toggle is OFF — new entities don't auto-leak.
- **Alexa exposure:** 18 entities, state reporting ON, "Expose new entities" OFF.
- **Google exposure:** "Expose new entities" OFF; bridge unused regardless.

---

## Voice pipelines (defined under Settings → Voice Assistants)

Four pipelines exist:

- **Home Assistant** — built-in agent only (no cloud), default fallback
- **Home Assistant Cloud** ⭐ (starred / system preferred) — STT/conversation/TTS all via HA Cloud
- **Alexa** — for Alexa Voice integration paths
- **LRD Voice Assistant** — the pipeline assigned to physical voice satellites. STT: HA Cloud · Conversation: OpenAI Conversation (local-first preference) · TTS: HA Cloud (Davis voice)

The starred default and the LRD Voice Assistant pipeline use different conversation agents. This is intentional — the LRD pipeline gets OpenAI for richer conversation; the Cloud-default pipeline is the safe fallback.

---

## Known quirks

- **STT/TTS latency** can spike during Nabu Casa-side incidents. Voice satellite UX degrades during these windows. No automatic fallback configured today.
- **Conversation agent drift** is a real risk. If the LRD Voice Assistant pipeline's OpenAI agent becomes unavailable (API key issue, service outage, billing), satellites enter the same red-LED retry loop seen with the Ollama incident on 2026-04-28. Periodic agent health audit recommended (cleanup-plan reference).
- **Google Assistant bridge enabled but unfinished.** Either finish the Google Home app setup or disable the toggle. Currently consumes no resources but shows up in the UI as "Continue setting up..." which is noise.

---

## Why this exists today

- Cloud TTS/STT we don't run locally (no Whisper + Piper stood up on the NUC).
- Alexa Smart Home bridge for voice control of HA devices via Echo.
- Stable remote URL for the HA app and external webhook integrations.
- Remote access (currently primary; WireGuard available as alternative if reconfigured).

---

## Cancellation impact

If the subscription lapses (current path if no action taken before 2026-05-04):

- **Voice satellites lose STT/TTS.** Garage VA goes red until a local pipeline (Whisper + Piper) is configured.
- **Alexa control of HA devices stops.** The 18 exposed entities disappear from Alexa routines.
- **Remote access via Nabu Casa goes away.** WireGuard would need to be reconfigured to restore remote.
- **Stable remote URL goes away.** Anything pointing at the `*.ui.nabu.casa` URL breaks.
- **Cloud LLM agent stops** (not currently canonical anyway, but the option goes).

Mitigation paths:

1. **Subscribe.** Removes the cliff.
2. **Stand up Whisper + Piper on the NUC.** Feasible given the hardware. Replaces STT/TTS but not Alexa/remote.
3. **Reconfigure WireGuard.** Replaces remote access but not Alexa or STT/TTS.

Cleanup-plan recommendation: schedule the trial-vs-subscribe decision as a near-term task. May 4 is close.

---

## Cross-references

- ADR-003: voice pipeline (needs sync — currently states HA Cloud as canonical conversation agent, but production reality is OpenAI on the LRD pipeline)
- `current-state.md`: voice assistant satellites section
- `integrations/zwave-js.md`, `integrations/midea-ac-lan.md`, etc.: most local-first integrations are independent of Nabu Casa
