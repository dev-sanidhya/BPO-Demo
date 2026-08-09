# Real call test audio

`real-call-sample.wav` is a real customer service help-line call recording
("Warid_help_line"), sourced from the public-domain Internet Archive item
[Call Center Audio](https://archive.org/details/CallCenterAudio) and
converted to 8kHz mono PCM WAV (Asterisk's expected sound format) with:

```
ffmpeg -i warid_help_line.mp3 -ar 8000 -ac 1 -sample_fmt s16 real-call-sample.wav
```

Used by `scripts/make_real_call_test.py` to prove the transcription/QA
scoring/nudge pipeline against genuine call content — not just Asterisk's
own demo audio (`demo-congrats`, `demo-thanks`), which is generic
installer narration with nothing for a QA rubric or coaching nudge to
react to.

## Multilingual support fixtures

`synthetic-support-hi.*`, `synthetic-support-mr.*`, and
`synthetic-support-hi-en.*` are synthetic customer-support calls generated
with Microsoft Edge TTS voices by `scripts/generate_multilingual_fixtures.py`.
Each JSON manifest contains the exact input turns, speakers, language, and
timestamps. They are repeatable test fixtures, not recordings of people and
not evidence of real-world accuracy.

Model selection was also checked on streamed samples from Google's FLEURS
dataset (`google/fleurs`, CC-BY-4.0): Hindi sample
`10011266027513218401.wav` and Marathi sample
`10029086309791186826.wav`. Those source files are intentionally not copied
into this repository. On the measured samples, `whisper-large-v3` beat Turbo
for Hindi and Marathi and was substantially better on the synthetic Hinglish
fixture. The Marathi error rate remained too high for autonomous QA, so the
product labels Marathi as review-required.
