# ADR-003: Voice pipeline — HA Cloud (Davis/High); OpenAI experimental only

**Status:** Accepted (with revisit pending)
**Date:** 2026-04
**Decider:** Scott

## Context

Voice satellites need a STT → conversation → TTS pipeline. Options evaluated:

1. **Local Whisper + Piper** — runs on the NUC, no cloud dependency, free. Lower quality voices, NUC CPU load per interaction.
2. **HA Cloud (Nabu Casa)** — $65/year, cloud STT/TTS, multiple voice options (Davis chosen, High quality). Reliable, no local CPU load, requires internet.
3. **OpenAI** — best-in-class conversation (gpt-4o-mini), best STT (gpt-4o-mini-transcribe), best TTS (gpt-4o-mini-tts). Pay-per-use API. Higher quality than HA Cloud TTS but requires API credits separate from ChatGPT Plus.

OpenAI was tested in production. Findings:

- **Conversation quality** noticeably better than the local HA conversation agent.
- **TTS audio compatibility issue** with the ESP32-S3 + MAX98357A chain. OpenAI TTS output format produced playback errors. HA Cloud TTS worked cleanly.
- **Billing surprise.** $20/month ChatGPT Plus does not include API credits — those are billed separately on platform.openai.com.

## Decision

**Default pipeline:** HA Cloud STT + HA Cloud TTS (Davis voice, High quality) + HA conversation agent.

Continue using HA Cloud for production. OpenAI conversation can be re-evaluated once the audio quality issue on the satellites is resolved (suspected I2S clock drift, separate problem).

## Consequences

### Positive
- Pipeline known to work reliably with the ESP32-S3 + MAX98357A audio chain.
- $65/year is reasonable; also funds HA development.
- Bundles cloud TTS/STT with remote access (replacing the unreliable WireGuard remote setup).

### Negative
- All voice traffic goes through Nabu Casa servers — privacy trade-off acknowledged.
- Conversation agent quality is meaningfully behind OpenAI/GPT-class models.
- HA Cloud trial → paid subscription decision still active.

### Revisit conditions
- I2S audio clarity issue resolved → re-test OpenAI TTS for output compatibility.
- microWakeWord on-device → reduces server-side wake word latency, may shift the cost calculus.
- HA Cloud price change or feature change.
