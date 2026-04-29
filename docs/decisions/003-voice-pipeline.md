# ADR-003: Voice pipeline — HA Cloud STT/TTS + OpenAI conversation (local-first); Ollama as alternative

**Status:** Accepted (revised 2026-04-28 evening to match production reality)
**Date:** 2026-04 (revised 2026-04-28)
**Decider:** Scott

## Context

Voice satellites need a STT → conversation → TTS pipeline. Options evaluated:

1. **Local Whisper + Piper** — runs on the NUC, no cloud dependency, free. Lower quality voices, NUC CPU load per interaction.
2. **HA Cloud (Nabu Casa)** — $65/year, cloud STT/TTS, multiple voice options (Davis chosen, High quality). Reliable, no local CPU load, requires internet.
3. **OpenAI** — best-in-class conversation (gpt-4o-mini), best STT (gpt-4o-mini-transcribe), best TTS (gpt-4o-mini-tts). Pay-per-use API. Higher quality than HA Cloud TTS but requires API credits separate from ChatGPT Plus.
4. **Ollama** — local LLM as conversation agent. STT/TTS still need to come from somewhere (HA Cloud, local, or another provider). Free at the LLM layer; requires Ollama server running and an entity exposed in HA as `conversation.<...>`.

OpenAI was tested in production. Findings:
- Conversation quality noticeably better than the local HA conversation agent.
- TTS audio compatibility issue with the ESP32-S3 + MAX98357A chain. OpenAI TTS output format produced playback errors. HA Cloud TTS worked cleanly.
- Billing surprise. $20/month ChatGPT Plus does not include API credits — those are billed separately on platform.openai.com.

Ollama was set up and used as an alternative conversation agent (`conversation.ollama_conversation`). Worked when the Ollama server was running. **Failure mode discovered 2026-04-28:** when the Ollama conversation entity is referenced by an active pipeline but the entity is not currently available in HA (server down, integration removed, entity renamed), every assigned satellite enters a tight error retry loop. The garage satellite's red LED was traced to the pipeline still pointing at Ollama after the entity went missing.

## Decision

**Canonical pipeline for voice satellites (LRD Voice Assistant):**
- STT: HA Cloud (American English)
- TTS: HA Cloud (Davis voice, High quality)
- Conversation agent: **OpenAI Conversation** with **"Prefer handling commands locally"** ON. Local HA agent gets first crack at every command; OpenAI handles only what local can't (general questions, ambiguous requests). This minimizes OpenAI API spend while preserving GPT-class fallback quality.

**System default pipeline** (Settings → Voice Assistants ⭐ "Home Assistant Cloud"):
- STT/conversation/TTS all HA Cloud. Acts as the safe fallback that any new device defaults to before being assigned to LRD Voice Assistant. Always available as long as the HA Cloud subscription is active.

**Supported alternative pipelines** (per-device or experimental, NOT default):
- **Ollama conversation agent** — fully supported as an alternative pipeline option. Acceptable to assign to a satellite *as long as someone monitors the Ollama agent's availability* and accepts that an outage will surface as red LEDs / VA Errors on the affected device. The 2026-04-28 incident: a stale `conversation.ollama_conversation` reference in an active pipeline put garage VA into a tight retry loop.

**Rule:** if a satellite is assigned to a non-default pipeline (LRD Voice Assistant or Ollama), the assigned conversation agent's availability must be monitored. The system default (HA Cloud) is what new/recovery devices should default to.

**OpenAI TTS** specifically (separate from OpenAI as conversation agent) is NOT in production due to playback compatibility issues with the ESP32-S3 + MAX98357A audio chain. HA Cloud TTS works cleanly on that hardware. Re-evaluate OpenAI TTS once the I2S audio quality issue (separate problem) is resolved.

## Consequences

### Positive
- Default pipeline works reliably with the ESP32-S3 + MAX98357A audio chain.
- $65/year is reasonable; also funds HA development.
- Bundles cloud TTS/STT with remote access (replacing the unreliable WireGuard remote setup).
- Ollama remains available for experimentation without risk to the canonical setup.

### Negative
- All voice traffic on the canonical path goes through Nabu Casa servers — privacy trade-off acknowledged.
- HA Cloud conversation agent quality is meaningfully behind OpenAI/GPT-class models.
- Pipeline-to-agent assignments live in HA's `.storage` (UI-managed), making them invisible to git. Drift detection requires a manual audit pass.

### Revisit conditions
- I2S audio clarity issue resolved → re-test OpenAI TTS for output compatibility.
- microWakeWord on-device → reduces server-side wake word latency, may shift the cost calculus.
- HA Cloud price change or feature change.
- Ollama becomes hosted/managed in a way that removes the uptime monitoring burden.

## Operational notes

- **Periodic audit of pipeline assignments.** Settings → Voice Assistants → for each pipeline, confirm the conversation agent entity still exists. Stale references are silent until a device tries to use them.
- **Symptom of pipeline drift on satellites:** red LED solid (per `voice-garage.yaml` `on_error` handler), tight retry loop visible in ESPHome logs as repeating `Error: intent-not-supported - Intent recognition engine conversation.<name> is not found`.
- **Quick fix when this happens:** change the pipeline's conversation agent to a known-good one (HA Cloud / Home Assistant) → satellite recovers within seconds, no device-side action required.
