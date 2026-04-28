# Nabu Casa (HA Cloud)

HA Cloud subscription. Provides Cloud STT/TTS, remote access (backup path), and Google/Alexa Smart Home bridge if used.

---

## Subscription

- **Service:** Home Assistant Cloud (Nabu Casa)
- **Account:** Scott's HA Cloud account
- **Renewal:** TODO capture date

---

## What we use it for

| Feature | Purpose | Notes |
|---|---|---|
| Cloud TTS | Voice satellite responses, Echo Speaks alternative | **Davis voice, High quality** (per ADR-003) |
| Cloud STT | Voice satellite speech recognition | Used by garage voice satellite |
| Remote access | Backup remote path | Primary remote access is WireGuard via UDM SE; Nabu Casa is failover |
| Alexa Smart Home | TODO confirm if used or disabled | Echo Speaks (HACS) handles TTS; Alexa skill exposure is separate |
| Google Assistant | TODO confirm | |

---

## Configuration

- HA UI: Settings → Home Assistant Cloud
- Exposed entities: TODO audit — current-state.md flags 573 entities exposed to Assist; same likely overexposes to Cloud bridges. Item on cleanup-plan backlog.

---

## Known quirks

- **STT/TTS latency** can spike during Nabu Casa-side incidents. Voice satellite UX degrades during these windows. No fallback configured.
- **OpenAI experiment** (alternative cloud LLM/STT path) was tested but reverted due to billing and quality concerns. See ADR-003.

---

## Why this exists

WireGuard via UDM SE is the primary remote-access path. Nabu Casa serves as backup remote, plus the cloud TTS/STT we don't run locally (yet). On-device wake word is microWakeWord (per ADR-003); server-side openWakeWord remains for Hey Nabu but adds latency.

---

## Cancellation impact

If the subscription lapses:
- Voice satellites lose STT/TTS until a local pipeline (Whisper + Piper) is configured
- Backup remote access goes away (WireGuard still primary)
- Any Smart Home bridge integrations stop working

Mitigation: a local Whisper + Piper pipeline is feasible on the NUC but not yet stood up. Not urgent while Nabu Casa is paid.
