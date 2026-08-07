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
